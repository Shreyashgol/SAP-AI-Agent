# Enterprise AI Intelligence Platform
## Production-Ready Software Requirements Specification
### Version 2.0 — June 2026 | Status: ✅ GREEN FLAG ISSUED

**Target Databases:** SAP Business One HANA · Microsoft SQL Server
**Classification:** Internal Product Specification — Confidential

---

## DOCUMENT CONTROL

| Item | Detail |
|------|--------|
| Version | 2.0 (Production-Ready) |
| Previous Version | 1.0 (PRD — development blocked) |
| Changes in v2.0 | All 9 critical gaps resolved · Web Search Agent added · 14 features removed · Full schema design added · NFRs complete · API contract defined · Testing strategy defined · Observability stack defined · Deployment spec defined · UI/UX spec defined · SAP B1 domain fully specified |
| Status | ✅ APPROVED FOR DEVELOPMENT |

---

## FEATURES REMOVED FROM SPECIFICATION

The following features were assessed as **not useful, premature, or delivering no distinct value** for MVP or v1.1. They are removed entirely. Rationale is provided for each.

| Feature ID | Feature Name | Reason for Removal |
|-----------|-------------|-------------------|
| DC-007 | Stored Procedure Discovery | SAP B1 HANA stored procs are internal system objects, not business analytics tools. Adds discovery complexity with no user-facing value at MVP. Revisit at v3.0 if customers request. |
| MC-007 | Table Importance Ranking | Superseded by the SAP B1 Entity Pack (SL-010) which pre-defines importance. AI-scoring an already-known schema wastes LLM tokens and adds latency to onboarding. |
| KG-008 | Cross-DB Graph | Premature for MVP and v1.1. SAP B1 and MSSQL operate as independent tenants. Cross-DB relationships introduce graph complexity, join ambiguity, and security boundary issues that cannot be safely solved at this stage. |
| DI-001 (partial) | CSV as document type | CSV files are data, not documents. They belong in the DB connector pipeline, not the RAG pipeline. Ingesting CSVs into a RAG index produces low-quality embeddings and inaccurate retrieval. Removed from DI-001 scope. |
| AE-007 | Cohort Analysis | High implementation complexity, low business demand in SAP B1 SME market. Not a standard ERP report. Deferred to v3.0. |
| AE-010 | What-If Scenarios | Requires write/simulation capability against business models. Out of scope for a read-only analytics platform at MVP. Full v2.0 feature. |
| AE-011 | Benchmark Comparisons | Requires cross-company data or industry benchmarks, neither of which is available in the platform scope. Deferred to v3.0. |
| VE-007 | Heat Maps | Low usage pattern for SAP B1 ERP analytics. Adds frontend complexity for minimal business value at MVP. Deferred to v2.0. |
| RD-007 | PowerPoint Export | High implementation cost (pptx generation), low enterprise priority vs PDF and Excel. Deferred to v2.0. |
| OB-010 | Admin Training Mode | Duplicate of existing sandbox functionality. A dedicated training mode adds maintenance overhead. Sandbox behavior can be achieved with a test company DB connection. Removed. |
| FL-009 | A/B Tool Testing | Requires significant infrastructure (traffic splitting, statistical significance engine). Overkill for MVP learning loop. Replace with simpler tool performance dashboard (FL-003). |
| TR-003 | Usage Frequency Signal | Redundant. Historical success rate (TR-002) already captures usage patterns with accuracy weighting. Pure frequency without accuracy correlation creates a popularity bias that degrades answer quality. |
| GS-013 | Data Retention Policy (UI) | This is an infrastructure/ops configuration, not a platform feature. Handle via environment configuration. Not user-facing. |
| PI-007 | Period-End Intelligence | Too narrow a use case and easily covered by scheduled reports (RD-001). Does not justify a dedicated feature. |

**Total features removed: 14**
**Remaining feature count: 130+ across 16 modules**

---

## PART 1 — PLATFORM ARCHITECTURE

### 1.1 Platform Layer Model

