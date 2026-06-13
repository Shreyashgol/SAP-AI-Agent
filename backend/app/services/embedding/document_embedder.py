"""
Document Embedding Service — chunks and embeds uploaded documents.

Spec: DI-001, DI-002, DI-003, EM-005
- Recursive character splitting: 512 tokens target, 64 overlap
- Embedding model: voyage-3 (input_type="document")
- Stored in document_chunks + document_embeddings
- Re-upload: old chunks deactivated atomically (DI-010)
- Supported: txt, markdown (generic text); pdf/docx handled by caller pre-extract

Chunking strategy:
  1. Split on double-newline (paragraph)
  2. If chunk > MAX_TOKENS, split on single newline
  3. If still > MAX_TOKENS, hard-split on MAX_TOKENS characters
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk, DocumentEmbedding
from app.services.embedding.client import get_embedding_client

log = get_logger(__name__)

MAX_TOKENS = 512      # approx chars ÷ 4 ≈ tokens
CHUNK_OVERLAP = 64    # characters
HARD_CHAR_LIMIT = MAX_TOKENS * 4  # character budget per chunk (~2048 chars)


class DocumentEmbedder:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def process_document(self, document_id: uuid.UUID) -> dict[str, int]:
        """
        Chunk and embed a document. Deactivates old chunks first (re-upload safety).
        Returns {chunks_created, chunks_embedded}.
        """
        doc_result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id,
            )
        )
        doc = doc_result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Deactivate existing chunks (DI-010)
        await self.db.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.tenant_id == self.tenant_id,
            )
            .values(is_active=False)
        )

        # Read document text content from storage path (plain-text assumed here;
        # PDF/DOCX extraction is done by the Celery task before calling this method)
        text = await self._read_text(doc)
        if not text.strip():
            doc.status = "error"
            doc.error_message = "Document has no extractable text content"
            return {"chunks_created": 0, "chunks_embedded": 0}

        # Chunk
        chunks_text = _chunk_text(text)
        if not chunks_text:
            doc.status = "error"
            doc.error_message = "Chunking produced no content"
            return {"chunks_created": 0, "chunks_embedded": 0}

        # Persist chunks
        chunk_records: list[DocumentChunk] = []
        for idx, (content, page_num, section) in enumerate(chunks_text):
            chunk = DocumentChunk(
                tenant_id=self.tenant_id,
                document_id=document_id,
                chunk_index=idx,
                content=content,
                page_number=page_num,
                section_title=section,
                token_count=len(content) // 4,
                is_active=True,
            )
            self.db.add(chunk)
            chunk_records.append(chunk)

        await self.db.flush()

        # Embed in batches
        client = get_embedding_client()
        texts = [c.content for c in chunk_records]
        vectors = await client.embed_texts(texts, input_type="document")

        for chunk, vector in zip(chunk_records, vectors):
            self.db.add(DocumentEmbedding(
                tenant_id=self.tenant_id,
                chunk_id=chunk.id,
                embedding=vector,
                is_active=True,
            ))

        doc.status = "ready"
        doc.chunk_count = len(chunk_records)
        await self.db.flush()

        log.info("document_embedder.done",
                 document_id=str(document_id),
                 chunks=len(chunk_records))
        return {"chunks_created": len(chunk_records), "chunks_embedded": len(chunk_records)}

    async def _read_text(self, doc: Document) -> str:
        """
        Read plain text from storage_path.
        For pdf/docx, the Celery task pre-extracts and writes a .txt sidecar file.
        """
        import os
        path = doc.storage_path
        # For non-text types a sidecar .txt file is written by the extraction task
        if doc.file_type not in ("txt", "md", "markdown"):
            path = path.rsplit(".", 1)[0] + ".txt"
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as exc:
            log.error("document_embedder.read_error",
                      document_id=str(doc.id), path=path, error=str(exc))
            return ""


def _chunk_text(
    text: str,
) -> list[tuple[str, int | None, str | None]]:
    """
    Split text into (content, page_number, section_title) tuples.
    Page numbers and section titles are None for plain-text sources.
    """
    # Split on paragraph boundaries first
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= HARD_CHAR_LIMIT:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            # If para itself is too large, hard-split
            if len(para) > HARD_CHAR_LIMIT:
                for i in range(0, len(para), HARD_CHAR_LIMIT - CHUNK_OVERLAP):
                    sub = para[i : i + HARD_CHAR_LIMIT]
                    if sub.strip():
                        chunks.append(sub.strip())
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return [(chunk, None, None) for chunk in chunks if chunk.strip()]
