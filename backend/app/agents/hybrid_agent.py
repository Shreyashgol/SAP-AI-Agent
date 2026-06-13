"""
Hybrid Agent — merges a structured data answer with document context.

Spec: AG-011, HY-001, HY-002, HY-003
  - HY-001: Runs after response_formatter has a data answer (answer_text populated)
  - HY-002: Performs a parallel document chunk search using the same question
  - HY-003: If relevant chunks found (similarity >= 0.55), asks Claude to blend
            the data answer with the policy/document context into a single narrative
  - HY-004: If no relevant chunks found, passes through the data answer unchanged

Use case examples:
  "What is our DSO and what does the credit policy say about it?"
  "Show revenue by region and summarise any targets from the board report."

The agent short-circuits gracefully when:
  - No documents are uploaded / embedded for the tenant
  - No chunks match the query above the similarity threshold
  - The document context would not add value (data-only answer is sufficient)

Model: default (Sonnet) — blending requires reasoning quality.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_BLEND_SYSTEM = """\
You are an enterprise analytics assistant. You have two sources of information:
1. A structured data analysis answer (from the business database)
2. Relevant excerpts from company documents (policies, reports, guidelines)

Synthesise these into a single, coherent response that:
- Leads with the data finding
- Adds relevant policy or context from the documents where it illuminates the data
- Cites the document source inline using [Doc N] notation
- Keeps the total response to 3-5 sentences
- Does not repeat the same information twice

If the document context does not add meaningful value, return the data answer unchanged.
Output: plain prose only.
"""

_MIN_DOC_SIMILARITY = 0.55
_MAX_DOC_CHUNKS = 3


class HybridAgent(BaseAgent):
    name = "hybrid_agent"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        # The data answer is already in state from response_formatter
        data_answer = state.get("answer_text") or ""
        question = state.get("enriched_question") or state["question"]
        tenant_id = state["tenant_id"]

        # Search for relevant document chunks
        chunks = []
        try:
            from app.db.session import AsyncSessionLocal
            from app.services.embedding.vector_search import VectorSearchService
            async with AsyncSessionLocal() as db:
                search = VectorSearchService(db, tenant_id)
                chunks = await search.find_document_chunks(
                    query=question,
                    top_k=_MAX_DOC_CHUNKS,
                    min_similarity=_MIN_DOC_SIMILARITY,
                )
        except Exception as exc:
            self._log.warning("hybrid_agent.doc_search_fail", exc=str(exc))

        if not chunks:
            # No documents to blend — return data answer as-is
            self._log.info("hybrid_agent.no_docs_found")
            return {}  # empty dict = no state changes, existing answer preserved

        # Build document context block
        doc_parts = []
        lineage_chunks = []
        for i, chunk in enumerate(chunks, start=1):
            doc_parts.append(f"[Doc {i}]\n{chunk.content[:1200]}")
            lineage_chunks.append({
                "label": f"Doc {i}",
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "similarity": round(chunk.similarity, 4),
            })

        doc_context = "\n\n---\n\n".join(doc_parts)
        user_msg = (
            f"Data answer: {data_answer}\n\n"
            f"Question: {question}\n\n"
            f"Document excerpts:\n\n{doc_context}"
        )

        blended = await self._call_llm(
            system=_BLEND_SYSTEM,
            user=user_msg,
            model=self._default_model,
            max_tokens=768,
        )
        blended = blended.strip()

        # Merge document sources into lineage
        existing_lineage = dict(state.get("lineage") or {})
        existing_lineage["hybrid_docs"] = lineage_chunks

        self._log.info(
            "hybrid_agent.blended",
            doc_chunks=len(chunks),
            answer_len=len(blended),
        )

        return {
            "answer_text": blended,
            "lineage": existing_lineage,
        }
