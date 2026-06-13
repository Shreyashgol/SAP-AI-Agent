"""
Document RAG Agent — retrieves relevant document chunks and synthesises an answer.

Spec: AG-008, DR-001, DR-002, DR-003, DR-004
  - DR-001: Embed the (enriched) question with Voyage-3 query embedding
  - DR-002: Retrieve top-5 chunks via VectorSearchService (min_similarity=0.55)
  - DR-003: Build a grounded prompt with retrieved context; ask Claude to answer
  - DR-004: Lineage includes document_ids, chunk_ids, similarity scores
  - DR-005: If no chunks found above threshold, return a clear "not in documents" message

Model: default (Sonnet) — documents may be long; we need higher reasoning quality.
Max context sent to Claude: top-5 chunks × 2048 chars = ~10 KB (well within context).

Hybrid intent:
  For Hybrid intent, the orchestrator can call this agent AND the data pipeline.
  This agent handles the Document portion; the final formatter merges both.

Citation format:
  Each chunk is labelled [Doc N] so the LLM can cite sources naturally.
  The lineage returned maps N → {document_id, chunk_id, page, section}.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_RAG_SYSTEM = """\
You are an enterprise knowledge assistant. Answer the user's question using ONLY
the provided document excerpts. Each excerpt is labelled [Doc N].

Rules:
- Cite your sources using [Doc N] inline (e.g. "Payment terms are net 30 [Doc 1].")
- If the documents do not contain enough information to answer, say so clearly
- Do not use prior knowledge outside the provided excerpts
- Be concise — 2-4 sentences unless the question requires a detailed list
- If multiple documents agree, synthesise them; if they conflict, mention the conflict
- Never make up numbers, names, or dates not present in the excerpts

Output: plain prose answer with inline citations.
"""

_MAX_CHUNKS = 5
_MIN_SIMILARITY = 0.55  # lower than tool search — documents are more varied
_MAX_CHUNK_CHARS = 1800  # truncate long chunks before sending to Claude


class DocumentRAGAgent(BaseAgent):
    name = "document_rag"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        question = state.get("enriched_question") or state["question"]
        tenant_id = state["tenant_id"]

        from app.db.session import AsyncSessionLocal
        from app.services.embedding.vector_search import VectorSearchService

        async with AsyncSessionLocal() as db:
            search = VectorSearchService(db, tenant_id)
            chunks = await search.find_document_chunks(
                query=question,
                top_k=_MAX_CHUNKS,
                min_similarity=_MIN_SIMILARITY,
            )

        if not chunks:
            self._log.info("document_rag.no_chunks", question=question[:80])
            return {
                "answer_text": (
                    "I could not find relevant information in your uploaded documents "
                    "to answer this question. Please check that the relevant documents "
                    "have been uploaded and processed, or rephrase your question."
                ),
                "answer_data": {"type": "document", "chunks_found": 0},
                "chart_hint": "table",
                "follow_up_questions": [],
                "confidence_score": 0.1,
                "lineage": {"type": "document", "chunks": []},
            }

        # Build context block
        context_parts: list[str] = []
        lineage_chunks: list[dict] = []

        for i, chunk in enumerate(chunks, start=1):
            content = chunk.content[:_MAX_CHUNK_CHARS]
            label = f"[Doc {i}]"
            meta_parts = []
            if chunk.section_title:
                meta_parts.append(f"section: {chunk.section_title}")
            if chunk.page_number:
                meta_parts.append(f"page {chunk.page_number}")
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            context_parts.append(f"{label}{meta}\n{content}")
            lineage_chunks.append({
                "label": f"Doc {i}",
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "similarity": round(chunk.similarity, 4),
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
            })

        context_block = "\n\n---\n\n".join(context_parts)
        user_msg = f"Question: {question}\n\nDocument excerpts:\n\n{context_block}"

        answer = await self._call_llm(
            system=_RAG_SYSTEM,
            user=user_msg,
            model=self._default_model,  # Sonnet for document reasoning
            max_tokens=1024,
        )

        # Confidence based on best similarity score
        best_sim = chunks[0].similarity if chunks else 0.0
        confidence = round(0.3 + 0.7 * best_sim, 3)

        lineage = {
            "type": "document",
            "chunks": lineage_chunks,
            "chunks_found": len(chunks),
            "turn_id": str(state.get("turn_id", "")),
        }

        follow_ups = await self._generate_follow_ups(question)

        self._log.info(
            "document_rag.done",
            chunks_used=len(chunks),
            best_similarity=best_sim,
            confidence=confidence,
        )

        return {
            "answer_text": answer,
            "answer_data": {
                "type": "document",
                "chunks_found": len(chunks),
                "sources": lineage_chunks,
            },
            "chart_hint": "table",
            "follow_up_questions": follow_ups,
            "confidence_score": confidence,
            "lineage": lineage,
        }

    async def _generate_follow_ups(self, question: str) -> list[str]:
        system = (
            "Suggest 3 natural follow-up questions someone might ask after getting "
            "a document-based answer. Return ONLY a JSON array of 3 strings."
        )
        try:
            import json
            raw = await self._call_llm(system=system, user=f"Question: {question}", max_tokens=200)
            raw = raw.strip()
            if raw.startswith("["):
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(q) for q in parsed[:3]]
        except Exception:
            pass
        return [
            "Can you find more details on this topic?",
            "Which document covers this in more depth?",
            "Are there any exceptions or conditions mentioned?",
        ]
