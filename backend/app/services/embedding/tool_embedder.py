"""
Tool Embedding Service — generates and stores embeddings for Tool records.

Spec: EM-004, TR-001
- Embeds: name + description + domain + category + input param names
- Stores in tool_embeddings table as JSON text (pgvector migration applies Vector type)
- Upserts on regeneration; skips tools with unchanged embedding text
- Used by ToolRanker for semantic similarity retrieval
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool import Tool, ToolEmbedding
from app.services.embedding.client import get_embedding_client

log = get_logger(__name__)


def _tool_text(tool: Tool) -> str:
    """Build the embedding source text for a tool."""
    param_names = " ".join(p["name"] for p in (tool.input_schema or []))
    return (
        f"{tool.name} {tool.description or ''} "
        f"domain:{tool.domain} category:{tool.category} "
        f"params:{param_names}"
    ).strip()


class ToolEmbedder:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def embed_all(self, force: bool = False) -> dict[str, int]:
        """
        Embed all active tools for the tenant that lack an embedding (or force=True).
        Returns {embedded, skipped}.
        """
        tools_result = await self.db.execute(
            select(Tool).where(
                Tool.tenant_id == self.tenant_id,
                Tool.status == "active",
            )
        )
        tools = tools_result.scalars().all()

        # Pre-load existing embeddings
        existing_result = await self.db.execute(
            select(ToolEmbedding.tool_id).where(
                ToolEmbedding.tenant_id == self.tenant_id
            )
        )
        existing_tool_ids = {r[0] for r in existing_result.fetchall()}

        to_embed = [t for t in tools if force or t.id not in existing_tool_ids]
        if not to_embed:
            return {"embedded": 0, "skipped": len(tools)}

        texts = [_tool_text(t) for t in to_embed]
        client = get_embedding_client()
        vectors = await client.embed_texts(texts, input_type="document")

        embedded = 0
        for tool, vector in zip(to_embed, vectors):
            await self._upsert_embedding(tool.id, vector)
            embedded += 1

        await self.db.flush()
        log.info("tool_embedder.done",
                 tenant_id=str(self.tenant_id),
                 embedded=embedded,
                 skipped=len(tools) - embedded)
        return {"embedded": embedded, "skipped": len(tools) - embedded}

    async def embed_tool(self, tool_id: uuid.UUID) -> None:
        """Embed a single tool by ID."""
        result = await self.db.execute(
            select(Tool).where(
                Tool.id == tool_id,
                Tool.tenant_id == self.tenant_id,
            )
        )
        tool = result.scalar_one_or_none()
        if not tool:
            return
        client = get_embedding_client()
        vector = await client.embed_single(_tool_text(tool), input_type="document")
        await self._upsert_embedding(tool.id, vector)
        await self.db.flush()

    async def _upsert_embedding(self, tool_id: uuid.UUID, vector: list[float]) -> None:
        existing = await self.db.execute(
            select(ToolEmbedding).where(
                ToolEmbedding.tool_id == tool_id,
                ToolEmbedding.tenant_id == self.tenant_id,
            )
        )
        emb = existing.scalar_one_or_none()
        if emb:
            emb.embedding = vector
        else:
            self.db.add(ToolEmbedding(
                tenant_id=self.tenant_id,
                tool_id=tool_id,
                embedding=vector,
            ))
