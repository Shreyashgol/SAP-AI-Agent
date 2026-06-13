# Enterprise AI Intelligence Platform
## Development Execution Plan — Sprint & Phase Breakdown
### Version 1.0 FINAL (Cross-Checked) — June 2026

**Scope:** MVP v1.0 + Release v1.1 | From scratch → Production deployed
**Source Specification:** Production Spec v2.0 (Green-Flagged)
**Sprint Length:** 2 weeks | **MVP Timeline:** 28 weeks (14 sprints) | **v1.1:** +6 weeks (3 sprints)

---

## 1. TEAM COMPOSITION & ROLES

| Role | Count | Allocation | Primary Responsibility |
|------|-------|-----------|----------------------|
| Tech Lead / Architect | 1 | 100% | Architecture decisions, code review, agent design, unblocking |
| Backend Engineer | 2 | 100% | FastAPI, connectors, discovery, semantic layer, tools, DB |
| AI/ML Engineer | 1 | 100% | LangGraph agents, prompts, embeddings, golden dataset, RAG |
| Frontend Engineer | 1 | 100% | React UI, WebSocket streaming, charts, dashboards |
| DevOps Engineer | 1 | 50% | CI/CD, Docker/K8s, observability, environments, backups |
| QA Engineer | 1 | 100% | Test framework, golden dataset runner, security/perf tests |
| SAP B1 Domain Expert | 1 | 50% | Entity pack validation, tool SQL review, golden dataset Q&A |
| Product Manager | 1 | 50% | Backlog, UAT coordination, pilot customer, acceptance |

**Total: ~6.5 FTE engineering + 1 PM**

---

## 2. TECHNOLOGY STACK (LOCKED FOR DEVELOPMENT)

### Backend
| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12 |
| API Framework | FastAPI | 0.111+ |
| ASGI Server | Uvicorn + Gunicorn | latest stable |
| Agent Orchestration | LangGraph | 1.x |
| LLM | Claude API (Sonnet + Haiku) | claude-sonnet-4, claude-haiku |
| Embeddings | Claude embeddings (1536 dim) | latest |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic | latest |
| Task Queue | Celery + RedBeat | 5.x |
| SAP B1 Connector | hdbcli | latest |
| MSSQL Connector | pyodbc + SQLAlchemy dialect | latest |
| SQL Validation | sqlglot (AST parsing) | latest |
| Forecasting (v1.1) | Prophet | latest |
| PDF Generation | WeasyPrint | latest |
| Excel Generation | openpyxl | latest |
| Auth | python-jose (JWT) + passlib (bcrypt) | latest |
| SSO | python3-saml + authlib (OIDC) | latest |

### Data Layer
| Component | Technology |
|-----------|-----------|
| Primary DB | PostgreSQL 16 + pgvector extension |
| Vector Index | HNSW (m=16, ef_construction=128) |
| Cache / Session / Queues | Redis 7 (AOF + RDB) |
| Secrets | HashiCorp Vault (or AWS Secrets Manager) |

### Frontend
| Component | Technology |
|-----------|-----------|
| Framework | React 18 + TypeScript 5 |
| Build | Vite |
| Server State | TanStack React Query |
| Local State | Zustand |
| Charts | Recharts |
| Tables | TanStack Table |
| Graph Visualiser | D3.js (force-directed) |
| Dashboard Grid | React Grid Layout |
| Styling | Tailwind CSS |
| WebSocket | native WebSocket + reconnect wrapper |
| E2E Testing | Playwright |

### DevOps & Quality
| Component | Technology |
|-----------|-----------|
| Containers | Docker + Docker Compose (dev), Kubernetes (prod) |
| CI/CD | GitHub Actions |
| IaC | Terraform (cloud infra) |
| Reverse Proxy | Nginx (TLS 1.3) |
| Metrics | Prometheus + Grafana |
| Logs | Loki (structured JSON) |
| Errors | Sentry |
| Agent Tracing | LangSmith |
| Load Testing | k6 |
| Unit/Integration Tests | pytest + pytest-asyncio + coverage |
| Lint/Type | ruff + mypy |
| Security Scan | pip-audit + bandit + Snyk |

---

## 3. PHASE OVERVIEW

```
PHASE 0  Foundation & Setup          Sprint 0            Weeks 1–2
PHASE 1  Data Foundation             Sprints 1–2         Weeks 3–6
PHASE 2  Knowledge & Intelligence    Sprints 3–5         Weeks 7–12
PHASE 3  Agentic Runtime             Sprints 6–9         Weeks 13–20
PHASE 4  Experience & Delivery       Sprints 10–11       Weeks 21–24
PHASE 5  Hardening & Launch          Sprints 12–13       Weeks 25–28  → MVP v1.0 LIVE
PHASE 6  Proactive & Learning (v1.1) Sprints 14–16       Weeks 29–34  → v1.1 LIVE
```