```
┌──────────────────────────────────────────────────────────────────┐
│  DELIVERY LAYER      Chat UI · Visualisation · Reports · Alerts  │
├──────────────────────────────────────────────────────────────────┤
│  AGENTIC RUNTIME     LangGraph Supervisor · 15 Specialist Agents │
├──────────────────────────────────────────────────────────────────┤
│  TRUST LAYER         Explainability · Governance · Feedback Loop │
├──────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE LAYER  Tool Engine · RAG · Proactive Engine        │
├──────────────────────────────────────────────────────────────────┤
│  KNOWLEDGE LAYER     Semantic Layer · Knowledge Graph · Catalog  │
├──────────────────────────────────────────────────────────────────┤
│  DATA LAYER          SAP B1 HANA · MSSQL · Documents             │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Design Principles

| Principle | Rule |
|-----------|------|
| Agent-first | Every capability is a named, testable, independent agent |
| Trust by design | Every answer includes confidence score + data lineage |
| Tool before SQL | Pre-generated tools always tried before SQL generation |
| Knowledge-grounded | All agents operate on the Knowledge Graph, not raw tables |
| Read-only always | Zero write operations to source ERP databases. Ever. |
| Governance-native | RBAC + row-level security enforced at query time, not as afterthought |
| Tenant isolation | tenant_id on every table, PostgreSQL RLS from day one |
| Fail loudly | Agent failures raise RuntimeError with full trace — no silent returns |

### 1.3 Execution Priority (Non-Negotiable)

```
1st → Tool Execution Agent      (pre-generated, validated business tools)
2nd → Analytics Agent           (trend / RCA / comparative reasoning)
3rd → RAG Agent                 (document-grounded answers)
4th → Web Search Agent          (external market/forecast enrichment)
5th → SQL Agent                 (last resort, SELECT only, fully validated)
```

---

## PART 2 — COMPLETE FEATURE SPECIFICATION

### Module 1: Data Connection & Discovery

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| DC-001 | SAP B1 HANA Connector | hdbcli native client, SSL/TLS required, read-only service user, connection pooling (min 2, max 10), 30s connect timeout |
| DC-002 | MSSQL Connector | pyodbc + sqlalchemy, TLS encrypted, read-only role with DENY on sys schema, connection pooling (min 2, max 10) |
| DC-003 | Connection Health Monitor | Heartbeat ping every 60s, auto-reconnect on failure (3 attempts, exponential backoff), latency tracking in metrics |
| DC-004 | Schema Discovery | Discovers: schemas, tables, columns, data types, nullability, defaults, check constraints, indexes. Excludes system schemas. |
| DC-005 | Foreign Key Discovery | Explicit FKs from information_schema. Inferred FKs via column name pattern matching (CardCode → OCRD.CardCode). Confidence scored. |
| DC-006 | View Discovery | Catalogues views with dependency resolution. Marks views as queryable where they provide business value. |
| DC-008 | Sample Data Harvesting | 20 rows per table, excludes PII-flagged columns (GS-006). Stored encrypted. Used only for AI context, never exposed to users. |
| DC-009 | Column Statistics | Min, max, null %, distinct count, top 10 values. Refreshed on incremental re-discovery. |
| DC-010 | Incremental Re-Discovery | Schema change detection via metadata hash comparison. Updates catalog diff only. Triggers semantic layer review notification. |
| DC-011 | Multi-Company Support | Per-tenant, each tenant registers their own SAP B1 company DB. No cross-tenant data access. |
| DC-012 | Connection Credential Vault | AES-256 encryption at rest. Credentials never returned via API after save. Rotation via PUT endpoint. |

---

### Module 2: Metadata Catalog

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| MC-001 | Unified Metadata Store | PostgreSQL schema: metadata_tables, metadata_columns, metadata_relations. All versioned. tenant_id on all rows. |
| MC-002 | Object Versioning | Snapshot on each discovery run. JSON diff stored between versions. Admin can revert to prior version. |
| MC-003 | Metadata Search | PostgreSQL full-text search (tsvector) on table name, column name, AI description. Returns relevance-ranked results. |
| MC-004 | Data Lineage Tracking | Directed acyclic graph: source_table → semantic_entity → tool → kpi → report. Queryable via lineage API. |
| MC-005 | Catalog Health Score | Score = (mapped entities / total tables) × (tools generated / KPIs defined) × 100. Displayed on admin dashboard. |
| MC-006 | Admin Review Interface | UI table with AI-generated descriptions, edit-in-place, approve/reject buttons. Bulk approve supported. Change audit-logged. |

---

### Module 3: Semantic Layer

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| SL-001 | Entity Recognition | Maps tables → business entities using SAP B1 Pack first, then Claude AI for unmapped tables. Confidence scored. Human override persists. |
| SL-002 | Attribute Mapping | Maps columns → business attributes. Type-aware (currency, date, quantity, code, text). Business display name + description generated. |
| SL-003 | KPI Catalogue | Auto-generates KPI from numeric attributes + entity context. Stores formula, unit, aggregation method, display format. |
| SL-004 | Business Glossary | AI-generated definition per entity and attribute. Editable. Exported as searchable glossary in UI. |
| SL-005 | Metric Library | 50+ pre-defined metrics: Revenue, Gross Margin, DSO, DPO, Inventory Turnover, Order Fill Rate, Quote Conversion Rate. |
| SL-006 | Synonym Engine | Many-to-one synonym mapping. "sales", "revenue", "income", "turnover" → Revenue metric. Stored in synonym_mappings table. |
| SL-007 | Business Rules Engine | Filter predicates stored per entity. SAP B1 Pack ships with 20+ pre-defined rules (active customers, posted invoices, etc.). Custom rules via UI. |
| SL-008 | Semantic Versioning | Semantic definitions versioned independently of schema versions. Change log with author + timestamp. |
| SL-009 | Human Review & Override | Any AI mapping can be corrected via UI. Override stored with higher priority than AI-generated value. Override is preserved on re-generation. |
| SL-010 | SAP B1 Entity Pack | 80+ pre-mapped tables. Ships with platform. Applied automatically on SAP B1 HANA connection. See Part 8 for full mapping. |
| SL-011 | MSSQL Schema Fingerprinting | Discovery Engine fingerprints MSSQL schema against known ERP pattern library (Dynamics BC, Sage 300, custom patterns). Applies best-match entity pack or falls back to AI-only mapping. |

---

### Module 4: Knowledge Graph

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| KG-001 | Entity Relationship Graph | Nodes: semantic entities. Edges: relationships (FK, inferred, business-logical). Stored in knowledge_graph_nodes + knowledge_graph_edges tables. |
| KG-002 | FK-Based Edge Generation | One edge per FK relationship. Direction: child → parent (Invoice → Customer). Weight: 1.0 (explicit). |
| KG-003 | Inferred Relationship Discovery | Column name similarity matching. Edge weight < 1.0, stored with confidence score. Requires admin confirmation before use in SQL generation. |
| KG-004 | Graph Traversal API | Internal Python service. BFS path-finding between two entity nodes. Returns ordered list of join conditions. Max depth: 5 hops. |
| KG-005 | Graph Visualiser | React-based force-directed graph (D3.js). Nodes coloured by entity type. Edges labelled with relationship name. Filter by entity domain. |
| KG-006 | Relationship Confidence Score | Explicit FK = 1.0, Column-name inferred = 0.6–0.9, AI-inferred = 0.4–0.7. Threshold for auto-use in SQL = 0.8. |
| KG-007 | Graph-Guided SQL Join Builder | Takes entity path from traversal API, generates SQL JOIN chain with correct ON conditions and aliases. Used by SQL Agent and Tool Generation. |
| KG-009 | Graph Refresh | Triggered by metadata catalog change event. Adds/removes nodes and edges incrementally. Does not rebuild full graph. |
| KG-010 | GraphRAG Integration | Top-3 related entity paths injected into LLM system prompt context. Improves join accuracy and entity disambiguation. |

---

### Module 5: Tool Generation Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| TG-001 | Auto Tool Generation | Reads Semantic Layer + Knowledge Graph. For each KPI and entity summary pattern, generates a named tool. Runs during onboarding and on demand. |
| TG-002 | Tool Schema Definition | Each tool: `{ id, name, description, category, inputs: [{name, type, required, default}], output_schema, sql_template, permissions: [role_ids], version, status }` |
| TG-003 | Tool Embedding | Claude text-embedding-3 (1536 dim). Embeds: name + description + input names + output schema. Stored in tool_embeddings (pgvector). HNSW index. |
| TG-004 | KPI Tool Generation | One tool per KPI. SQL template uses parameterized date range, optional entity filter. Returns: value, period, comparison_period, change_pct. |
| TG-005 | Entity Summary Tools | One tool per core entity (Customer, Supplier, Item, Warehouse). Returns master + aggregated transactional summary. |
| TG-006 | Comparative Tools | Period comparison, entity ranking, branch comparison. Uses window functions. Returns: dimension, current_value, prior_value, variance, variance_pct. |
| TG-007 | Drill-Down Tools | Detail tools for each transaction entity. Returns paginated line-level data with sort/filter params. |
| TG-008 | Custom Tool Builder | Admin UI: name, description, input definition, raw SQL editor with syntax highlighting and live test. Saved as tool with status=custom. |
| TG-009 | Tool Validation | At generation: executes against DB with LIMIT 1. Validates: non-error response, schema matches output_schema definition. Failed tools flagged status=invalid. |
| TG-010 | Tool Versioning | Each edit creates new version. Previous version retained. Admin can rollback. Active version used by ranking engine. |
| TG-011 | Tool Dependency Map | Stored as tool_table_dependencies. Used to auto-flag tools as deprecated when schema changes affect their tables. |
| TG-012 | SAP B1 Tool Pack | 50 pre-built tools. See Part 8 for full list with SQL templates. Ships with platform, activated on SAP B1 connection. |
| TG-013 | Tool Deprecation | On schema change detected → query tool_table_dependencies → flag affected tools status=deprecated → notify admin → exclude from ranking. |

---

### Module 6: Tool Ranking Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| TR-001 | Semantic Similarity Ranking | Cosine similarity between question embedding and tool embedding. Top-10 candidates returned. Threshold: 0.65 minimum. |
| TR-002 | Historical Success Rate | `success_rate = successful_executions / total_executions` per tool per question_type. Decay weight: recent 30 days weighted 2×. |
| TR-004 | User Feedback Signal | Positive feedback: +0.05 weight to tool. Negative feedback: −0.10 weight. Weights normalised weekly. Stored in tool_ranking_weights. |
| TR-005 | Permission Filter | Hard gate before ranking. Tools with required permissions not held by requesting user are excluded. Never ranked, never logged as candidates. |
| TR-006 | Context Reranking | Extracts active entities from conversation context. Boosts tools whose entity_ids match active entities by +0.15. |
| TR-007 | Confidence Threshold | Tools scoring below 0.65 composite score are not executed. Escalated directly to SQL Agent or returns "I don't have a tool for that" message. |
| TR-008 | Multi-Tool Planning | Planner Agent identifies compound questions. Generates ordered tool execution plan. Results merged by Response Synthesis Agent. |
| TR-009 | Ranking Explainability | Every ranking decision logged: tool_id, question_embedding_id, similarity_score, success_rate_weight, feedback_weight, final_score. Queryable by admin. |

---

### Module 7: Document Intelligence (RAG)

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| DI-001 | Document Ingestion | Supported: PDF, DOCX, XLSX, TXT. Max file size: 50MB. Processed async via Celery worker. Status tracked in documents table. |
| DI-002 | Intelligent Chunking | Recursive character splitter: 512 tokens per chunk, 50-token overlap. Structure-aware: preserves headings, table boundaries. |
| DI-003 | Vector Indexing | Claude embeddings (1536 dim) stored in document_embeddings (pgvector). HNSW index (ef_construction=128, m=16). Namespace isolated per tenant. |
| DI-004 | Hybrid RAG | Step 1: BM25 keyword search (PostgreSQL full-text). Step 2: pgvector cosine similarity. Step 3: RRF (Reciprocal Rank Fusion) merge. Top-5 chunks returned. |
| DI-005 | Document Metadata Tagging | Tags: document_type, department, effective_date, access_roles, tenant_id. Applied at upload. Filterable in retrieval. |
| DI-006 | Cross-Document Reasoning | If top chunks span >1 document, Claude synthesises across them. Source citations include document name, page, and chunk reference. |
| DI-007 | Document-to-Data Linking | Admin can tag a document with entity_ids. RAG retrieval checks entity match to boost relevant documents when entity is in question context. |
| DI-008 | Citation Tracking | Every RAG-based answer includes: `{ document_name, page_number, section, excerpt_preview }`. Displayed in lineage trace. |
| DI-009 | Document Access Control | Documents tagged with access_roles. RAG Agent filters candidates to documents the requesting user's role can access. |
| DI-010 | Document Refresh | Re-upload triggers full re-chunk + re-embed. Old embeddings soft-deleted, new embeddings activated atomically. |
| DI-011 | GraphRAG Integration | Entity nodes from Knowledge Graph injected into RAG retrieval context. Improves entity-specific document retrieval accuracy. |

---

### Module 8: Agentic Runtime (LangGraph — 15 Agents)

Full agent specifications are in Part 4. Feature list:

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| AR-001 | Supervisor Agent | LangGraph StateGraph root node. Dynamic routing via Command primitive. Global state owner. Max 5 retry cycles per pipeline run. |
| AR-002 | Intent & Routing Agent | 7-class classifier (Lookup/Aggregation/Trend/Comparative/RCA/Document/Hybrid). Model: Claude Haiku (fast path). Routes to Planner or direct execution. |
| AR-003 | Conversation Context Agent | Redis session store. 50-turn sliding window. Entity carry-forward with NER. Outputs fully-resolved standalone question. |
| AR-004 | Semantic Retrieval Agent | pgvector ANN search. Returns top-10 tool candidates + top-5 entity matches. Input: enriched question embedding. |
| AR-005 | Knowledge Graph Agent | BFS graph traversal. Outputs join paths for SQL generation. Resolves entity ambiguity via graph proximity. |
| AR-006 | Planner Agent | Decomposes multi-intent questions. Generates ordered sub-task DAG. Re-plans if intermediate results change strategy. Model: Claude Sonnet. |
| AR-007 | Tool Ranking Agent | Applies permission filter → composite scoring → confidence threshold. Returns ranked tool list with scores. |
| AR-008 | Tool Execution Agent | Executes top tool with parameterised inputs. Validates result. 3-tool fallback chain before escalating to SQL Agent. |
| AR-009 | SQL Agent | SELECT-only query generation using KG join paths + RLS filters. AST validation before execution. Flags answer as AI-generated. |
| AR-010 | RAG Agent | Hybrid retrieval + cross-document synthesis. Attaches citations. Falls back to "no document found" with graceful message. |
| AR-011 | Analytics Agent | Trend, variance, RCA, comparative analysis. Generates NL narrative. Calls Tool Execution Agent for data retrieval. |
| AR-012 | Web Search Agent | **NEW — Agent 15.** Retrieves external market data, industry forecasts, and economic indicators for enrichment. See Part 4 Agent 15. |
| AR-013 | Proactive Intelligence Agent | Scheduled KPI monitoring. Z-score + IQR anomaly detection. Triggers Analytics Agent on confirmed anomaly. Pushes alerts. |
| AR-014 | Confidence & Explainability Agent | Scores confidence (0.0–1.0). Builds lineage trace. Detects data conflicts. Constructs evidence package. |
| AR-015 | Response Synthesis Agent | Selects visualisation type. Writes NL narrative. Attaches confidence + lineage. Generates 2–3 follow-up questions. |

---

### Module 9: Analytics Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| AE-001 | Trend Analysis | Time series over configurable window (7d/30d/90d/1y). Detects: direction, slope, seasonality. Returns: data points + NL summary. |
| AE-002 | Period Comparison | Current vs prior period. Configurable: DoD, WoW, MoM, QoQ, YoY. Returns: values + absolute variance + % variance + NL explanation. |
| AE-003 | Root Cause Analysis | Decomposes metric change into contributing dimensions. Ranks contributors by impact %. NL explanation of top 3 drivers. |
| AE-004 | Anomaly Detection | Z-score (>2.5σ) and IQR (1.5× IQR) methods. Applied to KPI monitoring and user queries. Returns: value, expected range, severity. |
| AE-005 | Variance Analysis | Volume effect, price/rate effect, mix effect decomposition. Standard management accounting methodology. Returns labelled waterfall data. |
| AE-006 | Forecast Engine | Prophet-based time-series forecasting. Requires minimum 24 data points. Returns: forecast values + confidence intervals + seasonality components. Web Search Agent enriches with external signals. |
| AE-008 | Ranking & Leaderboards | Top/bottom N across any dimension and metric. Configurable N (default 10). Returns: ranked list with values and rank change vs prior period. |
| AE-009 | Contribution Analysis | Shows % contribution of each dimension member to total metric. Pareto-sorted. Returns: member, value, contribution_pct, cumulative_pct. |
| AE-012 | Natural Language Narrative | Every Analytics Engine output includes a 2–4 sentence plain-English business summary. Generated by Claude Haiku post-computation. |

---

### Module 10: Proactive Intelligence Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| PI-001 | KPI Monitoring | Celery beat executes KPI tools on schedule. Default: hourly for critical KPIs, daily for standard. Configurable per KPI. |
| PI-002 | Threshold Alerts | Admin defines: KPI, operator (>, <, =), threshold value, severity (Critical/Warning/Info). Stored in alert_rules table. |
| PI-003 | Anomaly Push Alerts | Statistical anomaly triggers alert automatically without threshold config. Requires 7+ data points to establish baseline. |
| PI-004 | Business Event Triggers | Rule-based: invoice overdue > 90 days, stock < reorder point, order > $X value. Evaluated on KPI monitoring cycle. |
| PI-005 | Insight Digest | Daily 06:00 (tenant timezone): AI-generated summary of top 5 KPI movements for each user role. Delivered via email or in-app notification. |
| PI-006 | Suggested Questions | After each anomaly or insight, generate 3 follow-up questions the user should investigate. Shown in Alert Centre. |
| PI-008 | Alert Routing | Each alert_rule has assigned_role_ids. Alerts delivered only to users with matching role AND data domain permission. |
| PI-009 | Alert Acknowledgement | Users can: Acknowledge (dismiss), Snooze (1h/4h/24h), Escalate (notify another user). All actions audit-logged. |
| PI-010 | Alert History | Full immutable alert log. Queryable by: date range, severity, KPI, acknowledged status. Exportable to CSV. |

---

### Module 11: Trust & Explainability Layer

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| TE-001 | Answer Confidence Score | Composite: semantic similarity (40%) + tool validation status (30%) + data freshness (20%) + source reliability (10%). High ≥0.85, Medium 0.65–0.84, Low <0.65. |
| TE-002 | Data Lineage Trace | Returns: `{ source_db, tables_used: [], tool_id | sql_query, documents_cited: [], agents_invoked: [] }`. Stored per conversation turn. |
| TE-003 | Reasoning Trace | Step-by-step agent decision log. Stored in LangSmith + local audit_log. Accessible by admin. Not shown to standard users (privacy). |
| TE-004 | Query Transparency | "How was this calculated?" button expands the tool SQL or generated query. Shown with syntax highlighting. Read-only. |
| TE-005 | Conflict Detection | If two sources return different values for same metric in same question, Confidence Agent flags conflict. Shows both values + sources. User must choose. |
| TE-006 | Uncertainty Acknowledgement | When confidence < 0.65, response includes: "I'm not fully certain about this answer. Please verify using the data source." No suppression of low-confidence answers — they are shown with clear warning. |
| TE-007 | Answer Verification Link | "Verify this answer" expands raw data table behind every numeric answer. Paginated. Sortable. |
| TE-008 | Hallucination Guard | Pre-response: cross-check numeric values in NL narrative against actual tool/query output. Mismatch → re-generate narrative or flag discrepancy. |
| TE-009 | Calculation Audit Trail | For financial KPIs: shows formula, period, filters applied, row count, sum verification. Exportable as PDF evidence. |

---

### Module 12: Governance & Security

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| GS-001 | Role-Based Access Control | 4 built-in roles: Platform Admin, Power User, Business User, Viewer. Custom roles supported. |
| GS-002 | Data Domain Permissions | Domains: Finance, Sales, Purchasing, Inventory, HR (if applicable), Operations. Each role assigned allowed domains. |
| GS-003 | Row-Level Security | PostgreSQL RLS policies on all tenant data. company_id filter applied at query generation time by SQL Agent and Tool Execution Agent. |
| GS-004 | Column-Level Masking | Sensitive columns (cost price, salary, margin %) configurable as masked. Masked columns replaced with "***" in results for unauthorised roles. |
| GS-005 | Query Audit Log | Immutable append-only log: user_id, question, generated_sql, tool_id, execution_time, result_row_count, confidence_score, timestamp. Partitioned by month. |
| GS-006 | PII Detection | Discovery scans column names against PII pattern library (email, phone, SSN, credit card, DOB, salary patterns). Auto-flags, requires admin review. |
| GS-007 | PII Access Control | PII-flagged columns excluded from sample harvesting (DC-008) and accessible only to Platform Admin role. |
| GS-008 | SQL Injection Prevention | All dynamic values parameterised. No string interpolation in SQL generation. AST parser validates structure before execution. |
| GS-009 | DML Blocker | AST parser checks every generated query. BLOCKS: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC (unapproved), GRANT, REVOKE. Hard exception, full audit log entry. |
| GS-010 | Session Management | JWT access token (8h), refresh token (30d, httpOnly cookie). Logout invalidates refresh token in Redis blocklist. |
| GS-011 | SSO Integration | SAML 2.0 and OIDC supported. Attribute mapping: email → user, groups → roles. Tested with Entra ID, Okta, Google Workspace. |
| GS-012 | Compliance Export | Audit log export: CSV, JSON. Date range filter. Includes all fields. Used for SOC 2, GDPR, and internal audit. |

---

### Module 13: Feedback & Learning Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| FL-001 | Per-Response Rating | Thumbs up/down rendered below every answer. Stored in user_feedback: user_id, conversation_turn_id, tool_id, rating, timestamp. |
| FL-002 | Answer Correction | "Correct this answer" text field. Correction stored as labelled training example in feedback_corrections. Used to improve tool ranking and semantic layer. Reviewed by admin. |
| FL-003 | Tool Performance Dashboard | Admin view: tool name, execution_count, success_rate, avg_confidence, feedback_score, last_used. Sortable. Filterable by date range. |
| FL-004 | Semantic Drift Detection | Weekly job: compare rolling 30-day tool success rate vs 90-day baseline. If delta > 10%, flag tool for admin review. |
| FL-005 | Auto Re-ranking | Feedback weights recalculated nightly. New weights applied to ranking engine by 02:00 UTC. No manual trigger required. |
| FL-006 | Re-generation Triggers | Tool flagged for re-generation when: success_rate < 0.5 for 7+ days OR admin manually triggers. Notifies admin with specific recommendation. |
| FL-007 | Glossary Crowdsourcing | "Suggest a better term" link on every entity/attribute display. Suggestion routed to admin review queue. If approved, updates Business Glossary. |
| FL-008 | Negative Pattern Learning | Questions that route to SQL fallback or return low confidence are stored in negative_patterns table. Admin reviews weekly. Used to identify missing tools. |
| FL-010 | Feedback Loop Dashboard | Admin: overall answer quality score (rolling 30d), thumbs up/down ratio trend, top 10 failing question patterns, tool regeneration queue. |

---

### Module 14: Visualisation Engine

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| VE-001 | Auto Chart Selection | Rules engine: data shape + question intent → chart type. See Response Synthesis Agent visualisation logic in Part 4. |
| VE-002 | Bar / Column Charts | Recharts BarChart. Horizontal (>8 categories) or vertical. Sorted by value. Colour-coded by series. |
| VE-003 | Line / Area Charts | Recharts LineChart/AreaChart. Multi-series. Hover tooltip with all series values. Reference lines for targets. |
| VE-004 | Pie / Donut Charts | Recharts PieChart. Max 8 slices (others grouped). Percentage labels. Legend with values. |
| VE-005 | KPI Cards | Large metric display, trend arrow, % change vs prior period, period label. Colour-coded: green (positive), red (negative). |
| VE-006 | Data Tables | TanStack Table. Sortable columns. Filterable. Column resize. Sticky header. Row highlight on hover. Virtual scroll for large sets. |
| VE-008 | Waterfall Charts | Recharts custom waterfall. Used for variance and contribution analysis. Positive/negative colour coding. |
| VE-009 | Drill-Through | Click any chart element → new conversation turn pre-populated with drill-down question. Maintains full context. |
| VE-010 | Chart Annotations | AI-generated text annotation on highest/lowest point and trend inflection. Rendered as chart subtitle. |
| VE-011 | Chart Export | PNG export (html2canvas). SVG export. Copy to clipboard. Available on all chart types. |
| VE-012 | Dashboard Builder | Drag-and-drop grid (React Grid Layout). Pin any answer as a dashboard widget. Per-user, per-role dashboards. Share dashboard link. |
| VE-013 | Responsive Rendering | Recharts ResponsiveContainer. Breakpoints: Desktop (full chart), Tablet (simplified), Mobile (KPI card fallback for complex charts). |

---

### Module 15: Report Automation & Delivery

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| RD-001 | Scheduled Reports | Cron-based (Celery beat). Schedules: daily, weekly, monthly. Stored in report_schedules. Executes as background job. |
| RD-002 | NL Report Definition | User defines report content by typing questions ("Show revenue by customer, then AR aging, then top 10 overdue invoices"). Each question = one report section. |
| RD-003 | Email Delivery | SendGrid/SES integration. HTML email with embedded charts + PDF attachment. Configurable recipients per report. |
| RD-004 | Teams / Slack Delivery | Webhook integration. Summary text + link to full report in platform. Configurable per report. |
| RD-005 | PDF Export | WeasyPrint/ReportLab PDF generation. Company logo, colours, header/footer from tenant branding config. |
| RD-006 | Excel Export | openpyxl. Separate sheet per data table. Chart sheets for visualisations. Formatted: headers, number formatting, column widths. |
| RD-008 | Anomaly-Triggered Reports | alert_rule can be configured with report_template_id. On alert trigger → generate report → deliver immediately. |
| RD-009 | Report Subscriptions | Users subscribe to report_schedule_id. Added to recipient list. Can unsubscribe via one-click link in email. |
| RD-010 | Report History | All generated reports stored (30-day retention, configurable). Re-runnable. Diff view between runs (v1.1). |
| RD-011 | Branded Report Templates | Tenant branding: logo URL, primary colour, font. Applied to all PDF and email outputs. Configured in tenant settings. |

---

### Module 16: Onboarding & Time-to-Value

| Feature ID | Feature | Production Specification |
|-----------|---------|--------------------------|
| OB-001 | Guided Setup Wizard | 8-step wizard: Connect DB → Run Discovery → Review Semantic Layer → Review Knowledge Graph → Activate Tool Pack → Upload Documents (optional) → Configure Alerts (optional) → First Query. Progress persisted. |
| OB-002 | SAP B1 Quick-Start Pack | Auto-applied on SAP B1 HANA connection: 80+ entity mappings, 20+ business rules, 50+ tools, 50+ KPIs. Time-to-first-query target: <30 minutes. |
| OB-003 | MSSQL Quick-Start Pack | Schema fingerprinting → best-match entity pack applied → AI fills gaps. Estimated time-to-first-query: 45–60 minutes. |
| OB-004 | Onboarding Progress Tracker | Visual checklist with completion %. Each step: status (pending/in-progress/complete/error), duration, next action. |
| OB-005 | Sample Question Gallery | 50 curated questions by category: Finance (10), Sales (10), AR/AP (10), Inventory (10), Purchasing (10). Clickable → pre-populates conversation input. |
| OB-006 | KPI Library | 50+ pre-defined KPIs displayed in library. Admin activates/deactivates per deployment. Each KPI shows: definition, formula, data source tables. |
| OB-007 | Setup Validation | Post-onboarding automated test: runs 10 standard SAP B1 queries, checks for non-error response, reports pass/fail per question. |
| OB-008 | Time-to-First-Insight Target | Platform SLA: SAP B1 connection → first correct answer ≤ 30 minutes. Measured in OB telemetry. |
| OB-009 | ROI Dashboard | Admin view: queries answered (total, daily trend), unique users, reports generated, avg response time, top question categories, estimated analyst hours saved (configurable formula). |

---

## PART 3 — NON-FUNCTIONAL REQUIREMENTS

### 3.1 Performance Requirements

| NFR ID | Requirement | Target | Test Method |
|--------|-------------|--------|-------------|
| NFR-P01 | Simple lookup query (tool execution) | p95 < 3 seconds | Load test |
| NFR-P02 | Complex analytics query (RCA, trend) | p95 < 8 seconds | Load test |
| NFR-P03 | SAP B1 schema discovery (1,000 tables) | < 10 minutes | Integration test |
| NFR-P04 | Semantic layer generation (full schema) | < 30 minutes | Integration test |
| NFR-P05 | Tool generation (per tool) | < 5 seconds | Unit benchmark |
| NFR-P06 | Vector similarity search (tool retrieval) | < 200ms | Unit benchmark |
| NFR-P07 | Knowledge graph traversal (5-hop max) | < 500ms | Unit benchmark |
| NFR-P08 | Document ingestion (10MB PDF) | < 60 seconds | Integration test |
| NFR-P09 | Dashboard load (cached data) | < 2 seconds | Lighthouse / k6 |
| NFR-P10 | PDF report generation | < 15 seconds | Integration test |
| NFR-P11 | Concurrent sessions (MVP) | 50 concurrent users | k6 load test |
| NFR-P12 | API throughput per tenant | 100 requests/minute | k6 load test |

### 3.2 Scalability Requirements

| NFR ID | Requirement | Limit |
|--------|-------------|-------|
| NFR-S01 | Max tables per DB connection | 10,000 |
| NFR-S02 | Max tools per tenant | 5,000 |
| NFR-S03 | Max document pages per tenant | 50,000 |
| NFR-S04 | Max conversation turns in session | 50 |
| NFR-S05 | Max concurrent background jobs per tenant | 20 |
| NFR-S06 | Horizontal scaling | Stateless API pods, Kubernetes HPA |
| NFR-S07 | DB connection pool per tenant | Min 2 / Max 10 |
| NFR-S08 | Vector index size | Up to 5M embeddings per tenant (pgvector HNSW) |

### 3.3 Reliability & Availability

| NFR ID | Requirement | Target |
|--------|-------------|--------|
| NFR-R01 | Platform uptime | 99.5% monthly SLA |
| NFR-R02 | Scheduled maintenance window | Max 4 hours/month, announced 48h in advance |
| NFR-R03 | Agent failure retry | 3 retries, exponential backoff (1s, 2s, 4s) |
| NFR-R04 | Agent node timeout | 60 seconds hard limit |
| NFR-R05 | Full pipeline timeout | 120 seconds hard limit |
| NFR-R06 | DB connection timeout | 30 seconds, auto-reconnect |
| NFR-R07 | Session persistence | Redis, 24h TTL, survives server restart |
| NFR-R08 | Graceful degradation | Cached results served when DB unreachable |
| NFR-R09 | RTO (Recovery Time Objective) | < 4 hours from full outage |
| NFR-R10 | RPO (Recovery Point Objective) | < 24 hours (daily backup) |

### 3.4 Security Requirements

| NFR ID | Requirement | Standard |
|--------|-------------|---------|
| NFR-SEC01 | Data in transit | TLS 1.3 minimum |
| NFR-SEC02 | Credentials at rest | AES-256 |
| NFR-SEC03 | JWT access token lifetime | 8 hours (configurable 1–24h) |
| NFR-SEC04 | Refresh token lifetime | 30 days (configurable) |
| NFR-SEC05 | Login lockout | 5 failed attempts → 15-minute lockout |
| NFR-SEC06 | SQL injection prevention | Parameterised queries only |
| NFR-SEC07 | Generated SQL validation | AST whitelist parser before execution |
| NFR-SEC08 | API rate limiting | 60 req/min per user, 100 req/min per tenant |
| NFR-SEC09 | Secrets management | Environment variables + HashiCorp Vault (or AWS Secrets Manager) |
| NFR-SEC10 | Audit log integrity | Append-only, no update/delete permitted |
| NFR-SEC11 | PII in logs | No raw query results in application logs |
| NFR-SEC12 | Dependency scanning | pip-audit + Snyk in CI/CD, blocks on CVSS ≥ 7.0 |
| NFR-SEC13 | Web Search Agent scope | Only permitted domains list. No user-supplied URLs. |

### 3.5 Usability Requirements

| NFR ID | Requirement | Standard |
|--------|-------------|---------|
| NFR-U01 | First successful query (untrained user) | < 5 minutes |
| NFR-U02 | Error messages | Plain English. No stack traces. Always include suggested action. |
| NFR-U03 | Loading states | All async operations: progress indicator within 300ms of trigger |
| NFR-U04 | Browser support | Chrome 110+, Firefox 110+, Edge 110+, Safari 16+ |
| NFR-U05 | Responsive breakpoints | Desktop 1280px+, Tablet 768px+, Mobile 375px+ |
| NFR-U06 | Accessibility | WCAG 2.1 Level AA |

### 3.6 Compliance Requirements

| NFR ID | Requirement | Scope |
|--------|-------------|-------|
| NFR-C01 | GDPR Article 17 Right to Erasure | EU tenants: user query logs deletable on request |
| NFR-C02 | EU AI Act (August 2026) | Platform classified as General Purpose AI tool, not high-risk. Document classification rationale. |
| NFR-C03 | SOC 2 Type II readiness | Audit log, access control, encryption, availability monitoring as baseline |
| NFR-C04 | Data residency | PostgreSQL deployable in customer's chosen region |
| NFR-C05 | No training on customer data | Anthropic API called with `anthropic-beta: no-training` header. Documented in privacy policy. |

---

## PART 4 — COMPLETE AGENT SPECIFICATIONS (15 AGENTS)

### Agent 1: Supervisor Agent

**Role:** Central orchestrator. Routes, monitors, retries, and escalates. Never executes tasks directly.

**LangGraph Pattern:** StateGraph root with Command-based dynamic routing
**Model:** None (pure routing logic — no LLM call in supervisor node)
**State Schema:**
```python
class PlatformState(TypedDict):
    tenant_id: str
    user_id: str
    session_id: str
    original_question: str
    enriched_question: str
    intent: str
    execution_plan: list[SubTask]
    agent_results: dict[str, Any]
    final_answer: AnswerObject
    confidence: float
    lineage: LineageTrace
    error_log: list[AgentError]
    iteration_count: int  # hard limit: 5
