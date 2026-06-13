"""
Web Search Agent — external data enrichment (spec Agent 12 / Agent 15).

Handles Web-intent questions ("Latest GST update", "Latest SAP B1 release",
"How does our growth compare to industry?") via Anthropic's server-side
web_search tool: Claude generates the queries, Anthropic executes them and
returns results with citations. No scraping infrastructure runs here and no
user-supplied URLs are ever fetched (NFR-SEC13).

Failure handling per spec: web search is supplementary — if search fails the
agent returns a graceful "external data unavailable" answer instead of
blocking the conversation.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_MAX_SEARCHES = 5         # max server-side searches per question
_MAX_CONTINUATIONS = 3    # pause_turn resumptions before giving up

_WEB_SYSTEM = """You are a web research assistant inside an enterprise business-intelligence platform for SAP Business One users.

Answer the user's question using web search. Rules:
- Use the web_search tool for anything time-sensitive (news, releases, rates, regulations) — do not answer from memory.
- Be concise and factual. Lead with the direct answer, then supporting detail.
- External data is supplementary context for business decisions — clearly attribute facts to their sources.
- If results conflict, say so and prefer official/primary sources."""

_UNAVAILABLE_TEXT = (
    "External web data is unavailable right now. "
    "I can still answer questions about your internal business data."
)


class WebSearchAgent(BaseAgent):
    """Terminal node for Web-intent questions."""

    name = "web_search"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        question = state.get("enriched_question") or state["question"]

        try:
            answer_text, sources = await self._search(question)
        except Exception as exc:
            # Spec: web failures must not block the primary answer path
            self._log.warning("web_search.unavailable", exc=str(exc))
            return {
                "answer_text": _UNAVAILABLE_TEXT,
                "answer_data": {"type": "web", "sources": [], "available": False},
                "chart_hint": "table",
                "follow_up_questions": [],
                "confidence_score": 0.0,
                "lineage": {"type": "web", "sources": []},
                "fallback_used": True,
            }

        self._log.info(
            "web_search.done",
            question=question[:80],
            sources=len(sources),
        )
        return {
            "answer_text": answer_text or _UNAVAILABLE_TEXT,
            "answer_data": {"type": "web", "sources": sources, "available": True},
            "chart_hint": "table",
            "follow_up_questions": [],
            "confidence_score": 0.7 if sources else 0.3,
            "lineage": {
                "type": "web",
                "sources": sources,
                "turn_id": str(state.get("turn_id", "")),
            },
        }

    async def _search(self, question: str) -> tuple[str, list[dict[str, Any]]]:
        """Run the server-side web search loop; returns (answer, cited sources)."""
        tools = [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": _MAX_SEARCHES,
            }
        ]
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]

        response = await self._claude.messages.create(
            model=self._default_model,
            max_tokens=2048,
            system=_WEB_SYSTEM,
            messages=messages,
            tools=tools,
        )

        # The server-side tool loop may pause; re-send to let it resume
        for _ in range(_MAX_CONTINUATIONS):
            if response.stop_reason != "pause_turn":
                break
            messages = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": response.content},
            ]
            response = await self._claude.messages.create(
                model=self._default_model,
                max_tokens=2048,
                system=_WEB_SYSTEM,
                messages=messages,
                tools=tools,
            )

        text_parts: list[str] = []
        sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for block in response.content:
            if block.type != "text":
                continue
            text_parts.append(block.text)
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", None)
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(
                        {"url": url, "title": getattr(citation, "title", None)}
                    )

        return "".join(text_parts).strip(), sources