**Parallel tracks run throughout:** Frontend begins UI foundations in Sprint 1 (not waiting for Phase 4). QA builds test infrastructure from Sprint 0. SAP Domain Expert builds golden dataset Sprints 0–3.

---

## 4. PHASE 0 — FOUNDATION & SETUP (Sprint 0, Weeks 1–2)

**Goal:** Every engineer can clone, run, test, and deploy a hello-world slice of the platform on day 10.

### Sprint 0 Deliverables

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 0.1 | Git monorepo structure (`/backend`, `/frontend`, `/infra`, `/docs`) + branch protection | Tech Lead | — |
| 0.2 | Docker Compose dev environment: api, worker, beat, postgres(pgvector), redis, nginx | DevOps | Part 11.2 |
| 0.3 | PostgreSQL schema v1: all 33 tables via Alembic migrations + RLS policies + partitioning (audit_log, conversation_turns, tool_executions) | Backend 1 | Part 6 |
| 0.4 | FastAPI skeleton: app factory, settings, structured JSON logging, request_id middleware, response envelopes, error handler, `/health/live`, `/health/ready` | Backend 2 | Part 5.1–5.2 |
| 0.5 | CI pipeline v1: ruff + mypy + pytest + coverage gate (80%) + pip-audit/bandit + Docker build on PR | DevOps | Part 11.3 |
| 0.6 | React app scaffold: Vite + TS + Tailwind + React Query + Zustand + router + login page shell | Frontend | Part 12 |
| 0.7 | Test framework: pytest fixtures (test tenant, test DB), factory pattern, coverage config | QA | Part 9 |
| 0.8 | SAP B1 test environment: demo company DB (HANA) provisioned + MSSQL test DB | SAP Expert + DevOps | — |
| 0.9 | Golden dataset build started: first 40 Q&A pairs (AR/AP + Sales) verified against test DB | SAP Expert + QA | Part 8.4 |
| 0.10 | Secrets management: Vault dev instance, credential pattern established, `.env` policy | DevOps | NFR-SEC09 |
| 0.11 | LangSmith + Sentry projects created and wired into skeleton | AI Engineer | Part 10.1 |

### Sprint 0 Exit Criteria
- `docker compose up` produces a running stack passing `/health/ready`
- CI green on main; a sample migration + sample test runs end-to-end
- All engineers onboarded with local environments

---

## 5. PHASE 1 — DATA FOUNDATION (Sprints 1–2, Weeks 3–6)

**Goal:** Platform can securely connect to SAP B1 HANA and MSSQL, discover full schemas, and populate the metadata catalog.

### Sprint 1 — Auth, Tenancy & Connections

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 1.1 | Auth API: login, refresh, logout, me; JWT (8h) + refresh (30d, httpOnly); bcrypt; lockout (5 attempts/15 min); Redis token blocklist | Backend 1 | Part 5.3 AUTH, NFR-SEC03–05 |
| 1.2 | Tenancy + RBAC: tenants, users, roles (4 system roles), user_roles, role_permissions (5 domains); permission dependency for endpoints | Backend 1 | Module 12, Part 6 |
| 1.3 | Connections API: CRUD + test + health; credentials → Vault reference only; AES-256; never returned via API | Backend 2 | Module 1 DC-001/002/003/012 |
| 1.4 | HANA + MSSQL connector services: pooled (min 2/max 10), TLS, 30s timeout, read-only enforcement check on connect | Backend 2 | DC-001, DC-002, NFR-R06 |
| 1.5 | Circuit breakers for HANA/MSSQL (5 fails/60s → open 120s) | Backend 2 | Part 7.2 |
| 1.6 | Audit log service: append-only writes, trigger blocking UPDATE/DELETE, partition automation | Backend 1 | GS-005, NFR-SEC10 |
| 1.7 | Rate limiting middleware: 60 req/min/user, 100 req/min/tenant, 429 + Retry-After | Backend 1 | NFR-SEC08 |
| 1.8 | FE: Login + auth flow (token refresh interceptor), app shell with sidebar, connections management screen (create/test/list) | Frontend | Part 12.1 |
| 1.9 | Unit tests: JWT suite, RBAC matrix (4 roles × 5 domains), lockout, rate limit, audit immutability | QA | Part 9.2, 9.5 |
| 1.10 | Golden dataset: +30 pairs (Inventory + Financials) | SAP Expert | Part 8.4 |