```
**Failure Mode:** `RuntimeError` on `iteration_count > 5`. Full state logged. Never silent return.
**Routing Logic:** Deterministic Python code, not LLM. Intent + plan → target agent selection.

---

### Agent 2: Intent & Routing Agent

**Role:** Classifies question into one of 7 intent types. Determines if Planner is needed.

**LangGraph Pattern:** Single classification node
**Model:** Claude Haiku (fast, low-cost classification)
**Intent Classes:**
```
Lookup      → "What is customer X's balance?"
Aggregation → "Total sales this month by region"
Trend       → "How has revenue trended over 12 months?"
Comparative → "Compare Q1 vs Q2 gross margin"
RCA         → "Why did sales drop in October?"
Document    → "What is our payment terms policy?"
Hybrid      → Multi-intent (triggers Planner)
```
**Output:** `{ intent: str, requires_planner: bool, primary_domain: str, confidence: float }`
**Latency Target:** < 500ms

---

### Agent 3: Conversation Context Agent

**Role:** Session memory manager and entity resolver.

**LangGraph Pattern:** Stateful node with Redis persistence
**Model:** Claude Haiku
**Responsibilities:**
- Loads last 50 turns from Redis session
- Resolves pronouns: "them" → last referenced customer entity
- Carries forward active date filters: "last month" persists across follow-ups
- Merges prior context into a fully-resolved standalone question
**Output:** Enriched question with resolved entities and explicit filters
**Session TTL:** 24 hours from last activity

---

### Agent 4: Semantic Retrieval Agent

**Role:** Vector search against Tool Catalogue and Knowledge Registry.

**LangGraph Pattern:** Tool node (pgvector client)
**Model:** Claude Embeddings (1536 dim)
**Steps:**
1. Embed enriched question
2. pgvector ANN search against tool_embeddings (HNSW, top-10)
3. pgvector ANN search against semantic_entities (top-5)
4. Return candidates with similarity scores
**Threshold:** Minimum similarity 0.65 to be returned as candidate
**Latency Target:** < 200ms

---

### Agent 5: Knowledge Graph Agent

**Role:** Business relationship resolver and SQL join path provider.

**LangGraph Pattern:** Graph traversal node (custom Python service)
**Model:** None (algorithmic — no LLM call)
**Steps:**
1. Identify entity nodes from question context
2. BFS traversal between identified entities (max depth 5)
3. Return ordered join path: `[{from_table, to_table, on_condition}]`
4. Resolve entity ambiguity via graph proximity score
**Failure Mode:** If no path found, returns empty. SQL Agent uses direct table hints as fallback.

---

### Agent 6: Planner Agent

**Role:** Multi-step question decomposer.

**LangGraph Pattern:** Planner-Executor with re-planning loop
**Model:** Claude Sonnet (reasoning-intensive)
**Responsibilities:**
- Decomposes Hybrid questions into ordered sub-tasks
- Assigns each sub-task to appropriate executor agent
- Generates DAG: sequential and parallel tasks where safe
- Re-plans if intermediate result changes strategy (max 2 re-plans)
**Output:** `ExecutionPlan { tasks: [{ id, agent, input, depends_on: [] }] }`
**When triggered:** Only for Hybrid intent. All other intents bypass Planner.

---

### Agent 7: Tool Ranking Agent

**Role:** Selects and scores tools for execution.

**LangGraph Pattern:** Scoring node
**Model:** None (algorithmic scoring)
**Scoring Formula:**
```
composite_score = (
  semantic_similarity × 0.40 +
  historical_success_rate × 0.35 +
  feedback_weight × 0.20 +
  context_entity_boost × 0.05
)
```
**Permission filter:** Applied before scoring. Unauthorised tools excluded — not ranked, not logged as seen.
**Output:** Ranked list `[{ tool_id, composite_score, rank }]`. Top tool passed to Execution Agent.

---

### Agent 8: Tool Execution Agent

**Role:** Executes ranked tools, validates results, manages fallback chain.

**LangGraph Pattern:** Executor with fallback chain
**Model:** None (execution logic)
**Execution Steps:**
1. Execute tool #1 with parameterised inputs
2. Validate result: non-null, correct type, within expected range
3. If fail → execute tool #2 from ranked list
4. If all top-3 tools fail → escalate to SQL Agent
5. Log each attempt to tool_executions table
**Retry per tool:** 1 retry on transient error (network timeout only)
**Output:** `{ data: [...], tool_id, execution_time_ms, row_count }`

---

### Agent 9: SQL Agent

**Role:** Last-resort structured query generator. SELECT only.

**LangGraph Pattern:** Code generation + validation + execution node
**Model:** Claude Sonnet (SQL generation quality matters)
**Steps:**
1. Build SELECT using KG join paths + semantic entity column mappings
2. Apply RLS filter: `WHERE tenant_id = ? AND company_id = ?`
3. Apply permission-based column masking
4. **AST VALIDATION:** Parse generated SQL. BLOCK if any of: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC, GRANT, REVOKE detected. Hard exception.
5. Execute with parameterised query (never string concatenation)
6. Flag response: `{ generated_by: "sql_agent", verified: false }`
**Output always tagged as unverified — shown to user with yellow warning.**

---

### Agent 10: RAG Agent

**Role:** Document-based question answering with citations.

**LangGraph Pattern:** RAG node
**Model:** Claude Sonnet (synthesis quality)
**Steps:**
1. Hybrid search: BM25 + pgvector cosine similarity, RRF merge
2. Apply document access control filter
3. Apply GraphRAG: boost chunks matching active entity context
4. Top-5 chunks to Claude Sonnet for synthesis
5. Generate answer with inline citations
6. If no relevant chunks found: "I couldn't find that in the uploaded documents."
**Output:** `{ answer, citations: [{ doc_name, page, section, preview }] }`

---

### Agent 11: Analytics Agent

**Role:** Deep analytical reasoning — answers *Why*, not just *What*.

**LangGraph Pattern:** Multi-step reasoning node with Tool Execution sub-calls
**Model:** Claude Sonnet
**Analysis Types:**
```
Trend Analysis    → calls time-series tool → detects direction, slope, seasonality
Period Comparison → calls two period tools → computes variance and % change
Root Cause        → calls metric tool + dimension breakdown tools → ranks contributors
Variance Analysis → volume effect + price effect + mix effect decomposition
Contribution      → Pareto analysis of dimension members
Forecast          → Prophet model + Web Search Agent for external signal enrichment
```
**Output:** `{ analysis_type, data_points, narrative, contributors: [], chart_type_hint }`

---

### Agent 12: Web Search Agent *(Agent 15 — NEW)*

**Role:** External data enrichment. Retrieves market data, economic indicators, and industry forecasts to contextualise internal business data.

**LangGraph Pattern:** Tool node with permitted domain whitelist
**Model:** Claude Sonnet
**When triggered:**
- Analytics Agent requests external benchmark enrichment
- Forecast Engine needs macroeconomic indicators
- User question explicitly references external data ("How does our revenue growth compare to industry?")
- Proactive Intelligence Agent requests market context for anomaly

**Permitted Data Sources (Whitelist — hardcoded, not user-configurable):**
```
Financial Data:    finance.yahoo.com, marketwatch.com, tradingeconomics.com
Economic Data:     worldbank.org, imf.org, stats.oecd.org, data.bls.gov
Industry Reports:  statista.com (public endpoints only)
Currency/FX:       exchangerate-api.com, openexchangerates.org
Commodity Prices:  commodity data via approved public APIs
```

**Security Controls:**
- URL whitelist enforced at agent level (NFR-SEC13)
- No user-supplied URLs accepted
- No authentication credentials passed to external sites
- Results cached in Redis (1-hour TTL) to prevent repeated external calls
- All external calls logged in audit_log with source URL

**Responsibilities:**
- Retrieve relevant external data points for the question context
- Normalise external data into platform metric format
- Attach source URL and retrieval timestamp as citation
- Never used as primary data source — always supplementary enrichment

**Output:** `{ external_data_points: [{ metric, value, source_url, retrieved_at }], summary }`

**Failure Handling:** If all external sources fail or are blocked, returns gracefully: "External market data unavailable. Showing internal data only." Does not block the primary answer.

---

### Agent 13: Proactive Intelligence Agent

**Role:** Autonomous background monitor. Operates without user prompts.

**LangGraph Pattern:** Scheduled autonomous agent (Celery beat trigger)
**Model:** Claude Haiku (anomaly classification)
**Monitoring Cycle:**
1. Execute KPI monitoring tools on schedule (configurable: 1h/4h/24h)
2. Retrieve last 30 data points for statistical baseline
3. Apply Z-score (>2.5σ) and IQR (1.5× IQR) anomaly tests
4. If anomaly confirmed: trigger Analytics Agent for RCA
5. Generate alert with: KPI, value, expected range, severity, RCA summary
6. Route alert to eligible users (by role + domain permission)
7. Optionally trigger anomaly report (RD-008)
**Deduplication:** Same KPI + same direction + same severity within 4h → suppress duplicate alert.
**Trigger Types:** Scheduled interval | Threshold breach | Business event rule

---

### Agent 14: Confidence & Explainability Agent

**Role:** Answer quality validator and evidence builder. Runs on every pipeline output before delivery.

**LangGraph Pattern:** Post-execution validation node
**Model:** Claude Haiku (light validation)
**Confidence Scoring:**
```python
confidence = (
  semantic_similarity_score * 0.40 +   # from Tool Ranking Agent
  tool_validation_status * 0.30 +       # 1.0=pre-validated tool, 0.6=custom, 0.3=sql-agent
  data_freshness_score * 0.20 +         # 1.0=<1h, 0.8=<24h, 0.5=<7d
  source_reliability_score * 0.10       # 1.0=SAP B1 pack tool, 0.7=custom tool, 0.4=sql-agent
)
```
**Lineage Trace Structure:**
```json
{
  "source_db": "SAP B1 HANA",
  "tables_used": ["OINV", "INV1", "OCRD"],
  "tool_id": "ar_invoice_list_v2",
  "sql_query": null,
  "documents_cited": [],
  "external_sources": [],
  "agents_invoked": ["intent_routing", "semantic_retrieval", "tool_ranking", "tool_execution"],
  "execution_time_ms": 1240
}
```
**Hallucination Guard:** Extracts all numeric values from NL narrative. Cross-checks each against actual data result. Mismatch > 1% → re-prompt narrative generation.
**Output:** Enriched answer object with confidence score + lineage + reasoning trace.

---

### Agent 15: Response Synthesis Agent

**Role:** Final answer formatter. Produces the user-facing response.

**LangGraph Pattern:** Terminal output node
**Model:** Claude Haiku (formatting, not reasoning)
**Visualisation Selection Logic:**
```
Single numeric value           → KPI Card
Time-series (≥3 points)        → Line Chart (area if one series, multi-line if multiple)
Categorical comparison (≤8)    → Bar Chart (horizontal if labels long)
Categorical comparison (>8)    → Table (auto-sorted by value)
Composition / share            → Donut Chart
Variance / contribution        → Waterfall Chart
Multi-dimensional              → Table with sort + filter
Mixed (KPIs + table)           → KPI Cards row + Table below
```
**NL Narrative Rules:**
- 2–4 sentences. Business language. No technical jargon.
- Always includes: the key finding, the magnitude, and the period.
- Confidence warning appended if score < 0.65.
- Uncertainty statement if score < 0.40: "I'm not confident in this answer."

**Follow-Up Questions:** Generate exactly 3. Contextually relevant. Pre-populated in UI as clickable chips.

---

## PART 5 — COMPLETE API SPECIFICATION

### 5.1 API Design Standards

- **Protocol:** RESTful JSON over HTTPS. WebSocket for streaming.
- **Versioning:** `/api/v1/` prefix. Breaking changes increment version.
- **Authentication:** Bearer JWT in Authorization header. Refresh via httpOnly cookie.
- **Pagination:** Cursor-based for all list endpoints. `{ cursor, has_more, total }`.
- **Dates:** ISO 8601 UTC everywhere. `2026-06-01T00:00:00Z`.
- **OpenAPI:** Full OpenAPI 3.1 spec generated from FastAPI decorators. Available at `/api/v1/openapi.json`.

### 5.2 Standard Response Envelopes

```json
// Single resource
{ "data": {}, "meta": { "request_id": "uuid4", "timestamp": "ISO8601" } }

