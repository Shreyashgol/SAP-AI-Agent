"""
Clarification Agent — produces a user-facing question when required parameters
are missing from the query plan.

Spec: AG-007, CL-001, CL-002
  - CL-001: Triggered when sql_executor signals needs_clarification=True
  - CL-002: Uses Claude to write a natural-language question asking for
            the specific missing parameters in business (not technical) terms
  - CL-003: Sets answer_text to the clarification question and marks the turn

The conversation endpoint returns this as a normal AskResponse with
has_clarification=True so the frontend can render it as a prompt card
rather than a data answer.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

_CLARIFICATION_SYSTEM = """\
You are an enterprise analytics assistant. A user asked a business question but
you need more information to answer it precisely.

Given the original question and the list of missing parameters (in technical form),
write a single, friendly, business-oriented clarifying question in plain English.

Rules:
- Ask for ALL missing parameters in ONE question
- Use business language, not SQL/technical terms
- Be concise — one or two sentences maximum
- Do not mention tools, parameters, schemas, or SQL
- Examples of good clarifications:
  "Which date range would you like to look at?"
  "Which customer or time period should I focus on?"
  "Could you specify the date range and the product category you're interested in?"

Output ONLY the clarifying question — no preamble, no JSON.
"""


class ClarificationAgent(BaseAgent):
    name = "clarification_agent"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        question = state.get("enriched_question") or state["question"]
        missing: list[str] = state.get("missing_params") or []
        tool = state.get("selected_tool") or {}

        # Humanise the param names for the Claude prompt
        param_labels = _humanise_params(missing, tool.get("input_schema") or [])

        user_msg = (
            f"Original question: {question}\n"
            f"Missing information needed: {', '.join(param_labels)}"
        )

        try:
            clarification = await self._call_llm(
                system=_CLARIFICATION_SYSTEM,
                user=user_msg,
                max_tokens=128,
            )
            clarification = clarification.strip().strip('"').strip("'")
        except Exception as exc:
            self._log.warning("clarification_agent.llm_fail", exc=str(exc))
            clarification = (
                f"To answer your question, I need a bit more detail. "
                f"Could you specify: {', '.join(param_labels)}?"
            )

        self._log.info("clarification_agent.produced", missing=missing)

        return {
            "clarification_question": clarification,
            "answer_text": clarification,
            "answer_data": {
                "type": "clarification",
                "missing_params": missing,
                "clarification_question": clarification,
            },
            "chart_hint": "table",
            "follow_up_questions": [],
            "confidence_score": None,
            "lineage": None,
        }


def _humanise_params(
    missing: list[str], schema: list[dict]
) -> list[str]:
    """Convert snake_case param names to human-readable labels using schema descriptions."""
    schema_map = {p["name"]: p.get("description", "") for p in schema}
    result = []
    for name in missing:
        desc = schema_map.get(name, "")
        if desc and len(desc) < 60:
            result.append(desc)
        else:
            # snake_case → "Start Date"
            result.append(name.replace("_", " ").title())
    return result