### Sprint 2 — Discovery Engine & Metadata Catalog

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 2.1 | Discovery jobs: async Celery job, progress tracking, full + incremental modes, metadata hash change detection | Backend 2 | DC-004, DC-010 |
| 2.2 | Schema crawler: tables, columns, types, constraints, views; excludes system schemas; handles 10k tables (NFR-S01) within 10 min (NFR-P03) | Backend 2 | DC-004, DC-006 |
| 2.3 | FK discovery: explicit (information_schema) + inferred (column-name patterns, confidence-scored) | Backend 1 | DC-005 |
| 2.4 | Column statistics + sample harvesting (20 rows, PII-excluded, encrypted) | Backend 1 | DC-008, DC-009 |
| 2.5 | PII detector: pattern library scan, auto-flag, admin review queue | Backend 1 | GS-006, GS-007 |
| 2.6 | Metadata catalog APIs: search (tsvector), versioning + diff, health score, lineage stubs | Backend 2 | MC-001–MC-006 |
| 2.7 | FE: Discovery progress screen (poll job status), metadata catalog browser with search | Frontend | Part 12.1 |
| 2.8 | Integration tests: full discovery against SAP B1 demo DB (500+ tables) and MSSQL test DB | QA | Part 9.3 |
| 2.9 | Golden dataset: final 30 pairs (Analytics/RCA) → 100 complete + verified | SAP Expert + QA | Part 8.4 |
| 2.10 | Grafana dashboard v1: API latency, error rate, discovery job metrics | DevOps | Part 10.2 |

### Phase 1 Exit Criteria (Milestone M1)
- Connect SAP B1 HANA demo DB → full discovery completes < 10 min → catalog browsable in UI
- Golden dataset of 100 verified Q&A pairs frozen as regression baseline
- Auth + RBAC + audit fully tested; security unit suite green

---

## 6. PHASE 2 — KNOWLEDGE & INTELLIGENCE (Sprints 3–5, Weeks 7–12)

**Goal:** Raw metadata becomes business knowledge: semantic layer, knowledge graph, and a validated, embedded, rankable tool catalogue.

### Sprint 3 — Semantic Layer + SAP B1 Entity Pack

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 3.1 | SAP B1 Entity Pack loader: 80+ table mappings, attribute mappings, 12 business rules, status-code reference; auto-applied on HANA connection | Backend 1 + SAP Expert | SL-010, Part 8.1–8.2 |
| 3.2 | AI entity/attribute mapper: Claude-driven mapping for unmapped tables, confidence-scored, semantic_type detection | AI Engineer | SL-001, SL-002 |
| 3.3 | KPI catalogue + metric library (50+ metrics) + business glossary generation | AI Engineer | SL-003–SL-005 |
| 3.4 | Synonym engine + business rules engine (predicate storage + default application) | Backend 1 | SL-006, SL-007 |
| 3.5 | Human override system: edits persist with priority over AI, survive regeneration; semantic versioning | Backend 1 | SL-008, SL-009 |
| 3.6 | MSSQL schema fingerprinting: pattern library (Dynamics BC, Sage 300), best-match pack application, AI fallback | AI Engineer | SL-011 |
| 3.7 | FE: Semantic layer review/edit screen (wizard step 3), glossary browser, KPI library screen | Frontend | OB-001, Part 12.1 |
| 3.8 | Unit tests: entity pack correctness on all 80+ tables, business rule SQL validity | QA + SAP Expert | Part 9.2 |

### Sprint 4 — Knowledge Graph + Tool Generation

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 4.1 | Knowledge graph builder: nodes from entities, FK edges (1.0), inferred edges (scored, admin-confirm gate at <0.8) | Backend 2 | KG-001–KG-003, KG-006 |
| 4.2 | Graph traversal service: BFS path-finding, max 5 hops, <500ms (NFR-P07); join condition output | Backend 2 | KG-004, KG-007 |
| 4.3 | Graph refresh on catalog change events | Backend 2 | KG-009 |
| 4.4 | Tool Generation Engine: auto-generation from semantic layer + KG; tool schema; validation at generation (LIMIT 1 test); versioning; dependency map; deprecation on schema change | Backend 1 | TG-001/002/009/010/011/013 |
| 4.5 | SAP B1 Tool Pack: all 50 tools implemented as parameterised SQL templates, validated against demo DB | Backend 1 + SAP Expert | TG-012, Part 8.3 |
| 4.6 | FE: Knowledge graph visualiser (D3 force-directed), tool catalogue manager screen | Frontend | KG-005, Part 12.1 |
| 4.7 | Unit tests: traversal correctness, hop limit, 50 tool SQL signatures against demo DB | QA | Part 9.2 |

### Sprint 5 — Embeddings, Ranking & Custom Tools

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 5.1 | Embedding service: Claude embeddings (1536), tool embedding pipeline, HNSW index, <200ms ANN search (NFR-P06) | AI Engineer | TG-003 |
| 5.2 | Tool Ranking Engine: composite scoring (similarity 0.40 + success 0.35 + feedback 0.20 + context 0.05), permission hard-gate, 0.65 threshold, ranking explainability log | AI Engineer | Module 6, Agent 7 |
| 5.3 | Tool execution service: parameterised execution, result validation, fallback chain (3 tools), execution history logging | Backend 1 | Agent 8, TG-009 |
| 5.4 | Custom tool builder API + admin UI (SQL editor, live test, save as custom) | Backend 2 + Frontend | TG-008 |
| 5.5 | KPI quick-start activation + onboarding wizard steps 4–5 (graph preview, tool review) | Frontend | OB-001, OB-006 |
| 5.6 | Benchmark suite: vector search latency, traversal latency under load | QA | NFR-P06/P07 |