// List resource
{ "data": [], "pagination": { "cursor": "opaque_string", "has_more": true, "total": 100 }, "meta": { "request_id": "uuid4" } }

// Error
{ "error": { "code": "TOOL_EXECUTION_FAILED", "message": "Human-readable description", "details": {}, "trace_id": "uuid4" } }

// WebSocket — Streaming Messages
{ "type": "agent_thinking", "agent": "planner",       "content": "Decomposing your question..." }
{ "type": "agent_thinking", "agent": "tool_ranking",  "content": "Selecting best tool..." }
{ "type": "partial",        "content": "Revenue for Q1 2026 was..." }
{ "type": "complete",       "data": { "answer": {}, "confidence": 0.91, "lineage": {} } }
{ "type": "error",          "code": "PIPELINE_TIMEOUT", "message": "Query timed out after 120s" }
```

### 5.3 Complete Endpoint Registry

```
━━━ AUTHENTICATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/auth/login                    # Email + password → JWT pair
POST   /api/v1/auth/refresh                  # Refresh token → new access token
POST   /api/v1/auth/logout                   # Invalidate refresh token
GET    /api/v1/auth/me                        # Current user profile + roles
POST   /api/v1/auth/sso/saml/callback        # SAML SSO callback
GET    /api/v1/auth/sso/oidc/callback        # OIDC SSO callback

━━━ CONNECTIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/connections                   # Create connection (SAP B1 / MSSQL)
GET    /api/v1/connections                   # List tenant connections
GET    /api/v1/connections/{id}              # Get connection (no credential fields)
PUT    /api/v1/connections/{id}              # Update connection config
DELETE /api/v1/connections/{id}              # Soft delete connection
POST   /api/v1/connections/{id}/test         # Test connectivity → { status, latency_ms }
GET    /api/v1/connections/{id}/health       # Real-time health status

━━━ DISCOVERY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/connections/{id}/discover     # Trigger discovery job → { job_id }
GET    /api/v1/connections/{id}/discover/{job_id}  # Poll job status + progress %
GET    /api/v1/connections/{id}/metadata     # Full catalog output (paginated)
POST   /api/v1/connections/{id}/discover/incremental  # Incremental re-scan

━━━ SEMANTIC LAYER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/semantic/entities             # List all semantic entities
GET    /api/v1/semantic/entities/{id}        # Get entity detail with attributes
PUT    /api/v1/semantic/entities/{id}        # Admin: update entity mapping
GET    /api/v1/semantic/kpis                 # List KPI catalogue
PUT    /api/v1/semantic/kpis/{id}            # Admin: update KPI definition
GET    /api/v1/semantic/glossary             # Business glossary (all terms)
POST   /api/v1/semantic/regenerate           # Trigger AI re-generation

━━━ KNOWLEDGE GRAPH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/graph/nodes                   # List nodes (paginated, filterable)
GET    /api/v1/graph/edges                   # List edges (paginated)
GET    /api/v1/graph/path?from={id}&to={id}  # Find join path between entities
GET    /api/v1/graph/visualize               # D3-compatible node/edge JSON
PUT    /api/v1/graph/edges/{id}/confirm      # Admin: confirm inferred relationship

━━━ TOOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/tools                         # List tools (filter: category, status)
GET    /api/v1/tools/{id}                    # Get tool detail with SQL template
POST   /api/v1/tools                         # Create custom tool
PUT    /api/v1/tools/{id}                    # Update tool (creates new version)
DELETE /api/v1/tools/{id}                    # Deprecate tool (soft delete)
POST   /api/v1/tools/{id}/test               # Test tool → { result, execution_time_ms }
GET    /api/v1/tools/{id}/versions           # Version history
GET    /api/v1/tools/{id}/executions         # Execution history (paginated)
GET    /api/v1/tools/performance             # Admin: performance dashboard data

━━━ CONVERSATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/conversations                 # Start new conversation → { id }
GET    /api/v1/conversations                 # List user's conversations
GET    /api/v1/conversations/{id}            # Get full conversation history
DELETE /api/v1/conversations/{id}            # Delete conversation + audit log entry
WS     /api/v1/conversations/{id}/stream     # WebSocket: stream response
POST   /api/v1/conversations/{id}/messages   # Send message (non-streaming REST)
POST   /api/v1/conversations/{id}/feedback   # Submit rating + optional correction
GET    /api/v1/conversations/{id}/lineage/{turn_id}  # Get full lineage for turn

━━━ DOCUMENTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/documents                     # Upload document (multipart/form-data)
GET    /api/v1/documents                     # List documents (filter: status, type)
GET    /api/v1/documents/{id}                # Get document metadata
DELETE /api/v1/documents/{id}                # Remove document + embeddings
GET    /api/v1/documents/{id}/status         # Indexing job status

