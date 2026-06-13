"""
Custom Prometheus metrics — business-level counters beyond the default
prometheus-fastapi-instrumentator request metrics.

Usage (call at module import time in agents / services):

    from app.services.monitoring.metrics import (
        llm_calls_total,
        llm_tokens_total,
        agent_errors_total,
        query_cache_hits_total,
    )

    llm_calls_total.labels(agent="intent_classifier", model="claude-haiku").inc()
    llm_tokens_total.labels(agent="intent_classifier", direction="input").inc(412)

All metrics are registered in the default Prometheus registry so they are
automatically scraped at /metrics (mounted by prometheus-fastapi-instrumentator).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# ── LLM usage ─────────────────────────────────────────────────────────────────

llm_calls_total = Counter(
    "llm_calls_total",
    "Total number of Claude API calls made",
    ["agent", "model"],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["agent", "direction"],  # direction: input | output
)

llm_retry_total = Counter(
    "llm_retry_total",
    "Number of LLM call retries (backoff circuit breaker)",
    ["agent", "status_code"],
)

# ── Agent pipeline ─────────────────────────────────────────────────────────────

agent_invocations_total = Counter(
    "agent_invocations_total",
    "Total agent node invocations",
    ["agent"],
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent invocation errors",
    ["agent"],
)

intent_classification_total = Counter(
    "intent_classification_total",
    "Questions classified by intent",
    ["intent"],
)

# ── Query execution ────────────────────────────────────────────────────────────

sql_executions_total = Counter(
    "sql_executions_total",
    "Total SQL queries executed against customer DBs",
    ["db_type"],  # mssql | hana
)

sql_execution_duration_seconds = Histogram(
    "sql_execution_duration_seconds",
    "SQL query round-trip duration",
    ["db_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── Cache ──────────────────────────────────────────────────────────────────────

query_cache_hits_total = Counter(
    "query_cache_hits_total",
    "Redis query result cache hits",
)

query_cache_misses_total = Counter(
    "query_cache_misses_total",
    "Redis query result cache misses",
)

# ── Document processing ────────────────────────────────────────────────────────

documents_uploaded_total = Counter(
    "documents_uploaded_total",
    "Documents uploaded",
    ["file_type"],
)

document_chunks_embedded_total = Counter(
    "document_chunks_embedded_total",
    "Document chunks embedded via Voyage-3",
)

# ── Alert pipeline ─────────────────────────────────────────────────────────────

alerts_triggered_total = Counter(
    "alerts_triggered_total",
    "Alert instances created",
    ["severity", "rule_type"],
)