### Phase 2 Exit Criteria (Milestone M2)
- SAP B1 connection → entity pack applied → 50 tools generated, validated, embedded, and rankable
- Demo: programmatically rank + execute correct tool for 20 sample questions with ≥ 90% top-1 accuracy
- Admin can review/edit semantic layer and confirm inferred graph edges in UI

---

## 7. PHASE 3 — AGENTIC RUNTIME (Sprints 6–9, Weeks 13–20)

**Goal:** All 15 LangGraph agents implemented, integrated, and answering questions end-to-end with confidence and lineage.

### Sprint 6 — Runtime Core (Agents 1–5)

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 6.1 | LangGraph StateGraph foundation: PlatformState schema, checkpointing, iteration limit (5) with loud RuntimeError | AI Engineer | Agent 1 |
| 6.2 | Supervisor Agent: deterministic Command routing, retry/fallback/escalate logic, 60s node + 120s pipeline timeouts | AI Engineer | Agent 1, NFR-R03–R05 |
| 6.3 | Intent & Routing Agent: 7-class Haiku classifier, <500ms, planner trigger flag | AI Engineer | Agent 2 |
| 6.4 | Conversation Context Agent: Redis session (24h TTL), 50-turn window, entity carry-forward, question enrichment | AI Engineer | Agent 3 |
| 6.5 | Semantic Retrieval Agent + Knowledge Graph Agent: wire existing services as graph nodes | Backend 2 | Agents 4–5 |
| 6.6 | Conversations API: create/list/get/delete + non-streaming message endpoint (REST path first) | Backend 1 | Part 5.3 |
| 6.7 | LangSmith tracing on every node; agent metrics → Prometheus | AI + DevOps | Part 10 |
| 6.8 | Integration tests: pipeline with mocked LLM (deterministic fixtures) | QA | Part 9.3 |

### Sprint 7 — Execution Agents (6–9)

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 7.1 | Planner Agent: hybrid-question decomposition, sub-task DAG, max 2 re-plans | AI Engineer | Agent 6 |
| 7.2 | Tool Ranking + Tool Execution Agents as graph nodes (wire Sprint 5 services), fallback to SQL Agent | AI Engineer | Agents 7–8 |
| 7.3 | SQL Agent: KG-join-path query builder, RLS injection, column masking, **sqlglot AST validation with DML hard-block**, parameterised execution, unverified flag | Backend 1 + AI | Agent 9, GS-008/009 |
| 7.4 | Column-level masking service (GS-004) wired into both tool execution and SQL agent | Backend 1 | GS-004 |
| 7.5 | Security test suite: 50 SQL injection patterns, all DML variants incl. obfuscated, cross-domain RBAC, cross-company RLS | QA | Part 9.5 |
| 7.6 | Golden dataset runner v1: executes 100 Q&A via REST pipeline, accuracy report; wired into CI as informational | QA | Part 9.4 |
| 7.7 | FE: Conversation screen v1 — input, REST request/response, answer text + data table rendering | Frontend | Part 12.2 |

### Sprint 8 — RAG + Web Search (Agents 10, 12)

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 8.1 | Document pipeline: upload API (50MB cap), Celery ingestion, chunking (512 tok/50 overlap, structure-aware), embedding, HNSW index, status tracking, refresh/delete | Backend 2 | DI-001–DI-003, DI-010 |
| 8.2 | Hybrid retrieval: BM25 (tsvector) + pgvector + RRF merge, top-5; document access control filter; metadata tagging | Backend 2 | DI-004, DI-005, DI-009 |
| 8.3 | RAG Agent: synthesis with citations, cross-document reasoning, GraphRAG entity boost, graceful "not found" | AI Engineer | Agent 10, DI-006/008/011 |
| 8.4 | Document-to-data linking (entity tags on documents) | Backend 2 | DI-007 |
| 8.5 | **Web Search Agent: domain whitelist enforcement (hardcoded), external data normalisation, source citations, Redis cache (1h TTL), audit logging, graceful failure (never blocks primary answer)** | AI Engineer | Agent 12, NFR-SEC13 |
| 8.6 | FE: Document library screen (upload, status, list), wizard step 6 | Frontend | Part 12.1 |
| 8.7 | Tests: ingestion of 10MB PDF < 60s (NFR-P08), retrieval accuracy fixtures, whitelist block tests | QA | Part 9.2/9.3 |