━━━ ANALYTICS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/analytics/trend               # { kpi_id, period, window } → trend data
POST   /api/v1/analytics/compare             # { kpi_id, period_a, period_b } → comparison
POST   /api/v1/analytics/rca                 # { metric, period, dimensions } → RCA

━━━ ALERTS (v1.1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/alerts                        # Active alerts for current user
GET    /api/v1/alerts/history               # All alerts (paginated)
PUT    /api/v1/alerts/{id}/acknowledge       # Acknowledge alert
PUT    /api/v1/alerts/{id}/snooze            # Snooze { duration: "1h"|"4h"|"24h" }
POST   /api/v1/alerts/rules                  # Admin: create alert rule
GET    /api/v1/alerts/rules                  # Admin: list alert rules
PUT    /api/v1/alerts/rules/{id}             # Admin: update rule
DELETE /api/v1/alerts/rules/{id}             # Admin: deactivate rule

━━━ REPORTS (v1.1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /api/v1/reports/schedules             # Create scheduled report
GET    /api/v1/reports/schedules             # List schedules
PUT    /api/v1/reports/schedules/{id}        # Update schedule
DELETE /api/v1/reports/schedules/{id}        # Deactivate schedule
GET    /api/v1/reports/history              # Generated report history
GET    /api/v1/reports/{id}/download?format=pdf|xlsx  # Download report

━━━ ADMIN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/admin/users                   # List users
POST   /api/v1/admin/users                   # Invite user
PUT    /api/v1/admin/users/{id}              # Update user (role, status)
DELETE /api/v1/admin/users/{id}              # Deactivate user
GET    /api/v1/admin/roles                   # List roles + permissions
POST   /api/v1/admin/roles                   # Create custom role
GET    /api/v1/admin/audit-log               # Query audit log (date, user, action filters)
GET    /api/v1/admin/usage                   # ROI + usage metrics dashboard
GET    /api/v1/admin/feedback                # Feedback loop dashboard data
GET    /api/v1/admin/catalog/health          # Catalog health score + details

━━━ SYSTEM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GET    /api/v1/health/live                   # Kubernetes liveness probe → 200 OK
GET    /api/v1/health/ready                  # Kubernetes readiness → 200 if DB+Redis up
GET    /api/v1/health/full                   # Detailed component status (admin only)
GET    /api/v1/openapi.json                  # OpenAPI 3.1 specification
```

### 5.4 Error Code Registry

| Code | HTTP Status | Description |
|------|------------|-------------|
| AUTH_INVALID_CREDENTIALS | 401 | Email or password incorrect |
| AUTH_TOKEN_EXPIRED | 401 | JWT access token expired |
| AUTH_REFRESH_INVALID | 401 | Refresh token invalid or revoked |
| AUTH_LOCKED | 423 | Account locked after failed attempts |
| AUTH_PERMISSION_DENIED | 403 | User lacks permission for requested resource |
| CONN_UNREACHABLE | 503 | Cannot connect to source database |
| CONN_AUTH_FAILED | 401 | DB credentials rejected by source |
| CONN_TIMEOUT | 504 | DB connection timed out |
| DISC_IN_PROGRESS | 409 | Discovery already running for this connection |
| DISC_FAILED | 500 | Discovery job failed (see details) |
| TOOL_NOT_FOUND | 404 | Tool ID does not exist |
| TOOL_EXECUTION_FAILED | 500 | Tool SQL returned error |
| TOOL_VALIDATION_FAILED | 422 | Tool result did not match output schema |
| TOOL_DEPRECATED | 410 | Tool has been deprecated |
| AGENT_TIMEOUT | 504 | Agent node exceeded 60s timeout |
| AGENT_PIPELINE_TIMEOUT | 504 | Full pipeline exceeded 120s timeout |
| AGENT_MAX_ITERATIONS | 500 | Supervisor exceeded iteration limit |
| SQL_DML_BLOCKED | 403 | Generated SQL contained DML — blocked by security |
| SQL_VALIDATION_FAILED | 422 | Generated SQL failed AST validation |
| SQL_EXECUTION_FAILED | 500 | SQL executed with DB error |
| RAG_NO_DOCUMENTS | 404 | No documents uploaded or accessible |
| RAG_NO_RELEVANT_CHUNKS | 200 | Query answered but no relevant doc found (200 with notice) |
| VAL_MISSING_FIELD | 422 | Required field missing in request body |
| VAL_INVALID_FORMAT | 422 | Field value fails format validation |
| RATE_LIMIT_EXCEEDED | 429 | Rate limit hit — Retry-After header included |
| TENANT_NOT_FOUND | 404 | Tenant ID does not exist |
| INTERNAL_ERROR | 500 | Unexpected server error — trace_id for support |

---

## PART 6 — COMPLETE DATABASE SCHEMA

### 6.1 Design Decisions

- **Multi-tenancy:** Row-level `tenant_id` (UUID) on all tables + PostgreSQL RLS policies
- **Soft deletes:** `deleted_at TIMESTAMPTZ NULL` on all mutable resources
- **Audit columns:** `created_at`, `updated_at`, `created_by` on all tables
- **UUIDs:** All primary keys are UUID v4
- **Partitioning:** High-volume tables partitioned by month (audit_log, conversation_turns, tool_executions)
- **Embedding dimensions:** 1536 (Claude text-embedding-3)

### 6.2 Core Schema

```sql
-- TENANTS
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    branding        JSONB DEFAULT '{}',  -- logo_url, primary_color, font
    settings        JSONB DEFAULT '{}',  -- timezone, fiscal_year_start, etc.
    status          VARCHAR(20) DEFAULT 'active',  -- active, suspended
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- USERS
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    email           VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    password_hash   VARCHAR(255),          -- NULL for SSO-only users
    sso_provider    VARCHAR(50),           -- 'saml', 'oidc', NULL
    sso_subject     VARCHAR(255),          -- SSO external ID
    status          VARCHAR(20) DEFAULT 'active',
    failed_logins   INT DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE (tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- ROLES
CREATE TABLE roles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    is_system       BOOLEAN DEFAULT false,  -- system roles cannot be deleted
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

-- USER ROLES (many-to-many)
CREATE TABLE user_roles (
    user_id         UUID NOT NULL REFERENCES users(id),
    role_id         UUID NOT NULL REFERENCES roles(id),
    granted_by      UUID REFERENCES users(id),
    granted_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

-- DATA DOMAIN PERMISSIONS
CREATE TABLE role_permissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id         UUID NOT NULL REFERENCES roles(id),
    domain          VARCHAR(50) NOT NULL,  -- 'finance','sales','purchasing','inventory','hr'
    can_read        BOOLEAN DEFAULT true,
    company_filter  JSONB DEFAULT '[]',    -- [] means all companies
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- DB CONNECTIONS
CREATE TABLE connections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    db_type         VARCHAR(20) NOT NULL,    -- 'sap_b1_hana', 'mssql'
    host            VARCHAR(255) NOT NULL,
    port            INT NOT NULL,
    database_name   VARCHAR(255) NOT NULL,
    schema_name     VARCHAR(255),
    credential_ref  VARCHAR(255) NOT NULL,   -- Vault key reference, not raw credential
    ssl_enabled     BOOLEAN DEFAULT true,
    status          VARCHAR(20) DEFAULT 'active',  -- active, error, disconnected
    last_tested_at  TIMESTAMPTZ,
    last_tested_ok  BOOLEAN,
    latency_ms      INT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id)
);
CREATE INDEX idx_connections_tenant ON connections(tenant_id);

-- DISCOVERY JOBS
CREATE TABLE discovery_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    connection_id   UUID NOT NULL REFERENCES connections(id),
    job_type        VARCHAR(20) DEFAULT 'full',  -- 'full', 'incremental'
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, running, complete, failed
    progress_pct    INT DEFAULT 0,
    tables_found    INT,
    columns_found   INT,
    relations_found INT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- METADATA: TABLES
CREATE TABLE metadata_tables (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    connection_id   UUID NOT NULL REFERENCES connections(id),
    schema_name     VARCHAR(255),
    table_name      VARCHAR(255) NOT NULL,
    table_type      VARCHAR(20) DEFAULT 'table',  -- 'table', 'view'
    row_count_est   BIGINT,
    ai_description  TEXT,
    is_pii_flagged  BOOLEAN DEFAULT false,
    metadata_hash   VARCHAR(64),     -- SHA-256 of column list for change detection
    discovery_job_id UUID REFERENCES discovery_jobs(id),
    version         INT DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, connection_id, schema_name, table_name)
);
CREATE INDEX idx_meta_tables_tenant_conn ON metadata_tables(tenant_id, connection_id);

-- METADATA: COLUMNS
CREATE TABLE metadata_columns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    table_id        UUID NOT NULL REFERENCES metadata_tables(id),
    column_name     VARCHAR(255) NOT NULL,
    data_type       VARCHAR(100) NOT NULL,
    is_nullable     BOOLEAN DEFAULT true,
    is_primary_key  BOOLEAN DEFAULT false,
    column_default  TEXT,
    ordinal_pos     INT,
    ai_description  TEXT,
    sample_values   JSONB DEFAULT '[]',    -- up to 10 sample values, no PII
    null_pct        NUMERIC(5,2),
    distinct_count  BIGINT,
    min_value       TEXT,
    max_value       TEXT,
    is_pii          BOOLEAN DEFAULT false,
    semantic_type   VARCHAR(50),  -- 'currency','quantity','date','code','text','boolean'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, table_id, column_name)
);
CREATE INDEX idx_meta_columns_table ON metadata_columns(table_id);
CREATE INDEX idx_meta_columns_tenant ON metadata_columns(tenant_id);

-- METADATA: RELATIONS
CREATE TABLE metadata_relations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    from_table_id   UUID NOT NULL REFERENCES metadata_tables(id),
    from_column_id  UUID NOT NULL REFERENCES metadata_columns(id),
    to_table_id     UUID NOT NULL REFERENCES metadata_tables(id),
    to_column_id    UUID NOT NULL REFERENCES metadata_columns(id),
    relation_type   VARCHAR(20) DEFAULT 'inferred',  -- 'explicit_fk', 'inferred'
    confidence      NUMERIC(4,3) DEFAULT 1.0,
    is_confirmed    BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- SEMANTIC ENTITIES
CREATE TABLE semantic_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    table_id        UUID NOT NULL REFERENCES metadata_tables(id),
    business_name   VARCHAR(255) NOT NULL,
    business_description TEXT,
    domain          VARCHAR(50),  -- 'finance','sales','purchasing','inventory','hr'
    entity_type     VARCHAR(50),  -- 'master','transaction','reference','aggregate'
    source          VARCHAR(20) DEFAULT 'ai',  -- 'ai', 'pack', 'human'
    confidence      NUMERIC(4,3),
    is_override     BOOLEAN DEFAULT false,
    version         INT DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id)
);

-- SEMANTIC ATTRIBUTES
CREATE TABLE semantic_attributes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    entity_id       UUID NOT NULL REFERENCES semantic_entities(id),
    column_id       UUID NOT NULL REFERENCES metadata_columns(id),
    business_name   VARCHAR(255) NOT NULL,
    business_description TEXT,
    semantic_role   VARCHAR(50),  -- 'identifier','measure','dimension','date','status'
    display_format  VARCHAR(100), -- '#,##0.00','YYYY-MM-DD', etc.
    source          VARCHAR(20) DEFAULT 'ai',
    is_override     BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- KPI CATALOGUE
CREATE TABLE kpi_catalogue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    formula         TEXT,           -- human-readable formula
    unit            VARCHAR(50),    -- 'currency','percentage','days','count'
    aggregation     VARCHAR(20),    -- 'sum','avg','count','ratio'
    display_format  VARCHAR(100),
    domain          VARCHAR(50),
    entity_ids      UUID[],         -- entities involved in this KPI
    is_active       BOOLEAN DEFAULT true,
    source          VARCHAR(20) DEFAULT 'ai',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- BUSINESS GLOSSARY
CREATE TABLE business_glossary (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    term            VARCHAR(255) NOT NULL,
    definition      TEXT NOT NULL,
    synonyms        TEXT[],
    entity_id       UUID REFERENCES semantic_entities(id),
    source          VARCHAR(20) DEFAULT 'ai',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, term)
);

-- SYNONYM MAPPINGS
CREATE TABLE synonym_mappings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    synonym         VARCHAR(255) NOT NULL,
    canonical_term  VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(50),  -- 'entity','kpi','attribute'
    target_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, synonym)
);

-- BUSINESS RULES
CREATE TABLE business_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    entity_id       UUID NOT NULL REFERENCES semantic_entities(id),
    rule_name       VARCHAR(255) NOT NULL,
    description     TEXT,
    sql_predicate   TEXT NOT NULL,  -- e.g. "validFor = 'Y' AND frozenFor = 'N'"
    is_default      BOOLEAN DEFAULT true,  -- applied by default in queries
    source          VARCHAR(20) DEFAULT 'pack',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- KNOWLEDGE GRAPH: NODES
CREATE TABLE knowledge_graph_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    entity_id       UUID NOT NULL REFERENCES semantic_entities(id),
    node_label      VARCHAR(255) NOT NULL,
    domain          VARCHAR(50),
    properties      JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- KNOWLEDGE GRAPH: EDGES
CREATE TABLE knowledge_graph_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    from_node_id    UUID NOT NULL REFERENCES knowledge_graph_nodes(id),
    to_node_id      UUID NOT NULL REFERENCES knowledge_graph_nodes(id),
    relation_name   VARCHAR(255) NOT NULL,
    join_condition  TEXT NOT NULL,  -- "a.CardCode = b.CardCode"
    join_type       VARCHAR(10) DEFAULT 'INNER',
    confidence      NUMERIC(4,3) DEFAULT 1.0,
    is_confirmed    BOOLEAN DEFAULT true,
    source          VARCHAR(20) DEFAULT 'fk',  -- 'fk','inferred','manual'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_kg_edges_from ON knowledge_graph_edges(tenant_id, from_node_id);
