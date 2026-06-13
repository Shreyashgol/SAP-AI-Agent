---
  Part 1 — The data layer: what's stored where, and why

  PostgreSQL 16 + pgvector (the system's own database — not the user's SAP data)

  This is the platform's brain. The user's SAP B1 data stays in their SQL Server — Postgres only stores metadata about it, plus all application state. The
  33 tables (created in alembic/versions/0001_initial_schema.py) group into:

  ┌──────────────────┬───────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
  │      Group       │                              Tables                               │                        What it holds                        │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Identity &       │ tenants, users, roles, role_permissions, user_roles               │ Multi-tenant accounts and RBAC (platform_admin → viewer, 5  │
  │ access           │                                                                   │ data domains)                                               │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Connections      │ connections                                                       │ User's SAP DB details; password is AES-256-GCM encrypted,   │
  │                  │                                                                   │ never stored or returned in plaintext                       │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Schema catalog   │ metadata_tables, metadata_columns, metadata_relations             │ What discovery crawls out of the user's SQL Server: every   │
  │                  │                                                                   │ table, column, foreign key                                  │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │                  │ semantic_entities, semantic_attributes, kpi_definitions,          │ The mapping from raw tables (OCRD, OINV…) to business       │
  │ Semantic layer   │ business_glossary, synonym_mappings, business_rules               │ concepts ("Customers", "Invoices", "Revenue") that the AI   │
  │                  │                                                                   │ uses to write correct SQL                                   │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Knowledge graph  │ knowledge_graph_nodes/edges                                       │ Entity-relationship graph for reasoning over how concepts   │
  │                  │                                                                   │ connect                                                     │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Embeddings       │ document_embeddings, tool_embeddings, document_chunks, documents  │ Vector representations for semantic search (RAG)            │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Conversations &  │ conversations, dashboards, dashboard_widgets, alerts,             │                                                             │
  │ output           │ alert_rules, report_schedules, report_executions, user_feedback,  │ Chat history, pinned dashboards, alerting, feedback loop    │
  │                  │ feedback_corrections                                              │                                                             │
  ├──────────────────┼───────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
  │ Tools & audit    │ tools, tool_table_dependencies, tool_ranking_weights, audit log   │ The agent's tool catalog and a compliance trail             │
  └──────────────────┴───────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────┘

  Why Postgres + pgvector instead of Postgres + a separate vector DB (Pinecone/Qdrant): one engine does both relational and vector workloads, so an
  embedding row lives in the same transaction as its source chunk — no sync drift between two databases, one backup story, and SQL joins straight from
  vector hits to business metadata.

  HNSW index (m=16, ef_construction=128)

  When you ask a question, the agent embeds it and must find the most similar stored vectors. Comparing against every row (brute force) is O(n); HNSW
  ("Hierarchical Navigable Small World") builds a multi-layer graph over the vectors so lookup is roughly O(log n) — millisecond-level approximate
  nearest-neighbor search. The two knobs: m=16 is how many neighbors each node links to (graph density), ef_construction=128 is how hard it searches while
  building the index. These are the standard balanced defaults — good recall without bloating memory or insert time. It's applied to document_embeddings
  and tool_embeddings with cosine distance (vector_cosine_ops), which suits normalized text embeddings.

  Redis 7 (AOF + RDB persistence)

  Postgres is durable truth; Redis is everything fast and ephemeral. In this codebase it serves four distinct jobs:
  - Celery broker + result backend — the queue that carries background jobs (schema discovery crawls, embedding generation) from the API to the worker
  process.
  - Circuit breaker state (services/connections/circuit_breaker.py) — counts failures per connection; after repeated failures, it "opens" and instantly
  rejects further attempts to a dead SAP server instead of hanging for 30s each time.
  - Rate limiting (middleware/rate_limit.py) and query cache (services/cache/query_cache.py) — counters and cached query results with TTLs.
  - Job progress — discovery writes {stage, pct} keys that the onboarding wizard polls every 3 seconds.

  AOF + RDB means it both snapshots and logs every write, so queue contents survive a restart. The compose file runs redis:7-alpine with this enabled.

  Secrets (HashiCorp Vault / AWS Secrets Manager)

  The spec calls for Vault, but the code currently ships a local stand-in: credentials are AES-256-GCM encrypted (core/encryption.py, key from the
  ENCRYPTION_KEY env var) and the blob is stored in connections.vault_credential_path prefixed local:. The field name is deliberate — swapping in real
  Vault later means writing the secret there and storing the Vault path in the same column. Why this design at all: a DB dump alone can never leak SAP
  passwords (you'd also need the encryption key, which lives only in the environment), and the API never returns credentials after save (the response
  schema simply has no password field).

  How it all flows together: user submits SAP credentials → encrypted into Postgres → Celery worker (via Redis queue) connects to their SQL Server, crawls
  the schema into metadata_* → semantic layer maps it to business entities → embeddings of docs/tools land in pgvector with HNSW indexes → at question time
  the agent does vector search + semantic-layer lookup to generate SQL, runs it against the user's database, and caches/rate-limits via Redis.

  ---
  Part 2 — MSSQL connection path: what I found and fixed

  I traced the full path: POST /connections → ConnectionService.create (encrypt + store) → POST /connections/{id}/test → MSSQLConnector (pyodbc) →
  discovery worker. It had three bugs that made user-provided SQL Server connections fail, all fixed:

  1. pyodbc was commented out in requirements.txt — every MSSQL attempt died with "pyodbc not installed". Re-enabled (pyodbc==5.1.0).
  2. The Docker image never installed Microsoft's ODBC driver. The code requests ODBC Driver 18 for SQL Server, but the image only had generic unixODBC —
  so even with pyodbc, connections would fail with "driver not found". The runtime stage of backend/Dockerfile now adds Microsoft's Debian 12 repo and
  installs msodbcsql18.
  3. TLS settings rejected real-world SAP B1 servers. TrustServerCertificate=no was hardcoded, and on-prem SQL Servers almost always use self-signed
  certificates — the handshake would fail even with perfect credentials. There's now a single build_mssql_conn_str() helper in connector.py:27 that honors
  the is_tls flag the user picks (traffic still encrypted when on) with TrustServerCertificate=yes, and brace-escapes the password so ;, =, or } in
  passwords can't break the connection string. Both the connector and the discovery worker (which had its own duplicated, equally broken copy) now use it.

  I also hardened credential storage in connection_service.py:39: the JSON blob was built with an f-string, so a password containing a quote produced a
  corrupt blob that crashed on decrypt. It now uses json.dumps and stores is_tls with the credentials (old blobs fall back to the connection row's flag).

  All edited files pass syntax checks, and no tests asserted the old connection-string format. One note: I couldn't test against a live SQL Server from
  here — to pick up pyodbc and the ODBC driver you'll need to rebuild the image (docker compose build then restart), and the existing connection-test
  endpoint (POST /connections/{id}/test) will tell you latency/version/read-only status against your real server.