### Sprint 9 — Analytics, Trust & Synthesis (Agents 11, 13*, 14, 15)

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 9.1 | Analytics Engine + Agent: trend, period comparison, RCA (dimension decomposition, top-3 drivers), variance (volume/price/mix), ranking, contribution, NL narrative | AI Engineer + Backend 1 | Module 9, Agent 11 |
| 9.2 | Analytics REST endpoints (trend/compare/rca) | Backend 1 | Part 5.3 |
| 9.3 | Confidence & Explainability Agent: composite scoring formula, lineage trace builder, conflict detection, **hallucination guard (numeric cross-check, >1% mismatch → regenerate)** | AI Engineer | Agent 14, TE-001–TE-009 |
| 9.4 | Response Synthesis Agent: chart-type selection rules, NL narrative (2–4 sentences), low-confidence warnings, 3 follow-up questions | AI Engineer | Agent 15 |
| 9.5 | WebSocket streaming: `/conversations/{id}/stream`, message protocol (agent_thinking/partial/complete/error), reconnect handling | Backend 2 + Frontend | Part 5.2 |
| 9.6 | Web Search Agent → Analytics integration (external enrichment path) | AI Engineer | Agent 12 |
| 9.7 | Full-pipeline integration test: all 15 agents, all 7 intents, failure-path tests (timeouts, fallbacks, degradation levels 0–4) | QA | Part 7, 9.3 |
| 9.8 | Golden dataset gate activated in CI: merge to main blocked if accuracy < 85% | QA + DevOps | Part 9.4 |

*Agent 13 (Proactive Intelligence) is v1.1 — scheduled in Phase 6. Its hooks (alert tables, rule storage) exist from Sprint 0 schema.*

### Phase 3 Exit Criteria (Milestone M3)
- End-to-end: any of the 100 golden questions answered via streaming with chart hint, confidence badge data, and lineage — accuracy ≥ 85%
- Security suite green: zero DML escapes, zero RBAC/RLS bypasses
- p95 simple-lookup latency < 3s on dev hardware

---

## 8. PHASE 4 — EXPERIENCE & DELIVERY (Sprints 10–11, Weeks 21–24)

**Goal:** Complete, polished user experience: conversation UI with charts, dashboards, exports, onboarding wizard, and admin console.

### Sprint 10 — Conversation Experience & Visualisation

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 10.1 | Conversation screen v2 (full spec): streaming states (IDLE→THINKING→STREAMING→COMPLETE), agent activity indicator, confidence badges, low-confidence banner, error states | Frontend | Part 12.2 |
| 10.2 | Visualisation engine: KPI cards, bar/line/area/donut/waterfall, auto-selection from synthesis hint, chart-type toggle, hover tooltips | Frontend | Module 14 |
| 10.3 | Drill-through (click datapoint → pre-populated follow-up), chart annotations, PNG/SVG export | Frontend | VE-009/010/011 |
| 10.4 | Lineage trace panel: tables, tool/SQL (syntax-highlighted), agent path, execution time, "Verify Data" raw table | Frontend | TE-002/004/007, Part 12.2 |
| 10.5 | Feedback controls: 👍👎 + correction submission (FL-001/002 capture; learning loop is v1.1) | Frontend + Backend 1 | FL-001, FL-002 |
| 10.6 | Suggested follow-up chips + sample question gallery | Frontend | OB-005 |
| 10.7 | Responsive pass: 1280/768/375 breakpoints, mobile KPI-card fallback | Frontend | NFR-U05, VE-013 |
| 10.8 | Accessibility pass: WCAG 2.1 AA (axe-core automated + manual keyboard/contrast audit) | Frontend + QA | NFR-U06 |

### Sprint 11 — Dashboards, Exports, Onboarding & Admin

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 11.1 | Dashboard builder: pin answers, grid layout, per-user persistence, share link | Frontend + Backend 2 | VE-012 |
| 11.2 | PDF export (WeasyPrint, tenant branding) <15s (NFR-P10); Excel export (openpyxl, formatted) | Backend 2 | RD-005, RD-006, RD-011 |
| 11.3 | Onboarding wizard complete (all 8 steps incl. alerts config step as v1.1-stub), progress tracker, setup validation (10 standard queries auto-test) | Frontend + Backend 1 | OB-001/004/007 |
| 11.4 | Admin console: users, roles, audit log viewer, catalog health, usage/ROI dashboard, tool performance view | Frontend + Backend 1 | Part 12.1, OB-009, FL-003 |
| 11.5 | SSO: SAML 2.0 + OIDC, attribute→role mapping; tested against Entra ID + Okta | Backend 1 | GS-011 |
| 11.6 | GDPR erasure endpoint: delete user conversation logs on request | Backend 1 | NFR-C01 |
| 11.7 | E2E suite: E2E-001 → E2E-010 in Playwright, wired to CI on staging deploys | QA | Part 9.7 |

### Phase 4 Exit Criteria (Milestone M4)
- Full onboarding wizard: new SAP B1 connection → first correct answer ≤ 30 minutes (E2E-010 passes)
- All 10 E2E scenarios green
- WCAG AA automated audit passes; responsive verified on 3 breakpoints

---

## 9. PHASE 5 — HARDENING & LAUNCH (Sprints 12–13, Weeks 25–28)

**Goal:** Production infrastructure live, performance validated, pilot customer onboarded, MVP v1.0 launched.

### Sprint 12 — Production Infrastructure & Performance

