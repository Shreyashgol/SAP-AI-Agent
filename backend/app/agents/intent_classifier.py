"""
Intent Classifier Agent — maps natural-language questions to structured intent.

Spec: AG-003, IC-001, IC-002, IC-003

Outputs to state:
  - intent: Lookup | Aggregation | Trend | Comparative | RCA | Document | Hybrid | Web
  - detected_domain: finance | sales | purchasing | inventory | operations | None
  - confidence: 0.0–1.0

Fast model is used (Haiku) — target latency <200ms.

Synonym resolution from SynonymEngine runs before Claude classification.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.state import AgentState
from app.core.logging import get_logger

_INTENTS = {"Lookup", "Aggregation", "Trend", "Comparative", "RCA", "Document", "Hybrid", "Web"}
_DOMAINS = {"finance", "sales", "purchasing", "inventory", "operations"}

_SYSTEM = """\
You are an intent classifier for an enterprise analytics platform.
Given a business question, output ONLY valid JSON — no prose, no markdown.

Output format:
{
  "intent": "<Lookup|Aggregation|Trend|Comparative|RCA|Document|Hybrid|Web>",
  "domain": "<finance|sales|purchasing|inventory|operations|null>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>"
}

Intent definitions:
- Lookup:      Retrieve a specific record or value (e.g. "Show invoice #1234")
- Aggregation: SUM/COUNT/AVG over a set (e.g. "Total revenue this month")
- Trend:       Time-series or period-over-period (e.g. "Revenue trend last 6 months")
- Comparative: Compare two or more groups/periods (e.g. "Top 10 customers vs last year")
- RCA:         Root cause analysis (e.g. "Why did sales drop in March?")
- Document:    Query from uploaded documents/policies (e.g. "What is our payment policy?")
- Hybrid:      Combines a database query WITH company-document/policy knowledge in a
               single question — typically business data measured against a rule from
               an uploaded policy/guideline. Strong cues: "per our policy", "stated in
               our policy", "defined in our credit policy", "against our targets",
               "exceeding the limit in our policy", "past the payment terms in our policy".
               (e.g. "Which customers exceed the credit limit defined in our credit policy?",
                "Are any open invoices past the payment terms stated in our policy?")
- Web:         Needs current external/public information, not internal data
               (e.g. "Latest GST update", "Latest SAP B1 release", "industry benchmark")

domain: pick the closest match. Use null if genuinely cross-domain.
confidence: your confidence in the intent classification (not the answer).
"""


class IntentClassifierAgent(BaseAgent):
    name = "intent_classifier"

    async def _run(self, state: AgentState) -> dict:
        question = state["question"]

        # Fast synonym pre-resolution (if DB available)
        try:
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.db.session import AsyncSessionLocal
            from app.services.semantic.synonym_engine import SynonymEngine
            async with AsyncSessionLocal() as db:
                engine = SynonymEngine(db, state["tenant_id"])
                await engine._ensure_cache()
                terms = question.lower().split()
                resolved = [await engine.resolve(t) or t for t in terms]
                enriched = " ".join(resolved)
        except Exception:
            enriched = question

        # Prefer the context-enriched question if available (set by ContextAgent)
        effective_question = state.get("enriched_question") or question

        raw = await self._call_llm(
            system=_SYSTEM,
            user=f"Question: {effective_question}\nContext terms resolved: {enriched}",
        )

        parsed = self._extract_json(raw)
        if not parsed:
            self._log.warning("intent_classifier.parse_fail", raw=raw[:200])
            return {
                "intent": "Aggregation",
                "detected_domain": None,
                "confidence": 0.3,
                "fallback_used": True,
            }

        intent = parsed.get("intent", "Aggregation")
        if intent not in _INTENTS:
            intent = "Aggregation"

        domain = parsed.get("domain")
        if domain not in _DOMAINS:
            domain = None

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        reasoning = parsed.get("reasoning")
        reasoning = str(reasoning).strip() if reasoning else None

        self._log.info("intent_classifier.result",
                       intent=intent, domain=domain, confidence=confidence)
        return {
            "intent": intent,
            "detected_domain": domain,
            "confidence": confidence,
            "reasoning": reasoning,
        }
