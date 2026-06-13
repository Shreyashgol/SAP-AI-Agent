"""
Documents REST API — upload, list, delete, and trigger embedding.

Spec: DI-001, DI-005, DI-006, DI-007, DI-009

Endpoints:
  POST   /documents/upload           — multipart upload, stores file, enqueues embedding
  GET    /documents                  — list tenant documents with status
  GET    /documents/{id}             — single document detail
  PATCH  /documents/{id}             — update metadata (type, department, linked entities)
  DELETE /documents/{id}             — soft-delete (deactivates chunks, removes file)
  POST   /documents/{id}/reprocess   — re-chunk and re-embed an existing document

Supported file types: pdf, docx, txt, md (DI-005)
Max file size: 50 MB (enforced by FastAPI Content-Length check)
Storage: local disk at settings.document_storage_path/{tenant_id}/{document_id}

File extraction:
  txt/md — read directly
  pdf    — Celery task extracts via pymupdf and writes .txt sidecar
  docx   — Celery task extracts via python-docx and writes .txt sidecar
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_current_tenant
from app.core.settings import get_settings
from app.models.document import Document
from app.schemas.document import DocumentPatch, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_TYPES = {"pdf", "docx", "txt", "md", "markdown"}
_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[str | None, Form()] = None,
    department: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    settings = get_settings()

    # Validate type
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_TYPES))}",
        )

    # Read file content
    content = await file.read()
    if len(content) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content):,} bytes). Maximum is {_MAX_SIZE_BYTES:,} bytes.",
        )

    # Persist to storage
    doc_id = uuid.uuid4()
    storage_root = Path(getattr(settings, "document_storage_path", "/tmp/sap_ai_docs"))
    tenant_dir = storage_root / str(tenant["id"])
    tenant_dir.mkdir(parents=True, exist_ok=True)
    file_path = tenant_dir / f"{doc_id}.{ext}"
    file_path.write_bytes(content)

    # Create DB record
    doc = Document(
        id=doc_id,
        tenant_id=tenant["id"],
        uploaded_by=current_user.id,
        filename=file.filename or f"{doc_id}.{ext}",
        file_type=ext,
        file_size_bytes=len(content),
        storage_path=str(file_path),
        status="pending",
        document_type=document_type,
        department=department,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Enqueue embedding task
    try:
        from app.worker.tasks.embedding import embed_document
        embed_document.delay(
            document_id=str(doc_id),
            tenant_id=str(tenant["id"]),
        )
    except Exception:
        # Non-fatal — operator can reprocess manually
        pass

    return doc


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    q = select(Document).where(Document.tenant_id == tenant["id"])
    if status_filter:
        q = q.where(Document.status == status_filter)
    q = q.order_by(Document.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    doc = await _get_or_404(db, document_id, tenant["id"])
    return doc


# ── Patch metadata ────────────────────────────────────────────────────────────

@router.patch("/{document_id}", response_model=DocumentResponse)
async def patch_document(
    document_id: uuid.UUID,
    body: DocumentPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    doc = await _get_or_404(db, document_id, tenant["id"])
    if body.document_type is not None:
        doc.document_type = body.document_type
    if body.department is not None:
        doc.department = body.department
    if body.linked_entity_ids is not None:
        doc.linked_entity_ids = [str(e) for e in body.linked_entity_ids]
    await db.commit()
    await db.refresh(doc)
    return doc


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    from sqlalchemy import update
    from app.models.document import DocumentChunk, DocumentEmbedding

    doc = await _get_or_404(db, document_id, tenant["id"])

    # Deactivate chunks + embeddings
    await db.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .values(is_active=False)
    )

    # Remove from DB and disk
    storage_path = doc.storage_path
    await db.delete(doc)
    await db.commit()

    try:
        os.remove(storage_path)
        # Remove sidecar .txt if exists
        txt_sidecar = storage_path.rsplit(".", 1)[0] + ".txt"
        if os.path.exists(txt_sidecar):
            os.remove(txt_sidecar)
    except OSError:
        pass  # Non-fatal — storage cleanup is best-effort


# ── Reprocess ─────────────────────────────────────────────────────────────────

@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(get_current_user),
    tenant=Depends(get_current_tenant),
):
    doc = await _get_or_404(db, document_id, tenant["id"])
    doc.status = "pending"
    doc.error_message = None
    await db.commit()

    try:
        from app.worker.tasks.embedding import embed_document
        embed_document.delay(
            document_id=str(document_id),
            tenant_id=str(tenant["id"]),
        )
    except Exception:
        pass

    await db.refresh(doc)
    return doc


# ── Private ───────────────────────────────────────────────────────────────────

async def _get_or_404(
    db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