| # | Deliverable | Owner | Spec Ref |
|---|------------|-------|----------|
| 12.1 | Staging + production environments: Terraform-provisioned K8s (or managed equivalent), sizing per spec (12 vCPU/45GB), HPA rules (API CPU>70%, queue>50) | DevOps | Part 11.1, 11.4 |
| 12.2 | CD pipeline complete: staging auto-deploy + smoke tests + approval gate + prod deploy + post-deploy health check + 5-min auto-rollback | DevOps | Part 11.3 |
| 12.3 | Backups: daily pg_dump + WAL archiving (PITR), Redis RDB/AOF; **restore drill executed and timed (RTO < 4h verified)** | DevOps | Part 11.5, NFR-R09/R10 |
| 12.4 | Full observability: all Part 10.2 metrics, 13 alert rules wired to on-call (PagerDuty/Opsgenie), Loki log aggregation, uptime monitor | DevOps | Part 10.3 |
| 12.5 | Performance campaign (k6): load (50 users/10 min), stress (ramp to 200), spike (0→100/30s), soak (4h), volume (5k-table discovery) — all NFR-P targets verified on staging | QA + DevOps | Part 9.6 |
| 12.6 | Performance remediation: fix any NFR misses (query plans, caching, pool tuning, prompt-token reduction) | All Eng | NFR-P01–P12 |
| 12.7 | Penetration test pass: external or internal red-team against staging (auth, injection, RLS, rate limits, whitelist) | QA + Security | Part 9.5 |
| 12.8 | EU AI Act classification memo + privacy documentation (no-training header verified in all Claude calls) | Tech Lead + PM | NFR-C02, NFR-C05 |

### Sprint 13 — UAT, Pilot & Launch

| # | Deliverable | Owner |
|---|------------|-------|
| 13.1 | UAT with pilot customer: real SAP B1 company DB on staging, 2-week structured test script, daily triage | PM + All |
| 13.2 | Bug-fix burn-down: P0/P1 zero before launch; P2 triaged to v1.1 backlog | All Eng |
| 13.3 | Golden dataset final certification run on staging with pilot data variant: ≥ 85% | QA |
| 13.4 | Operational runbooks: incident response, on-call rotation, escalation matrix, degradation-level playbooks (Levels 0–5) | DevOps + Tech Lead |
| 13.5 | Documentation: admin guide, user quick-start, API docs (OpenAPI published) | PM + Tech Lead |
| 13.6 | **PRODUCTION LAUNCH — MVP v1.0** + 1-week hypercare (daily monitoring review) | All |

### Phase 5 Exit Criteria (Milestone M5 — GO-LIVE)
- All Part 14 acceptance criteria met: accuracy ≥85%, p95 targets, zero-DML verified in production audit, uptime monitoring live
- Pilot customer answering real business questions in production
- On-call + runbooks operational

---

## 10. PHASE 6 — v1.1: PROACTIVE & LEARNING (Sprints 14–16, Weeks 29–34)

### Sprint 14 — Proactive Intelligence (Agent 13)

| # | Deliverable | Spec Ref |
|---|------------|----------|
| 14.1 | Proactive Intelligence Agent: Celery-beat KPI monitoring cycles (1h/4h/24h), Z-score + IQR anomaly detection (7-point baseline), deduplication (4h window) | Agent 13, PI-001/003 |
| 14.2 | Alert rules engine + threshold alerts + business event triggers (overdue AR, reorder, large order) | PI-002, PI-004 |
| 14.3 | Auto-RCA on confirmed anomaly (Analytics Agent trigger) + alert routing by role/domain | Agent 13, PI-008 |
| 14.4 | Alert Centre UI: active alerts, acknowledge/snooze/escalate, history, suggested questions | PI-006/009/010, Part 12.1 |

### Sprint 15 — Feedback Learning + Report Automation

| # | Deliverable | Spec Ref |
|---|------------|----------|
| 15.1 | Learning loop: nightly feedback-weight recalc → ranking engine, semantic drift detection (weekly), regeneration triggers, negative pattern capture | FL-004/005/006/008 |
| 15.2 | Feedback loop dashboard + glossary crowdsourcing review queue | FL-007/010 |
| 15.3 | Report scheduler: NL-defined reports, cron schedules, generation jobs, history + re-run | RD-001/002/010 |
| 15.4 | Delivery channels: email (SendGrid/SES) with embedded charts + PDF, Teams/Slack webhooks, subscriptions, anomaly-triggered reports | RD-003/004/008/009 |

### Sprint 16 — Forecast + v1.1 Hardening & Release

| # | Deliverable | Spec Ref |
|---|------------|----------|
| 16.1 | Forecast Engine: Prophet pipeline (min 24 points), confidence intervals, Web Search Agent macro-signal enrichment | AE-006 |
| 16.2 | Insight digest: daily 06:00 role-based summary | PI-005 |
| 16.3 | Regression: full golden dataset + E2E + performance re-run; new E2E scenarios for alerts/reports/forecast | Part 9 |
| 16.4 | **v1.1 PRODUCTION RELEASE** | — |

