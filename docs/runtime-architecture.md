# Chat Runtime Architecture

How a user question flows through the agentic runtime, mapped to the code.
All routing lives in `backend/app/agents/supervisor.py` (LangGraph).

```
User Question → POST /conversations/{id}/ask
      │
Auth / Tenant / Permission        deps.py (auth bypassed by design — default
      │                           user; tenant + RBAC checks still enforced)
      ▼
Context Agent                     context_agent.py — resolves pronouns/filters
      ▼                           from prior turns (Memory layer)
Router (Intent Classifier)        intent_classifier.py — Haiku, <200ms
      │
 ┌────┴─────┬──────────┬─────────┬──────────┐
 SQL        RAG        Analytics  Hybrid     Web
 │          │          │          │          │
 Lookup/    Document   RCA/Trend  Hybrid     Web
 Aggregation/
 Comparative
 │          │          │          │          │
 planner →  document_  planner →  planner →  web_search.py
 ranking →  rag.py     executor → executor →  (Anthropic server-side
 executor   (pgvector  rca_agent/ formatter →  web_search tool,
 │          top-k      trend_     hybrid_      citations attached)
 │          chunks)    agent      agent
 └──────────┴──────────┴──────────┴──────────┘
      ▼
Response Formatter → Claude       response_formatter.py
      ▼
Charts / Tables / Text            chart_hint + answer_data → frontend
```

## Intent → flow mapping

| Intent (classifier) | Reference name | Path | Terminal agent |
|---|---|---|---|
| Lookup / Aggregation / Comparative | SQL Query | planner → tool ranking → SQL validation → MSSQL | response_formatter |
| Document | RAG Query | pgvector chunk search → context build → Claude | document_rag |
| RCA / Trend | Analytics Query | planner → executor → investigation/aggregation | rca_agent / trend_agent |
| Hybrid | Hybrid Query | SQL path + document merge after formatting | hybrid_agent |
| Web | Web Query | Anthropic server-side web_search tool | web_search |

## Shared components

| Component | Implementation |
|---|---|
| Semantic retrieval (pgvector) | `services/embedding/vector_search.py` — entities, tools, documents |
| Tool registry + ranking | `tools` table + `services/tools/ranker.py` |
| SQL safety layer | `services/sql/validator.py` — sqlglot AST, `tsql` dialect, SELECT-only; `sql_executor.py` injects `TOP 1000` caps |
| Cache layer | Redis — `services/cache/query_cache.py`, rate limits, circuit breaker |
| Memory layer | `context_agent.py` + `services/conversation/manager.py` (filters, date ranges, conversation context) |
| Clarification | `clarification_agent.py` — asks when required params are missing |
| Error handling | `error_handler` node — every stage routes errors to a graceful answer |

## Web Search Agent notes (added 2026-06-13)

- Uses Anthropic's **server-side** `web_search_20260209` tool — Claude writes
  the queries, Anthropic executes them and returns results with citations.
  No scraping code, no user-supplied URLs (NFR-SEC13), max 5 searches/question.
- Citations are returned in `answer_data.sources` / `lineage.sources`
  (`[{url, title}]`).
- Failure never blocks: if search errors, the user gets "External web data is
  unavailable…" and the platform keeps answering internal-data questions.
- Web search is billed per search by Anthropic in addition to tokens.
- Deep dive on the security model (why the spec's domain whitelist is not
  enforced, residual risks, hardening path) and billing anatomy:
  see `web-search-security-and-billing.md`.
