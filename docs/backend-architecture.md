# Backend Architecture — Full Working Reference

A program-level guide to how the backend is built and how the pieces call each
other, covering **both flows**:

- **Onboarding** — connect a database → discover its schema → build the
  semantic layer, tools, and embeddings (so the chatbot "understands" the DB).
- **Runtime** — a user question → multi-agent pipeline → SQL/RAG/web answer.

Companion docs: `data_layer_guide.md` (what's stored where & why),
`intelligence-pipeline.md` (the post-discovery pipeline),
`runtime-architecture.md` (the chat intents), `mssql-connection-guide.md`.

---

## 1. The big picture — two processes, shared infrastructure

The backend runs as **two separate processes from the same image**
(`backend/Dockerfile`, `docker-compose.yml`):

```
                ┌──────────────────────────────────────────────┐
   Browser ───► │  API process   (uvicorn app.main:app)        │
   (frontend)   │  - FastAPI HTTP endpoints                    │
                │  - runs the LangGraph agent pipeline inline  │
                └───────┬───────────────┬──────────────────────┘
                        │               │ enqueues background jobs
                        │               ▼
                        │       ┌────────────────────────────────┐
                        │       │ Worker process (Celery)        │
                        │       │ - discovery crawl              │
                        │       │ - semantic / tools / embeddings│
                        │       │ - reports, monitoring          │
                        │       └───────┬────────────────────────┘
                        │               │
        ┌───────────────┼───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼
  PostgreSQL 16    Redis 7         (Celery broker    Local embedding   User's
  + pgvector       cache/queues/    = Redis)         model (bge-large) MSSQL DB
  (platform state) circuit-breaker                   in-process        (SAP B1)
```

| Component | Role | Where configured |
|---|---|---|
| **API process** | Serves HTTP, runs the chat agent graph synchronously inside the request | `app/main.py`, compose `api` service |
| **Worker process** | Runs long jobs (discovery, embeddings…) off the request path | `app/worker/celery_app.py`, compose `worker` service |
| **Beat process** | Cron scheduler (nightly tool-weight recalc) | compose `beat` service |
| **PostgreSQL + pgvector** | All platform state + vector search | compose `postgres` |
| **Redis** | Celery broker/result backend, query cache, rate limits, circuit breaker, discovery progress | compose `redis` |
| **User's MSSQL/HANA DB** | The customer's SAP B1 data — read-only, never copied wholesale | `connections` table |

**Key idea:** the customer's business data stays in *their* database. Postgres
only stores *metadata about it* plus all application state.

---

## 2. Process startup — what boots, in order

### API process (`app/main.py`)
1. `create_app()` builds the FastAPI app.
2. `configure_logging()` (`core/logging.py`) wires **structlog → JSON stdout**.
3. Middleware stack added (outermost last): `RequestIDMiddleware` →
   `RateLimitMiddleware` → `SecurityHeadersMiddleware` → CORS
   (`app/middleware/*`).
4. Exception handlers registered (`core/exceptions.py`) — every error becomes a
   uniform JSON envelope.
5. `api_router` mounted at `/api/v1` (`app/api/v1/router.py`).
6. **Lifespan startup** runs `core/startup.validate_all()` — pings Redis,
   checks storage paths, validates the AES key; **exits the process** if any
   fail (fail-fast).

### Worker process (`app/worker/celery_app.py`)
- Creates the `Celery` app, broker/back-end = Redis.
- `include=[...]` registers every task module under `app/worker/tasks/`.
- `beat_schedule` defines the nightly `tools.recalculate_weights` cron.
- Tasks declare `queue="default"` / `queue="discovery"`; the worker is started
  with `-Q default,discovery` so both are consumed.

---

## 3. Directory map — what lives where

```
backend/app/
├── main.py              API app factory + lifespan (entry point)
├── core/                Cross-cutting infrastructure (no business logic)
│   ├── settings.py      Pydantic settings from env/.env (DB url, keys, models)
│   ├── logging.py       structlog JSON logging setup
│   ├── deps.py          get_current_user (auth bypassed → default user), RBAC
│   ├── redis.py         Shared async Redis client + key helpers
│   ├── encryption.py    AES-256-GCM encrypt/decrypt (credential vault)
│   ├── security.py      Password hashing, JWT encode/decode (login removed)
│   ├── exceptions.py    AppError types + FastAPI error handlers
│   └── startup.py       Fail-fast startup validation
├── db/session.py        SQLAlchemy async engine + Base + get_db() session dep
├── models/              SQLAlchemy ORM tables (one module per domain)
│   ├── base.py          UUID/Timestamp mixins + VECTOR_TYPE (pgvector(1024))
│   ├── tenant.py user.py connection.py metadata.py semantic.py
│   ├── knowledge_graph.py tool.py conversation.py document.py
│   ├── dashboard.py report.py feedback.py analytics.py audit.py
├── schemas/             Pydantic request/response models (API contracts)
├── api/
│   ├── deps.py          get_current_tenant (tenant_id + user from request)
│   └── v1/
│       ├── router.py    Mounts every endpoint router
│       └── endpoints/    One module per resource (HTTP layer only)
├── agents/              The runtime LangGraph pipeline (runs in API process)
│   ├── supervisor.py    Graph wiring + routing + run_question() entry
│   ├── state.py         AgentState TypedDict (shared between nodes)
│   ├── base.py          BaseAgent: Claude client, retry, JSON parse, logging
│   ├── context_agent.py intent_classifier.py query_planner.py
│   ├── sql_executor.py response_formatter.py clarification_agent.py
│   ├── document_rag.py rca_agent.py trend_agent.py hybrid_agent.py
│   └── web_search.py
├── services/            Business logic (called by endpoints AND agents AND tasks)
│   ├── connections/     connector.py (HANA/MSSQL drivers), connection_service,
│   │                    circuit_breaker
│   ├── discovery/       crawler.py (schema crawl), pii_detector
│   ├── semantic/        sap_b1_pack, pack_loader, mssql_fingerprint, ai_mapper,
│   │                    kpi_library, synonym_engine, rules_engine
│   ├── tools/           sap_b1_tools (50 pre-built), pack_loader, generator,
│   │                    ranker, custom_builder
│   ├── embedding/       client (bge-large), tool/semantic/document embedders,
│   │                    vector_search (pgvector cosine retrieval)
│   ├── knowledge_graph/ builder, traversal (BFS join-path finder)
│   ├── sql/             validator.py (sqlglot SELECT-only, tsql dialect)
│   ├── conversation/    manager.py (conversations, turns, context memory)
│   ├── cache/           query_cache.py (Redis answer cache)
│   ├── auth/            auth_service, rbac_service (tenant/role bootstrap)
│   ├── analytics/       anomaly.py
│   ├── monitoring/      metrics.py
│   └── audit_service.py Audit-log writer
├── worker/
│   ├── celery_app.py    Celery config + task registry + beat schedule
│   ├── db.py            AsyncSessionLocal for tasks (own engine)
│   └── tasks/           discovery, semantic, knowledge_graph, tools,
│                        embedding, document, report, monitoring
├── middleware/          request_id, rate_limit, security_headers
└── alembic/             DB migrations (0001 schema … 0004 vector resize)
```

### The layering rule (who may call whom)

```
endpoints/  ──►  services/  ──►  models/ + db/        (HTTP path)
agents/     ──►  services/  ──►  models/ + db/        (runtime path)
worker/tasks/ ─► services/  ──►  models/ + db/        (background path)
            core/  and  schemas/  are used by everyone
```

- **Endpoints, agents, and tasks are three different "front doors"** to the
  same `services/`. Endpoints handle HTTP; agents handle one graph node; tasks
  handle one background job. None of them contain business logic themselves —
  they delegate to `services/`.
- `services/` is the only layer that touches `models/` + the DB and external
  systems (the user's MSSQL DB, Claude, the embedding model).
- `core/` and `schemas/` are leaf utilities imported everywhere.

---

## 4. ONBOARDING flow — program level

Goal: turn a freshly connected database into a queryable knowledge base.
Triggered from the frontend onboarding wizard.

### Step 1 — Create the connection (synchronous, API process)
```
POST /api/v1/connections
  → endpoints/connections.py: create_connection()
      → services/connections/connection_service.py: ConnectionService.create()
          → core/encryption.py: encrypt()        # password AES-256-GCM
          → models/connection.py: Connection      # row written, blob in
                                                   #   vault_credential_path
```
The raw password is double-encrypted (per-field + whole blob) and never
returned by any endpoint.

`POST /connections/{id}/test` →
`ConnectionService.test()` → `connector.get_connector()` →
`MSSQLConnector.test_connection()` (pyodbc) → records `last_health_status`.

### Step 2 — Discovery (asynchronous, Worker process)
```
POST /api/v1/discovery/{connection_id}/start
  → endpoints/discovery.py: trigger_discovery()
      → run_full_discovery.delay(...)            # hands off to Redis queue
```
The worker picks it up:
```
worker/tasks/discovery.py: run_full_discovery
  → _execute_discovery()
      → load Connection, decrypt creds
      → connector.build_mssql_conn_str() → pyodbc.connect()   # to user's DB
      → services/discovery/crawler.py: SchemaCrawler.run_full()
          → reads INFORMATION_SCHEMA (tables, columns, FKs)
          → services/discovery/pii_detector.py  (flags PII columns)
          → writes models/metadata.py: MetadataTable / Column / Relation
      → writes discovery progress to Redis (polled by the wizard)
      → ON SUCCESS: build_post_discovery_pipeline(...).delay()
```

### Step 3 — The intelligence pipeline (asynchronous, Worker) 
`build_post_discovery_pipeline()` (in `worker/tasks/discovery.py`) enqueues a
Celery chain. Full detail in `intelligence-pipeline.md`; the call graph:

```
Foundation:
  semantic.apply_pack          → services/semantic/mssql_fingerprint.py  (detect ERP)
                                → services/semantic/pack_loader.py        (apply sap_b1 pack)
                                → writes semantic_entities / attributes / rules
  embedding.embed_entities     → services/embedding/semantic_embedder.py
                                → services/embedding/client.py (bge-large → 1024-dim)
                                → writes semantic_entity_embeddings (pgvector)

Phase B (parallel Celery group):
  semantic.run_ai_mapping      → services/semantic/ai_mapper.py  (Claude maps leftover tables)
  semantic.seed_kpis           → services/semantic/kpi_library.py
   → tools.generate_kpi_tools  → services/tools/generator.py    (one tool per KPI)
  tools.apply_tool_pack        → services/tools/pack_loader.py + sap_b1_tools.py (50 tools)
   → tools.generate_for_connection → services/tools/generator.py (entity summary tools)

Phase C (join):
  embedding.embed_entities  +  embedding.embed_tools
   → services/embedding/tool_embedder.py → writes tool_embeddings (pgvector, HNSW)
```

**After this, the chatbot is usable.** The knowledge graph is excluded by
default (MVP); pass `include_knowledge_graph=True` or call
`POST /knowledge-graph/build` to add it.

What's deterministic vs LLM:
- **No Claude key needed:** entity pack, KPI library, tool pack, tool/entity
  generation, embeddings (local model).
- **Claude key needed:** only `ai_mapper.py` (maps non-standard tables) and the
  chat runtime.

---

## 5. RUNTIME flow — program level

Goal: answer a natural-language question. Runs **synchronously inside the API
process** (no Celery) so the user gets a direct response.

### Entry: the ask endpoint
```
POST /api/v1/conversations/{id}/ask
  → endpoints/conversations.py: ask()
      → core/deps.py: get_current_user()         # default user (login removed)
      → api/deps.py: get_current_tenant()         # tenant_id for the request
      → services/conversation/manager.py: ConversationManager.get_conversation()
      → builds initial AgentState dict (question, tenant_id, turn_id, ...)
      → agents/supervisor.py: run_question(initial_state)   ◄── enters the graph
      → ConversationManager.save_turn(...)        # persists the answer
      → returns AskResponse
```

### The graph (`agents/supervisor.py` + `agents/state.py`)
`run_question()` invokes a compiled **LangGraph** `StateGraph`. Every node is a
`BaseAgent` subclass that reads/writes the shared `AgentState` TypedDict. Each
node logs `agent.start` (great for debugging — see "Observability").

```
context_agent           resolve pronouns/filters from prior turns (Memory)
   ▼                    → ConversationManager.get_context()
intent_classifier       classify intent (Haiku) → Lookup|Aggregation|Trend|
   │                      Comparative|RCA|Document|Hybrid|Web
   ├─ Document ─► document_rag        → vector_search.find_document_chunks() → Claude
   ├─ Web ──────► web_search          → Anthropic server-side web_search tool
   └─ everything else ─► query_planner
                          → services/embedding/vector_search.py: find_tools()
                              (embed question → cosine over tool_embeddings)
                          → services/tools/ranker.py  (rank candidates)
                          → resolve params; if required params missing:
                          ▼
                     sql_executor       (only if a tool was selected & params ok)
                          → services/sql/validator.py  (SELECT-only, tsql)
                          → services/connections/connector.py: get_connector()
                          → ConnectionService._load_credentials()  (decrypt)
                          → MSSQLConnector.execute_query()  ◄── hits user's DB
                          ├─ needs_clarification ─► clarification_agent ─► END
                          ├─ RCA ─► rca_agent ─► END
                          ├─ Trend ─► trend_agent ─► END
                          └─ ok ─► response_formatter
                                     → Claude turns rows into narrative + chart
                                     ├─ Hybrid ─► hybrid_agent (merges docs) ─► END
                                     └─ END
   (any node error) ─► error_handler ─► END   (graceful "I was unable to…")
```

### What each runtime node does
| Node (`agents/…`) | Calls into | Produces |
|---|---|---|
| `context_agent` | `conversation/manager` | `enriched_question` |
| `intent_classifier` | Claude (Haiku) | `intent`, `detected_domain`, `confidence` |
| `query_planner` | `embedding/vector_search`, `tools/ranker` | `selected_tool`, `resolved_params`, or `needs_clarification` |
| `sql_executor` | `sql/validator`, `connections/connector` | `query_result` (rows) |
| `response_formatter` | Claude (Sonnet) | `answer_text`, `chart_hint`, `answer_data` |
| `clarification_agent` | Claude | `clarification_question` |
| `rca_agent` / `trend_agent` | Claude + prior data | analytical narrative |
| `document_rag` | `embedding/vector_search` + Claude | answer from uploaded docs |
| `web_search` | Anthropic web_search tool | answer + citations |

The final `AgentState` flows back to `ask()`, which calls
`ConversationManager.save_turn()` → writes `conversation_turns` (question,
answer, SQL, lineage, agents_invoked, confidence) for history and the UI.

---

## 6. Cross-cutting concerns (used by every layer)

| Concern | Module | How it's used |
|---|---|---|
| **Settings** | `core/settings.py` | One `get_settings()` (cached) reads env/.env: DB url, Redis url, `anthropic_*` models/key, `sql_echo`, encryption key |
| **Auth / tenant** | `core/deps.py`, `api/deps.py` | Login is removed → `get_current_user()` returns the first active user (auto-bootstraps a default tenant+admin on a fresh DB); RBAC role/domain checks still enforced |
| **Encryption** | `core/encryption.py` | AES-256-GCM for DB credentials (the "vault") |
| **Redis** | `core/redis.py` | One async client: Celery broker, `cache/query_cache`, rate-limit counters, `connections/circuit_breaker`, discovery progress |
| **Circuit breaker** | `services/connections/circuit_breaker.py` | After repeated failures to a source DB, "opens" and fast-fails instead of hanging 30s each time |
| **Embedding model** | `services/embedding/client.py` | `BAAI/bge-large-en-v1.5` (1024-dim) loaded in-process; cache dir set via `HF_HOME=/data/.hf_cache` (compose) |
| **Logging** | `core/logging.py` | structlog → JSON; agents log `agent.start` etc.; SQL echo off by default (`SQL_ECHO=true` to enable) |
| **Errors** | `core/exceptions.py` | `AppError` subclasses → uniform `{success:false, error:{code,message}}` envelope |
| **Audit** | `services/audit_service.py` | Writes compliance events (discovery completed, etc.) |

---

## 7. Request lifecycle, end to end (a single chat question)

```
1. Browser POST /api/v1/conversations/{id}/ask
2. Middleware: RequestID → RateLimit (Redis) → SecurityHeaders → CORS
3. ask() resolves default user + tenant, builds AgentState
4. run_question() walks the LangGraph nodes (each = a BaseAgent):
     context → intent → planner → (vector search over pgvector) →
     sql_executor → (validate → connector → user's MSSQL) → formatter (Claude)
5. save_turn() persists the answer to conversation_turns
6. Response envelope returned; RequestIDMiddleware stamps the header
```

Every external dependency the question touches: **Postgres** (catalogue +
vector search + history), **Redis** (rate limit, cache), the **bge-large model**
(embed the question), **Claude** (classify + narrate), and the **user's MSSQL**
(run the tool's SQL).

---

## 8. Observability / debugging

- **Live trace:** `docker compose logs -f api worker`. Filter to the pipeline:
  ```
  | grep -E '"agent\.|intent_classifier|query_planner|sql_executor|HTTP Request: POST https://api.anthropic'
  ```
- The per-question trace is `agent.start → intent_classifier.result →
  query_planner.selected → sql_executor.done`; failures show `*.fail` /
  `agent.error`, and the matching stage name tells you exactly where it broke.
- SQL echo is off by default; set `SQL_ECHO=true` in `.env` to see every
  statement when debugging the DB layer.

---

## 9. Quick "where do I change X" index

| I want to… | Edit |
|---|---|
| Add a new HTTP endpoint | `api/v1/endpoints/*` + register in `api/v1/router.py` |
| Add/alter a pre-built tool | `services/tools/sap_b1_tools.py` (then re-embed) |
| Change how a question is routed | `agents/supervisor.py` (`_route_after_*`) + `agents/intent_classifier.py` |
| Add a new runtime agent/node | new `agents/*.py` + wire in `supervisor.py` |
| Change the post-discovery pipeline | `worker/tasks/discovery.py: build_post_discovery_pipeline()` |
| Change schema crawl logic | `services/discovery/crawler.py` |
| Change ERP detection / entity mapping | `services/semantic/mssql_fingerprint.py`, `pack_loader.py`, `sap_b1_pack.py` |
| Change SQL safety rules | `services/sql/validator.py` |
| Change DB connector behavior | `services/connections/connector.py` |
| Add a DB table | `models/*.py` + an Alembic migration in `alembic/versions/` |
```
