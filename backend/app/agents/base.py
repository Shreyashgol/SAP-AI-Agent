"""
Base agent class — all graph nodes inherit from this.

Provides:
  - Structured logging with agent name + turn_id
  - State mutation helpers (mark self as invoked, set error)
  - Claude client factory (model pre-wired)
  - Safe JSON extraction from LLM responses
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import anthropic

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.core.settings import get_settings


class BaseAgent:
    """Abstract base for all graph node agents."""

    name: str = "base"  # overridden by each subclass

    def __init__(self) -> None:
        settings = get_settings()
        self._log = get_logger(f"agent.{self.name}")
        self._claude = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
        )
        self._default_model = settings.anthropic_default_model
        self._fast_model = settings.anthropic_fast_model

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        """LangGraph node entry point. Subclasses implement _run()."""
        # Short-circuit on upstream error
        if state.get("error"):
            return {}

        self._log.info(
            "agent.start",
            agent=self.name,
            turn_id=str(state.get("turn_id", "")),
            question=state.get("question", "")[:80],
        )
        try:
            updates = await self._run(state)
            invoked = list(state.get("agents_invoked", []))
            invoked.append(self.name)
            updates["agents_invoked"] = invoked
            return updates
        except Exception as exc:
            self._log.error("agent.error", agent=self.name, exc=str(exc))
            return {"error": f"{self.name}: {exc}", "agents_invoked": state.get("agents_invoked", []) + [self.name]}

    async def _run(self, state: AgentState) -> dict[str, Any]:
        raise NotImplementedError

    async def _call_llm(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Call Claude with exponential-backoff retry on transient errors.

        Retries: up to 3 attempts on HTTP 429 (rate limit) or 5xx (server error).
        Raises immediately on 4xx (except 429) — those are caller errors.
        Backoff: 1 s, 2 s, 4 s between attempts.
        """
        _max_retries = 3
        _base_delay = 1.0

        last_exc: Exception | None = None
        for attempt in range(_max_retries):
            try:
                response = await self._claude.messages.create(
                    model=model or self._fast_model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return "".join(block.text for block in response.content if block.type == "text")
            except anthropic.APIStatusError as exc:
                status = exc.status_code
                retryable = status == 429 or status >= 500
                if not retryable or attempt == _max_retries - 1:
                    raise
                delay = _base_delay * (2 ** attempt)
                self._log.warning(
                    "llm.retry",
                    attempt=attempt + 1,
                    status=status,
                    delay=delay,
                )
                last_exc = exc
                await asyncio.sleep(delay)
            except anthropic.APIConnectionError as exc:
                if attempt == _max_retries - 1:
                    raise
                delay = _base_delay * (2 ** attempt)
                self._log.warning(
                    "llm.retry_connection",
                    attempt=attempt + 1,
                    delay=delay,
                )
                last_exc = exc
                await asyncio.sleep(delay)

        raise RuntimeError(f"LLM call failed after {_max_retries} attempts") from last_exc

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Extract JSON from LLM output, tolerating markdown fences."""
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