---

## 11. MILESTONES, DEPENDENCIES & CRITICAL PATH

```
M0  Wk 2   Dev environment + schema + CI live
M1  Wk 6   Discovery + catalog working; golden dataset frozen (100)
M2  Wk 12  Semantic layer + KG + 50 tools validated & rankable
M3  Wk 20  All 15 agents E2E; golden accuracy ≥85%; security suite green
M4  Wk 24  Full UX complete; E2E-001→010 green; ≤30-min onboarding proven
M5  Wk 28  MVP v1.0 PRODUCTION LAUNCH
M6  Wk 34  v1.1 release (Proactive + Learning + Reports + Forecast)

CRITICAL PATH:
Schema (S0) → Connectors (S1) → Discovery (S2) → Semantic Layer (S3)
→ KG + Tools (S4) → Embedding/Ranking (S5) → Runtime Core (S6)
→ Execution Agents (S7) → Trust/Synthesis (S9) → Hardening (S12) → Launch (S13)

OFF-CRITICAL-PATH (parallel): Frontend (S1+), RAG (S8 — parallel with S9 prep),
Web Search Agent (S8), Exports (S11), Golden dataset (S0–S2), Observability (continuous)
```

**Key dependency rules:**
- Golden dataset MUST be frozen by end of Sprint 2 — it is the acceptance instrument for Phase 3.
- SQL Agent (7.3) cannot merge without the security test suite (7.5) passing in the same sprint.
- WebSocket streaming (9.5) blocks Conversation screen v2 (10.1) — sequenced intentionally.
- Performance remediation buffer (12.6) is pre-allocated; do not consume it for features.

---

## 12. RISK REGISTER & MITIGATIONS

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| R1 | Golden dataset accuracy < 85% at M3 | Medium | High | Frozen dataset early (S2); accuracy tracked from S7 weekly; tool-pack-first design maximises deterministic answers; 2-sprint buffer via Phase 5 |
| R2 | SAP B1 HANA test environment access delays | Medium | High | Provisioned in Sprint 0 (item 0.8) as a blocking exit criterion; fallback: SQL Server-flavoured B1 demo DB |
| R3 | LLM latency pushes p95 > targets | Medium | Medium | Haiku for classification/synthesis paths; aggressive prompt-token budgets; Redis caching of identical questions; streaming hides perceived latency |
| R4 | Claude API cost overrun | Medium | Medium | Token metering per tenant from S6 (LangSmith), Haiku-first model tiering, embedding cache, monthly budget alert |
| R5 | Scope creep into MVP | High | High | v1.1/v2.0 fence enforced by PM; removed-features list is binding; change requests require Tech Lead + PM sign-off |
| R6 | Single AI engineer is a bottleneck in Phase 3 | Medium | High | Backend 2 pairs on agents from S6; agent specs are detailed enough for parallel implementation; Tech Lead absorbs overflow |
| R7 | pgvector performance at scale | Low | Medium | HNSW parameters pre-specified; benchmark in S5; fallback plan: dedicated read replica for vector workload |
| R8 | Pilot customer data surprises (custom UDFs/UDTs in SAP B1) | High | Medium | AI mapper (3.2) handles unmapped tables by design; UAT sprint (S13) reserved for exactly this; SAP expert on call |
| R9 | DML bypass via SQL obfuscation | Low | Critical | sqlglot AST (not regex), security suite with obfuscated variants, DML-attempt critical alert, read-only DB users as final backstop |

---

## 13. DEFINITION OF DONE (EVERY SPRINT)

A backlog item is DONE only when:
1. Code merged to main behind green CI (lint, types, unit tests, coverage ≥80%, security scan)
2. Integration tests for the feature pass
3. Feature traceable to a Spec v2.0 Feature ID / NFR ID
4. API changes reflected in OpenAPI; UI changes pass axe-core
5. Observability: relevant metrics/logs/traces emitted
6. Documentation updated (runbook or user-facing as applicable)
7. Demoed in sprint review against the spec acceptance criteria

---

## 14. CROSS-CHECK REPORT (PERFORMED ON THIS PLAN)

A full traceability audit of this plan against Production Spec v2.0 was performed before finalisation. **Five misses were found in the draft and fixed in this final version:**

| # | Issue Found in Draft | Fix Applied |
|---|---------------------|-------------|
| 1 | SSO (GS-011) and GDPR erasure (NFR-C01) were not assigned to any sprint | Added as Sprint 11 items 11.5 and 11.6 |
| 2 | MSSQL schema fingerprinting (SL-011) was missing — plan only covered the SAP B1 pack | Added as Sprint 3 item 3.6 |
| 3 | Backup **restore drill** (RTO verification) was absent — backups alone don't validate NFR-R09 | Added to Sprint 12 item 12.3 with explicit timed-restore requirement |
| 4 | Accessibility (NFR-U06, WCAG 2.1 AA) had no owner or sprint | Added as Sprint 10 item 10.8 with automated + manual audit |
| 5 | EU AI Act classification memo and no-training header verification (NFR-C02/C05) were unscheduled | Added as Sprint 12 item 12.8 |