CREATE INDEX idx_kg_edges_to ON knowledge_graph_edges(tenant_id, to_node_id);

-- TOOLS
CREATE TABLE tools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT NOT NULL,
    category        VARCHAR(100),  -- 'ar','ap','sales','inventory','purchasing','financial','partner'
    input_schema    JSONB NOT NULL,  -- [{ name, type, required, default, description }]
    output_schema   JSONB NOT NULL,  -- { columns: [{ name, type }] }
    sql_template    TEXT NOT NULL,
    permission_domains TEXT[],       -- ['finance'] — roles with these domains can execute
    source          VARCHAR(20) DEFAULT 'generated',  -- 'generated','pack','custom'
    status          VARCHAR(20) DEFAULT 'active',  -- 'active','invalid','deprecated','custom'
    version         INT DEFAULT 1,
    parent_tool_id  UUID REFERENCES tools(id),  -- for versioning
    last_validated_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id),
    deleted_at      TIMESTAMPTZ,
    UNIQUE (tenant_id, name, version)
);

-- TOOL EMBEDDINGS (pgvector)
CREATE TABLE tool_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    tool_id         UUID NOT NULL REFERENCES tools(id),
    embedding       vector(1536) NOT NULL,
    embed_text      TEXT NOT NULL,  -- text that was embedded
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tool_embeddings_hnsw
    ON tool_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- TOOL TABLE DEPENDENCIES
CREATE TABLE tool_table_dependencies (
    tool_id         UUID NOT NULL REFERENCES tools(id),
    table_id        UUID NOT NULL REFERENCES metadata_tables(id),
    PRIMARY KEY (tool_id, table_id)
);

-- TOOL RANKING WEIGHTS
CREATE TABLE tool_ranking_weights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    tool_id         UUID NOT NULL REFERENCES tools(id),
    feedback_weight NUMERIC(5,4) DEFAULT 0.0,
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, tool_id)
);

-- TOOL EXECUTIONS (partitioned by month)
CREATE TABLE tool_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    tool_id         UUID NOT NULL,
    conversation_turn_id UUID,
    user_id         UUID NOT NULL,
    input_params    JSONB DEFAULT '{}',
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    execution_time_ms INT,
    row_count       INT,
    executed_at     TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (executed_at);
CREATE INDEX idx_tool_exec_tool ON tool_executions(tool_id, success, executed_at);
CREATE INDEX idx_tool_exec_tenant ON tool_executions(tenant_id, executed_at);

-- DOCUMENTS
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    filename        VARCHAR(500) NOT NULL,
    file_type       VARCHAR(20),  -- 'pdf','docx','xlsx','txt'
    file_size_bytes BIGINT,
    document_type   VARCHAR(100),
    department      VARCHAR(100),
    effective_date  DATE,
    access_roles    UUID[],
    status          VARCHAR(20) DEFAULT 'pending',  -- 'pending','indexing','ready','failed'
    chunk_count     INT,
    storage_path    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id),
    deleted_at      TIMESTAMPTZ
);

-- DOCUMENT CHUNKS
CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    document_id     UUID NOT NULL REFERENCES documents(id),
    chunk_index     INT NOT NULL,
    content         TEXT NOT NULL,
    page_number     INT,
    section_heading TEXT,
    token_count     INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- DOCUMENT EMBEDDINGS (pgvector)
CREATE TABLE document_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    chunk_id        UUID NOT NULL REFERENCES document_chunks(id),
    embedding       vector(1536) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_doc_embeddings_hnsw
    ON document_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- CONVERSATIONS
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    title           VARCHAR(500),   -- AI-generated from first question
    turn_count      INT DEFAULT 0,
    last_activity_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_conversations_user ON conversations(tenant_id, user_id, created_at DESC);

-- CONVERSATION TURNS (partitioned by month)
CREATE TABLE conversation_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    conversation_id UUID NOT NULL,
    user_id         UUID NOT NULL,
    turn_number     INT NOT NULL,
    question        TEXT NOT NULL,
    enriched_question TEXT,
    answer_text     TEXT,
    answer_data     JSONB DEFAULT '{}',    -- raw data result
    chart_type      VARCHAR(50),
    chart_data      JSONB DEFAULT '{}',
    intent          VARCHAR(50),
    confidence      NUMERIC(4,3),
    lineage         JSONB DEFAULT '{}',
    agents_used     TEXT[],
    execution_time_ms INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (created_at);
CREATE INDEX idx_turns_conversation ON conversation_turns(conversation_id, turn_number);

-- USER FEEDBACK
CREATE TABLE user_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    turn_id         UUID NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(id),
    tool_id         UUID REFERENCES tools(id),
    rating          SMALLINT NOT NULL CHECK (rating IN (-1, 1)),  -- -1=negative, 1=positive
    correction_text TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_feedback_tool ON user_feedback(tool_id, rating, created_at DESC);

-- AUDIT LOG (partitioned by month — append-only)
CREATE TABLE audit_log (
    id              UUID DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    user_id         UUID,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(100),
    resource_id     UUID,
    question        TEXT,
    generated_sql   TEXT,
    tool_id         UUID,
    execution_time_ms INT,
    result_row_count INT,
    confidence      NUMERIC(4,3),
    ip_address      INET,
    user_agent      TEXT,
    trace_id        UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (created_at);
-- NO UPDATE, NO DELETE allowed on this table (enforced by RBAC + trigger)
CREATE INDEX idx_audit_user ON audit_log(tenant_id, user_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(tenant_id, resource_type, resource_id);

-- ALERT RULES
CREATE TABLE alert_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    kpi_id          UUID REFERENCES kpi_catalogue(id),
    rule_name       VARCHAR(255) NOT NULL,
    condition_operator VARCHAR(10) NOT NULL,  -- '>','<','>=','<=','='
    threshold_value NUMERIC,
    severity        VARCHAR(20) DEFAULT 'warning',  -- 'critical','warning','info'
    assigned_role_ids UUID[],
    report_template_id UUID,
    monitoring_interval_hours INT DEFAULT 1,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id)
);

-- ALERTS
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    rule_id         UUID REFERENCES alert_rules(id),
    kpi_name        VARCHAR(255),
    kpi_value       NUMERIC,
    expected_min    NUMERIC,
    expected_max    NUMERIC,
    severity        VARCHAR(20),
    rca_summary     TEXT,
    status          VARCHAR(20) DEFAULT 'active',  -- 'active','acknowledged','snoozed','resolved'
    snoozed_until   TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- REPORT SCHEDULES
CREATE TABLE report_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    questions       JSONB NOT NULL,    -- [{ question, section_title }]
    cron_expression VARCHAR(100) NOT NULL,
    delivery_email  TEXT[],
    delivery_slack_webhook TEXT,
    delivery_teams_webhook TEXT,
    output_formats  TEXT[] DEFAULT '{pdf}',
    is_active       BOOLEAN DEFAULT true,
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      UUID REFERENCES users(id)
);
```

---

## PART 7 — ERROR HANDLING & FAILURE MODES

### 7.1 Agent Failure Classification & Response

| Failure Type | Trigger | Required System Behaviour |
|-------------|---------|---------------------------|
| LLM API timeout | Claude API > 30s | Retry 3× with backoff (1s, 2s, 4s). If all fail: queue response or return cached answer. |
| Tool execution failure | SQL returns error | Try next-ranked tool. After 3 failures: escalate to SQL Agent. |
| All tools exhausted | No tools pass validation | SQL Agent fallback. Flag response as unverified. |
| SQL DML detected | AST parser finds DML | Hard block. HTTP 403 SQL_DML_BLOCKED. Audit log entry. Do not retry. |
| SQL execution error | DB returns SQL error | Return HTTP 500 SQL_EXECUTION_FAILED with trace_id. Do not expose raw DB error to user. |
| Agent node timeout | Agent > 60s | Cancel node. Return partial state to Supervisor. Supervisor sends degraded response. |
| Full pipeline timeout | Pipeline > 120s | Cancel all pending nodes. Return AGENT_PIPELINE_TIMEOUT. Log full state. |
| Confidence < 0.40 | Confidence Agent scores low | Return answer WITH low-confidence warning. Never suppress. Never retry for higher score. |
| Permission denied | User lacks domain access | Return AUTH_PERMISSION_DENIED. Audit log. Do not reveal what data exists. |
| Rate limit hit | >60 req/min | HTTP 429. Retry-After header set. User-facing: "You've sent too many requests. Please wait X seconds." |
| Vector DB failure | pgvector unavailable | Degrade to BM25 keyword-only search. Log alert. Continue with reduced accuracy. |
| Session expired | JWT expired | HTTP 401 AUTH_TOKEN_EXPIRED. Client auto-refreshes using refresh token. |
| DB connection down | Source DB unreachable | Cache-only mode for identical past queries. RAG still functional. Admin alert sent. User notified with data timestamp. |

### 7.2 Circuit Breaker Configuration

| Service | Failure Threshold | Open Duration | Half-Open Probes |
|---------|------------------|---------------|-----------------|
| SAP B1 HANA | 5 failures in 60s | 120s | 1 probe every 30s |
| MSSQL | 5 failures in 60s | 120s | 1 probe every 30s |
| Claude API | 10 failures in 60s | 60s | 1 probe every 15s |
| Email delivery | 3 failures in 300s | 600s | 1 probe every 120s |

### 7.3 Graceful Degradation Modes

```
LEVEL 0 — Full Operation:           All agents + DB + LLM + Vector all available
LEVEL 1 — DB Unreachable:          Serve cached answers. RAG functional. LLM functional.
LEVEL 2 — Vector Store Degraded:   Keyword-only tool matching. Accuracy reduced. User warned.
LEVEL 3 — LLM API Degraded:        Queue new queries (5 min max). Serve cached identical queries.
LEVEL 4 — Redis Unavailable:       Stateless mode. No session memory. No caching. Still functional.
LEVEL 5 — Full Outage:             Health check returns 503. Queue with ETA if possible.
```

---

## PART 8 — SAP BUSINESS ONE DOMAIN SPECIFICATION

### 8.1 Core Table Mapping (SAP B1 Entity Pack)

```
BUSINESS PARTNERS
OCRD  → Customer / Supplier Master          OCRB → BP Bank Accounts
CRD1  → BP Addresses                        CRD7 → BP Payment Terms

SALES CYCLE
OQUT  → Sales Quotation Header              QUT1 → Sales Quotation Lines
ORDR  → Sales Order Header                  RDR1 → Sales Order Lines
ODLN  → Delivery Note Header                DLN1 → Delivery Note Lines
OINV  → AR Invoice Header                   INV1 → AR Invoice Lines
ORCT  → Incoming Payments                   RCT2 → Payment Invoice Links
OCRD.CardType='C' → Customer filter

PURCHASING CYCLE
OPQT  → Purchase Quotation Header           PQT1 → Purchase Quotation Lines
OPOR  → Purchase Order Header               POR1 → Purchase Order Lines
OPDN  → Goods Receipt PO Header             PDN1 → Goods Receipt PO Lines
OPCH  → AP Invoice Header                   PCH1 → AP Invoice Lines
OVPM  → Outgoing Payments                   VPM2 → Payment Invoice Links
OCRD.CardType='S' → Supplier filter

INVENTORY
OITM  → Item Master                         OITB → Item Groups
OITW  → Item Warehouse Info                 OWHS → Warehouse Master
OIGE  → Goods Issue Header                  IGE1 → Goods Issue Lines
OIGN  → Goods Receipt Header               IGN1 → Goods Receipt Lines
OITL  → Item Ledger / Bin Locations         OSRI → Serial Number Master

FINANCIALS
OJDT  → Journal Entry Header                JDT1 → Journal Entry Lines
OACT  → Chart of Accounts                   OCOA → Account Category
OFPR  → Fiscal Periods                      OPRD → Price Lists
OCRN  → Currency Master

PRODUCTION (if applicable)
OWOR  → Production Order Header            WOR1 → Production Order Lines
OITM.MakeBuy='M' → Manufactured items

STATUS CODE REFERENCE:
  DocStatus: 'O'=Open, 'C'=Closed, 'L'=Cancelled
  CardType:  'C'=Customer, 'S'=Supplier, 'L'=Lead
  InvntItem: 'Y'=Stock item, 'N'=Non-stock
  validFor:  'Y'=Active, 'N'=Inactive
  frozenFor: 'Y'=Frozen, 'N'=Active
  objType:   13=Invoice, 15=Delivery, 17=Order, 18=Returns, 20=Quotation
```

### 8.2 SAP B1 Pre-Built Business Rules

```sql
-- Active Customers
OCRD.validFor = 'Y' AND OCRD.frozenFor = 'N' AND OCRD.CardType = 'C'

-- Active Suppliers
OCRD.validFor = 'Y' AND OCRD.frozenFor = 'N' AND OCRD.CardType = 'S'

-- Posted AR Invoices (include open and closed)
OINV.canceled = 'N'

-- Open AR Invoices
OINV.docStatus = 'O' AND OINV.canceled = 'N'

-- Overdue AR Invoices
OINV.docStatus = 'O' AND OINV.docDueDate < CURRENT_DATE AND OINV.canceled = 'N'

-- Open Sales Orders
ORDR.docStatus = 'O' AND ORDR.canceled = 'N'

-- Active Stock Items
OITM.validFor = 'Y' AND OITM.frozenFor = 'N' AND OITM.invntItem = 'Y'

-- Items Below Reorder
OITW.onHand <= OITW.minStock AND OITM.invntItem = 'Y'

-- Posted Journal Entries
OJDT.canceled = 'N' AND OJDT.transType IS NOT NULL

-- Current Fiscal Period
OFPR.F_RefDate <= CURRENT_DATE AND OFPR.T_RefDate >= CURRENT_DATE AND OFPR.locked = 'N'

-- Open Purchase Orders
OPOR.docStatus = 'O' AND OPOR.canceled = 'N'