### Final Traceability Verification

| Spec Element | Plan Coverage |
|--------------|--------------|
| Module 1 Data Connection & Discovery (11 features) | ✅ Sprints 1–2 |
| Module 2 Metadata Catalog (6) | ✅ Sprint 2 |
| Module 3 Semantic Layer (11) | ✅ Sprint 3 |
| Module 4 Knowledge Graph (9) | ✅ Sprint 4 |
| Module 5 Tool Generation (12) | ✅ Sprints 4–5 |
| Module 6 Tool Ranking (8) | ✅ Sprint 5 + Agent node S7 |
| Module 7 Document RAG (11) | ✅ Sprint 8 |
| Module 8 Runtime — all 15 agents | ✅ S6 (1–5), S7 (6–9), S8 (10, 12-WebSearch), S9 (11, 14, 15), S14 (13-Proactive, per v1.1 scope) |
| Module 9 Analytics (9, incl. Forecast v1.1) | ✅ Sprint 9 + Sprint 16 (Prophet) |
| Module 10 Proactive Intelligence (9) | ✅ Sprint 14 (v1.1 per spec Part 13) |
| Module 11 Trust & Explainability (9) | ✅ Sprint 9 + UI Sprint 10 |
| Module 12 Governance & Security (12) | ✅ Sprints 1, 2 (PII), 7 (masking), 11 (SSO/GDPR) |
| Module 13 Feedback & Learning (9) | ✅ Capture S10; loop S15 (v1.1 per spec) |
| Module 14 Visualisation (11) | ✅ Sprint 10 |
| Module 15 Report Automation (10) | ✅ S11 (PDF/Excel MVP) + S15 (scheduler/delivery v1.1) |
| Module 16 Onboarding (9) | ✅ Wizard steps across S2/S3/S5/S8/S11; validation S11 |
| All 57 NFRs | ✅ Performance S12.5; Security S1/S7/S12.7; Reliability S6/S12.3; Usability S10; Compliance S11.6/S12.8 |
| Error handling / circuit breakers / degradation L0–L5 | ✅ S1.5 (breakers), S6.2 (timeouts), S9.7 (degradation tests) |
| Testing strategy (unit/integration/golden/security/perf/E2E) | ✅ Continuous + S7.6, S9.8, S11.7, S12.5, S12.7 |
| Observability (metrics, 13 alerts, health endpoints) | ✅ S0.11, S2.10, S6.7, S12.4 |
| Deployment (Docker, CI/CD, IaC, sizing, backups) | ✅ S0, S12 |
| v2.0-deferred items (What-If, PPTX, Heat Maps, multi-tenant billing) | ✅ Correctly excluded from this plan |
| Removed features (14) | ✅ Verified absent from all sprints |

**Result: 100% of MVP v1.0 + v1.1 spec scope is mapped to a sprint with an owner. No orphaned features. No scope from removed/v2.0 lists leaked in.**

---

## 15. SUMMARY TIMELINE

```
Weeks 1–2    S0   Foundation: repo, Docker, schema, CI, skeleton          ── M0
Weeks 3–4    S1   Auth, RBAC, tenancy, connections, circuit breakers
Weeks 5–6    S2   Discovery engine, metadata catalog, golden dataset      ── M1
Weeks 7–8    S3   Semantic layer + SAP B1 pack + MSSQL fingerprinting
Weeks 9–10   S4   Knowledge graph + tool generation + 50-tool pack
Weeks 11–12  S5   Embeddings, ranking, custom tools                       ── M2
Weeks 13–14  S6   Runtime core: Supervisor, Intent, Context, Retrieval, KG
Weeks 15–16  S7   Planner, Tool Exec, SQL Agent + security suite
Weeks 17–18  S8   Document RAG + Web Search Agent
Weeks 19–20  S9   Analytics, Confidence, Synthesis, streaming             ── M3
Weeks 21–22  S10  Conversation UX, charts, lineage, accessibility
Weeks 23–24  S11  Dashboards, exports, onboarding, admin, SSO             ── M4
Weeks 25–26  S12  Prod infra, performance, pen-test, compliance
Weeks 27–28  S13  UAT, pilot, LAUNCH MVP v1.0                             ── M5 🚀
Weeks 29–30  S14  Proactive Intelligence + Alert Centre        (v1.1)
Weeks 31–32  S15  Learning loop + Report scheduler/delivery    (v1.1)
Weeks 33–34  S16  Forecast + digest + v1.1 RELEASE                        ── M6 🚀
```

---

*Plan Version: 1.0 FINAL (post cross-check, 5 fixes applied)*
*Aligned to: Production Specification v2.0 (Green-Flagged)*
*Prepared by: Principal Engineer / Platform Architect — June 2026*