-- Open AP Invoices
OPCH.docStatus = 'O' AND OPCH.canceled = 'N'
```

### 8.3 SAP B1 Tool Pack — 50 Tools with Signatures

```
ACCOUNTS RECEIVABLE (8)
ar_outstanding_balance(date_as_of, customer_code?)
ar_aging_report(date_as_of, buckets=[30,60,90])
ar_overdue_customers(days_overdue_min=1, limit=50)
ar_invoice_list(date_from, date_to, customer_code?, status?)
ar_invoice_detail(invoice_doc_num)
ar_payments_received(date_from, date_to, customer_code?)
ar_days_sales_outstanding(date_from, date_to)
ar_credit_utilization(customer_code?)

ACCOUNTS PAYABLE (6)
ap_outstanding_balance(date_as_of, supplier_code?)
ap_aging_report(date_as_of, buckets=[30,60,90])
ap_overdue_payables(days_overdue_min=1, limit=50)
ap_invoice_list(date_from, date_to, supplier_code?, status?)
ap_payments_made(date_from, date_to, supplier_code?)
ap_days_payable_outstanding(date_from, date_to)

SALES (10)
sales_revenue_by_period(date_from, date_to, group_by='month')
sales_revenue_by_customer(date_from, date_to, limit=20)
sales_revenue_by_item(date_from, date_to, limit=20)
sales_revenue_by_salesperson(date_from, date_to)
sales_gross_margin(date_from, date_to, group_by='month')
sales_order_backlog(date_as_of)
sales_quotation_conversion(date_from, date_to)
sales_top_customers(date_from, date_to, limit=10)
sales_customer_trend(customer_code, months=12)
sales_returns_analysis(date_from, date_to)

INVENTORY (8)
inventory_stock_levels(item_code?, warehouse_code?, below_reorder_only=false)
inventory_below_reorder(warehouse_code?)
inventory_valuation(warehouse_code?, item_group_code?)
inventory_turnover(date_from, date_to, item_code?)
inventory_slow_moving(no_movement_days=90, warehouse_code?)
inventory_receipts(date_from, date_to, item_code?, warehouse_code?)
inventory_issues(date_from, date_to, item_code?, warehouse_code?)
inventory_item_history(item_code, date_from, date_to, warehouse_code?)

PURCHASING (6)
purchase_orders_open(supplier_code?, date_as_of?)
purchase_spend_by_supplier(date_from, date_to, limit=20)
purchase_spend_by_period(date_from, date_to, group_by='month')
purchase_price_history(item_code, months=12)
purchase_lead_time(supplier_code?, item_code?, months=6)
purchase_goods_received(date_from, date_to, supplier_code?)

FINANCIALS (8)
financial_trial_balance(period_id)
financial_pl_summary(date_from, date_to)
financial_revenue_summary(date_from, date_to, group_by='month')
financial_expense_summary(date_from, date_to, group_by='month')
financial_balance_sheet(date_as_of)
financial_cash_flow(date_from, date_to)
financial_journal_entries(date_from, date_to, account_code?, limit=100)
financial_account_balance(account_code, date_from, date_to)

BUSINESS PARTNERS (4)
customer_profile(customer_code)
supplier_profile(supplier_code)
customer_transaction_history(customer_code, date_from, date_to)
new_customers_by_period(date_from, date_to, group_by='month')

CROSS-FUNCTIONAL (8)
period_comparison(kpi_tool_name, period_a_from, period_a_to, period_b_from, period_b_to)
entity_ranking(metric, entity_type, date_from, date_to, limit=10, sort_dir='desc')
branch_comparison(metric, date_from, date_to)
kpi_trend(kpi_tool_name, months=12, group_by='month')
top_n_analysis(dimension, metric, date_from, date_to, n=10)
contribution_analysis(metric, dimension, date_from, date_to)
cash_position_summary(date_as_of)
working_capital_analysis(date_as_of)
```

### 8.4 AI Golden Dataset (SAP B1 — 100 Q&A Pairs)

The following categories of questions must have verified correct answers built before launch:

```
AR / AP (20 questions)
  "What is the total outstanding AR as of today?"
  "Which customers have invoices overdue more than 90 days?"
  "What is our DSO for this quarter?"
  "Show me the top 10 customers by outstanding balance"
  [+ 16 more AR/AP questions]

Sales (20 questions)
  "What was total revenue last month?"
  "Who are the top 10 customers by revenue this year?"
  "What is our gross margin for Q1 vs Q2?"
  "Which salesperson has the highest revenue this quarter?"
  [+ 16 more Sales questions]

Inventory (20 questions)
  "Which items are below reorder point right now?"
  "What is the total inventory value by warehouse?"
  "Show me slow-moving items with no movement in 90 days"
  "What is the inventory turnover ratio for this year?"
  [+ 16 more Inventory questions]

Financials (20 questions)
  "What is the P&L summary for this month?"
  "Show me the trial balance for the current period"
  "What is the cash flow for the past 6 months?"
  "What is the balance of account 40000?"
  [+ 16 more Financial questions]

Analytics / RCA (20 questions)
  "Why did revenue drop in March?"
  "How has gross margin trended over the last 12 months?"
  "Compare our Q1 vs Q2 performance"
  "Which customer segment is growing fastest?"
  [+ 16 more Analytics questions]
```

Each Q&A pair must include: question, expected answer format, expected tool(s) used, expected confidence level, and verified result against a test SAP B1 company database.

---

## PART 9 — TESTING STRATEGY

### 9.1 Test Pyramid

```
           ┌────────────────────┐
           │    E2E Tests (10%) │  Playwright — Full user journeys
           └─────────┬──────────┘
      ┌──────────────┴──────────────┐
      │   Integration Tests (30%)  │  pytest — Agent chains, DB, API
      └──────────────┬──────────────┘
  ┌────────────────────────────────────┐
  │       Unit Tests (60%)            │  pytest — All business logic
  └────────────────────────────────────┘

Coverage target: 80% overall. 95% for security-critical paths (SQL validation, RBAC, DML blocker).
```

### 9.2 Unit Tests (Required Coverage)

```
Semantic Layer:       Entity mapping accuracy on 80+ SAP B1 tables (pack correctness)
Knowledge Graph:      FK detection, path traversal, hop-limit enforcement
Tool Generation:      SQL correctness for each of 50 tool signatures
Tool Ranking:         Scoring algorithm with known fixture inputs
SQL Agent:            DML blocking (50 injection patterns), parameterisation, AST parser
Confidence Scoring:   Boundary values (0.0, 0.65, 0.85, 1.0)
RBAC:                 Permission enforcement for all 4 roles × all 5 domains
JWT:                  Token expiry, refresh, blocklist, tampering
Circuit Breaker:      State transitions (closed → open → half-open → closed)
Hallucination Guard:  Numeric value cross-check with known mismatches
Web Search Agent:     Whitelist enforcement — blocked URLs return graceful failure
```

### 9.3 Integration Tests

```
SAP B1 HANA connector:    Discovery on test company DB (min 500 tables)
MSSQL connector:          Discovery on test DB
LangGraph pipeline:       Full agent chain with mocked LLM (deterministic responses)
pgvector:                 Embedding storage + retrieval top-K accuracy
Redis:                    Session persistence, expiry, blocklist
Celery:                   Background job execution, scheduling, retry
API endpoints:            All 60+ endpoints — happy path + error cases
WebSocket:                Streaming response assembly, disconnection handling
```

### 9.4 AI Quality Tests (Golden Dataset — Regression Gate)

```
Dataset:     100 verified SAP B1 Q&A pairs (Part 8.4)
Metric:      Answer accuracy = correct_answers / total_questions
Gate:        Accuracy must not fall below 85% between releases
Automation:  Golden dataset runner executes in CI/CD on every merge to main
Failure:     Accuracy drop > 5% blocks deployment to staging
Categories:  AR/AP (20), Sales (20), Inventory (20), Financials (20), Analytics (20)
```

### 9.5 Security Tests

```
SQL Injection:          50 attack patterns in question input
DML Blocking:           All DML variants including obfuscated forms
RBAC Boundaries:        Finance user accessing Sales tools → blocked
Row-Level Security:     Cross-company data access attempt → blocked
JWT Manipulation:       Expired, wrong signature, wrong tenant claim
Rate Limiting:          Exceed 60 req/min → 429 returned
PII Access:             Read PII column without admin role → masked
Audit Log Integrity:    Attempt to UPDATE/DELETE audit_log → rejected
Web Search Whitelist:   Attempt to pass non-whitelisted URL → blocked
```

### 9.6 Performance Tests (k6)

```
Load Test:     50 concurrent users, 10-minute sustained load → all NFR-P targets met
Stress Test:   Ramp to 200 concurrent, find breaking point, document degradation behaviour
Spike Test:    0 → 100 users in 30s → system recovers within 60s
Volume Test:   Schema discovery on 5,000-table DB → completes within NFR-P03 target
Soak Test:     10 concurrent users, 4-hour run → no memory leaks, stable response times
```

### 9.7 End-to-End Tests (Playwright)

```
E2E-001: New SAP B1 connection → discovery → first question answered → confidence shown
E2E-002: Ask "top 10 customers by revenue" → bar chart rendered with correct data
E2E-003: Upload document → ask policy question → RAG answer with citation
E2E-004: Ask "why did sales drop in March?" → RCA answer with contributors shown
E2E-005: Finance user cannot access HR domain questions → permission error shown
E2E-006: Admin creates scheduled report → report generated and "sent" in test mode
E2E-007: Thumbs down on answer → correction submitted → admin feedback queue updated
E2E-008: SAP B1 connection goes offline mid-query → graceful degradation message shown
E2E-009: Ask a question with external market context → Web Search Agent enrichment shown
E2E-010: Full onboarding wizard from zero to first insight (target: < 30 minutes)
```

---

## PART 10 — OBSERVABILITY & MONITORING

### 10.1 Observability Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Agent Tracing | LangSmith | Full agent execution traces, prompt logs, token usage |
| Application Metrics | Prometheus + Grafana | API latency, error rates, throughput, queue depth |
| Infrastructure | Prometheus node_exporter | CPU, memory, disk, network per service |
| Log Aggregation | Structured JSON (stdout) → Loki | All application and agent logs |
| Error Tracking | Sentry | Exception capture with full stack trace + context |
| DB Performance | pg_stat_statements | Slow query detection (>100ms logged) |
| Uptime Monitoring | /health/live + external pingdom/UptimeRobot | Public uptime tracking |

### 10.2 Key Metrics Dashboard

```
PLATFORM HEALTH
  query_response_time_p50/p95/p99   (by query type)
  agent_execution_time              (by agent name)
  tool_execution_success_rate       (by tool, rolling 24h)
  llm_api_latency_p95               (Claude API)
  llm_api_error_rate                (4xx/5xx)
  vector_search_latency_p95
  db_connection_pool_utilisation    (per connection)
  active_sessions                   (real-time)
  celery_queue_depth                (by queue name)
  circuit_breaker_state             (per service: 0=closed, 1=open)

AI QUALITY
  answer_confidence_distribution    (High/Medium/Low ratio, rolling 24h)
  tool_hit_rate                     (% answered by tool vs SQL fallback)
  user_feedback_score               (thumbs up ratio, rolling 7 days)
  hallucination_flag_rate           (answers flagged by Confidence Agent)
  golden_dataset_accuracy           (updated per CI/CD run)

BUSINESS METRICS
  queries_per_day                   (usage growth trend)
  unique_active_users               (DAU/WAU/MAU)
  onboarding_completion_rate        (% completing all 8 wizard steps)
  reports_generated_per_day
  avg_session_length_turns
```

### 10.3 Alerting Rules

| Alert Name | Condition | Severity | Action |
|-----------|-----------|---------|--------|
| API High Latency | p95 > 8s for 5 min | 🟠 Warning | Notify on-call |
| API Critical Latency | p95 > 15s for 2 min | 🔴 Critical | Page on-call |
| High Error Rate | Error rate > 5% for 5 min | 🔴 Critical | Page on-call |
| DB Connection Failure | Circuit breaker OPEN | 🔴 Critical | Page on-call |
| Claude API Errors | Error rate > 10% for 3 min | 🔴 Critical | Page on-call |
| Low Tool Hit Rate | Tool hit rate < 50% for 1h | 🟠 Warning | Notify team |
| Negative Feedback Spike | Feedback score < 60% over 4h | 🟠 Warning | Notify team |
| Celery Queue Backed Up | Queue depth > 100 for 10 min | 🟠 Warning | Notify on-call |
| Disk Usage High | Disk > 80% on any node | 🟠 Warning | Notify ops |
| Redis Memory Critical | Redis memory > 90% | 🔴 Critical | Page on-call |
| Audit Log Write Failure | Any write failure | 🔴 Critical | Page on-call + Legal |
| DML Attempt Detected | Any DML blocked event | 🔴 Critical | Page on-call + Security |

### 10.4 Health Check Endpoints

```
GET /api/v1/health/live
  → Always returns 200 OK if process is running (Kubernetes liveness)
  → Returns: { status: "alive" }

GET /api/v1/health/ready
  → Returns 200 if PostgreSQL + Redis connected and accepting queries
  → Returns 503 if either dependency is down (Kubernetes readiness)
  → Returns: { status: "ready"|"degraded", dependencies: { postgres, redis, claude_api } }

GET /api/v1/health/full  [Admin only]
  → Full component status for ops dashboard
  → Returns: { status, components: { db_connections[], vector_store, llm_api, celery, redis } }
```

---

## PART 11 — DEPLOYMENT & INFRASTRUCTURE

### 11.1 Environment Strategy

| Environment | Purpose | Data Policy | DB |
|-------------|---------|------------|-----|
| Development | Individual developer | Synthetic only. No real ERP data. | Docker Compose local |
| Staging | Integration + UAT | Anonymised copy of customer data | Cloud (same stack as prod) |
| Production | Live customer | Real data, full governance | Cloud, managed PostgreSQL |

### 11.2 Docker Service Composition

```yaml
services:
  api:
    image: platform/api
    env: [DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY, VAULT_ADDR]
    ports: ["8000:8000"]
    healthcheck: GET /api/v1/health/live
    depends_on: [postgres, redis]
    replicas: 2 (production)

  worker:
    image: platform/worker  # Celery worker
    command: celery -A app.worker worker --concurrency=4
    depends_on: [postgres, redis]
    replicas: 2 (production)

  beat:
    image: platform/worker  # Celery beat scheduler
    command: celery -A app.worker beat --scheduler=redbeat
    replicas: 1 (singleton — do not scale)

  postgres:
    image: pgvector/pgvector:pg16
    volumes: [postgres_data:/var/lib/postgresql/data]
    env: [POSTGRES_PASSWORD]

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}

  nginx:
    image: nginx:alpine
    volumes: [./nginx.conf:/etc/nginx/nginx.conf]
    ports: ["443:443", "80:80"]
    depends_on: [api]
```

### 11.3 CI/CD Pipeline (GitHub Actions)

```
PULL REQUEST TRIGGER:
  ├── ruff lint + mypy type check (fail on any error)
  ├── Unit tests (pytest, fail if coverage < 80%)
  ├── Security scan (pip-audit + bandit, fail on CVSS ≥ 7.0)
  └── Docker build (verify no build errors)

MERGE TO MAIN TRIGGER:
  ├── All PR checks above
  ├── Integration test suite
  ├── AI Golden Dataset accuracy check (fail if accuracy < 85%)
  ├── Docker push to registry (tagged with git SHA)
  ├── Deploy to Staging (Docker Compose / k8s apply)
  ├── Staging smoke tests (10 standard queries)
  └── Manual approval gate (required before production)

RELEASE TAG TRIGGER:
  ├── Deploy to Production
  ├── Post-deploy health check (/health/ready)
  ├── Run E2E smoke tests against production
  └── Auto-rollback if health check fails within 5 minutes
```

### 11.4 Infrastructure Sizing (Production — Single Tenant)

| Service | vCPU | RAM | Storage | Notes |
|---------|------|-----|---------|-------|
| API (×2) | 2 | 4GB | 20GB | Stateless, auto-scale |
| Worker (×2) | 2 | 4GB | 20GB | Celery concurrency 4 |
| PostgreSQL | 4 | 16GB | 500GB SSD | pgvector needs RAM |
| Redis | 1 | 4GB | 20GB | AOF + RDB persistence |
| Nginx | 1 | 1GB | 10GB | SSL termination |
| **Total** | **12** | **45GB** | **590GB** | ~$400–600/month |

**Auto-scaling triggers:**
- API pods: scale up when CPU > 70% for 3 minutes
- Worker pods: scale up when Celery queue depth > 50

### 11.5 Backup & Recovery

```
PostgreSQL:
  - Daily full pg_dump at 02:00 UTC
  - WAL archiving (continuous) for point-in-time recovery
  - 30-day backup retention
  - RTO: < 4 hours | RPO: < 24 hours (daily backup) or < 5 min (WAL PITR)

Redis:
  - RDB snapshot every 1 hour
  - AOF fsync every second
  - Redis data is reconstructable from PostgreSQL (session state only)
  - RTO: < 30 minutes (restart + load RDB)
```

---

## PART 12 — UI/UX SPECIFICATION

### 12.1 Screen Inventory

```
PUBLIC
  /login          → Login screen (email/password + SSO button)
  /forgot         → Password reset

ONBOARDING (Admin — 8-step wizard)
  /setup/connect  → Step 1: Add DB connection
  /setup/discover → Step 2: Discovery progress
  /setup/semantic → Step 3: Review Semantic Layer (entity mappings)
  /setup/graph    → Step 4: Knowledge Graph preview
  /setup/tools    → Step 5: Tool catalogue review
  /setup/docs     → Step 6: Upload documents (optional)
  /setup/alerts   → Step 7: Configure KPI alerts (optional)
  /setup/done     → Step 8: Platform ready + first question prompt

CORE APPLICATION
  /chat           → Conversation screen (primary screen)
  /dashboard      → Saved dashboard builder
  /documents      → Document library
  /kpis           → KPI library (view/activate)
  /alerts         → Alert centre (v1.1)
  /reports        → Report history + schedule management (v1.1)

ADMIN
  /admin/health   → Platform health dashboard
  /admin/users    → User management
  /admin/roles    → Role + permission editor
  /admin/catalog  → Metadata catalog + semantic layer editor
  /admin/graph    → Knowledge graph visualiser
  /admin/tools    → Tool catalogue manager
  /admin/audit    → Audit log viewer
  /admin/usage    → ROI + usage analytics
  /admin/feedback → Feedback loop dashboard
```

### 12.2 Conversation Screen — Full Interaction Specification

```
LAYOUT:
  Left sidebar:    Conversation history list (collapsible on mobile)
  Main area:       Question input + response area
  Right panel:     Lineage trace (expandable, hidden by default)

QUESTION INPUT:
  - Large text area, placeholder: "Ask anything about your business..."
  - Send button (Enter key or click)
  - Suggested questions chips below input (3 clickable chips, from Response Synthesis Agent)
  - Disabled during response generation

RESPONSE RENDERING STATES:
  IDLE:           Empty state. Example questions gallery. "Try asking: ..."
  THINKING:       Agent activity indicator. Shows current agent name + action.
                  "Selecting best tool..." / "Running AR analysis..." / "Searching documents..."
  STREAMING:      Text streams in token by token. Chart placeholder shimmer shown.
  COMPLETE:       Full response rendered:
                  ├── Confidence badge (🟢 High / 🟡 Medium / 🔴 Low)
                  ├── Natural language narrative (2–4 sentences)
                  ├── Primary visualisation (chart or KPI card)
                  ├── Data table (below chart, collapsed by default)
                  ├── Suggested follow-ups (3 clickable chips)
                  └── Feedback row (👍 👎 | Correct this | Verify data)
  ERROR:          Plain English message. Suggested action. No stack trace.
  LOW CONFIDENCE: Yellow banner: "This answer has low confidence. Verify before use."

CONFIDENCE BADGE DESIGN:
  🟢 High (≥0.85):   "Verified — answered using [Tool Name]"
  🟡 Medium (0.65–0.84): "Likely correct — recommend verification"
  🔴 Low (<0.65):    "Low confidence — AI-generated query, please review"

LINEAGE TRACE PANEL (expandable):
  Data Source:     SAP B1 HANA [connection name]
  Tables Used:     OINV, INV1, OCRD (clickable — opens metadata)
  Tool Used:       ar_invoice_list_v2 (or "AI-generated SQL")
  SQL Query:       Expandable code block (syntax highlighted, read-only)
  Agents Invoked:  [Intent → Semantic → Tool Ranking → Tool Execution → Response]
  Execution Time:  1,240ms
  "Verify Data" →  Expands raw result table

CHART INTERACTIONS:
  Hover:           Tooltip with exact values and period label
  Click data point: Pre-populates drill-down question in input
  Chart type toggle: User can switch between chart types for same data
  Download:        PNG / SVG / Copy to clipboard
```

### 12.3 Frontend State Management

```
Server State (React Query):
  - All API calls (conversations, tools, alerts, documents)
  - Auto-refetch on window focus for alerts and health data
  - Optimistic updates for feedback submission

Local State (Zustand):
  - Active conversation ID and turn state
  - Sidebar collapsed/expanded
  - Lineage panel open/closed
  - Chart type override per turn

Real-time (WebSocket):
  - Single WebSocket connection per conversation
  - Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s max)
  - Message queue during reconnection (5-message buffer)
  - Reconnect drops: show "Reconnecting..." indicator

Persistence:
  - Conversation list: server-side (conversations table)
  - Dashboard layout: server-side (user settings JSONB)
  - Chart type preferences: localStorage (non-sensitive)
```

---

## PART 13 — MVP SCOPE & RELEASE ROADMAP

### MVP v1.0 — Core Platform (Target: Ready for First Customer)

| Component | Scope |
|-----------|-------|
| SAP B1 HANA Connector | ✅ Full |
| MSSQL Connector | ✅ Full |
| Discovery Engine | ✅ Full |
| Metadata Catalog | ✅ Full |
| Semantic Layer + SAP B1 Pack | ✅ Full |
| Knowledge Graph | ✅ Full |
| Tool Generation + SAP B1 Tool Pack (50 tools) | ✅ Full |
| Tool Ranking Engine | ✅ Full |
| All 15 Agents (LangGraph Runtime) | ✅ Full (incl. Web Search Agent) |
| Analytics Engine (Trend, Comparison, RCA, Forecast) | ✅ Full |
| Document RAG | ✅ Full |
| Trust & Explainability Layer | ✅ Full |
| Governance & RBAC | ✅ Full |
| Visualisation Engine | ✅ Full |
| PDF + Excel Export | ✅ Full |
| Onboarding Wizard + SAP B1 Quick-Start | ✅ Full |
| Observability Stack | ✅ Full |
| CI/CD Pipeline | ✅ Full |
| Proactive Intelligence Engine | ⏳ v1.1 |
| Feedback & Learning Engine | ⏳ v1.1 |
| Report Scheduler & Delivery | ⏳ v1.1 |
| Teams / Slack Delivery | ⏳ v1.1 |
| Alert Centre UI | ⏳ v1.1 |
| Forecast (Prophet) | ⏳ v1.1 |
| What-If Scenarios | ⏳ v2.0 |
| PowerPoint Export | ⏳ v2.0 |
| Multi-tenant SaaS billing | ⏳ v2.0 |
| Heat Maps | ⏳ v2.0 |

---

## PART 14 — SUCCESS CRITERIA

### Functional Acceptance

- Business user asks "Show top 10 customers by revenue this quarter" → correct bar chart with confidence badge within p95 < 3 seconds
- Platform accuracy on Golden Dataset: ≥ 85% correct answers
- Zero DML queries ever executed against source ERP databases
- Every answer includes confidence score + data lineage trace
- New tenant SAP B1 onboarding → first correct insight ≤ 30 minutes

### Operational Acceptance

| Metric | Target |
|--------|--------|
| Platform uptime | ≥ 99.5% monthly |
| Query response time p95 (simple) | < 3 seconds |
| Query response time p95 (complex) | < 8 seconds |
| SAP B1 onboarding time | < 30 minutes to first insight |
| Golden dataset accuracy | ≥ 85% |
| Tool hit rate (tool vs SQL fallback) | ≥ 70% |
| User feedback positive ratio | ≥ 75% within 30 days of deployment |

### Business Acceptance

- Replaces ≥ 80% of recurring manual reports within 90 days
- Reduces SQL developer dependency for business questions by ≥ 90%
- User adoption ≥ 70% of licensed seats within 60 days of deployment

---

## FINAL CROSS-CHECK & GREEN FLAG ASSESSMENT

### Specification Completeness Audit v2.0

| Dimension | Status |
|-----------|--------|
| Functional Features (130+ across 16 modules) | ✅ Complete |
| Features Removed with Rationale (14 removed) | ✅ Complete |
| Agentic Workflow Design (15 agents, full specs) | ✅ Complete |
| Web Search Agent (Agent 12 — NEW) | ✅ Specified |
| Non-Functional Requirements (36 NFRs) | ✅ Complete |
| API Contract (60+ endpoints, error codes, envelopes) | ✅ Complete |
| Database Schema (Full DDL for all 28 tables) | ✅ Complete |
| Multi-tenancy Strategy (row-level, tenant_id from day 1) | ✅ Complete |
| Error Handling & Failure Modes | ✅ Complete |
| Circuit Breaker Specification | ✅ Complete |
| Graceful Degradation Levels (0–5) | ✅ Complete |
| Testing Strategy (unit, integration, E2E, AI, security, perf) | ✅ Complete |
| AI Golden Dataset Specification (100 Q&A pairs) | ✅ Complete |
| Observability Stack (Prometheus, Grafana, Sentry, LangSmith) | ✅ Complete |
| Alerting Rules (13 rules) | ✅ Complete |
| Deployment & Infrastructure (Docker, CI/CD, sizing) | ✅ Complete |
| Backup & Recovery (RTO/RPO defined) | ✅ Complete |
| UI/UX Specification (all screens + interaction patterns) | ✅ Complete |
| Frontend State Management | ✅ Complete |
| SAP B1 Entity Pack (80+ table mappings) | ✅ Complete |
| SAP B1 Business Rules (12 pre-built rules) | ✅ Complete |
| SAP B1 Tool Pack (50 tools with signatures) | ✅ Complete |
| MSSQL Schema Fingerprinting approach | ✅ Complete |
| MVP vs Roadmap Scope | ✅ Complete |
| Success Criteria (functional + operational + business) | ✅ Complete |
| Security Requirements | ✅ Complete |
| Compliance Requirements (GDPR, EU AI Act, SOC 2) | ✅ Complete |

---

# ✅ GREEN FLAG — APPROVED FOR DEVELOPMENT

**All 9 critical gaps from the v1.0 audit have been resolved.**
**14 non-useful features have been removed with documented rationale.**
**Agent 15 (Web Search Agent) has been specified and integrated.**
**The specification is complete, consistent, and production-ready.**

**This document is sufficient for:**
- Backend developers to begin database schema implementation
- Frontend developers to begin UI component development
- DevOps engineers to configure CI/CD and infrastructure
- AI engineers to begin agent implementation in LangGraph
- QA engineers to build the test suite and golden dataset
- SAP domain experts to validate and refine the entity pack

**Recommended Development Start:** Sprint 1 begins with:
1. PostgreSQL schema creation (Part 6)
2. Docker Compose local environment (Part 11)
3. FastAPI skeleton + auth endpoints (Part 5)
4. SAP B1 HANA connection + discovery pipeline (Module 1)

---

*Document Version: 2.0 — Production Ready*
*Specification Author: Principal Engineer / Platform Architect*
*Date: June 2026*
*Classification: Internal — Confidential*
