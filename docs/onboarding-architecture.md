# Onboarding Phase Architecture

This document describes the onboarding (post-discovery) pipeline as currently
implemented: how a freshly connected customer database is crawled and turned
into a query-ready semantic layer.

> Onboarding is **AI-driven and schema-grounded**. Claude builds the entire
> semantic layer (entities, KPIs, tools) from the REAL crawled schema. The
> legacy hardcoded SAP B1 tool pack has been removed — it assumed
> tables/columns (OPCH, OITB, Cancelled, DocNum, …) that don't exist in every
> dataset and caused "Invalid object name / Invalid column name" failures at
> query time.

---

## Trigger

`POST /connections/{id}/discover` → Celery task `discovery.run_full`
(`backend/app/worker/tasks/discovery.py`).

---

## Phase 0 — Schema Crawl (`discovery.run_full`)

- Loads the connection from the DB and decrypts credentials from the vault.
- Opens a raw source-DB connection in a threadpool (MSSQL via `pyodbc`, HANA
  via `hdbcli`). Host is normalized for the current runtime (container vs bare
  metal) via `normalize_db_host`.
- Runs `SchemaCrawler.run_full()` — crawls all tables, columns, PKs, FKs, data
  types, sample values, and PII flags, persisting them into
  `metadata_tables` / `metadata_columns` / `metadata_relations`.
- Progress is streamed to Redis at `discovery:progress:{job_id}`
  (stages: starting → connecting → crawling → done).
- Updates connection health (`last_health_status`) and emits an audit log
  (`DISCOVERY_COMPLETED`).
- On a successful **full** crawl, kicks off the post-discovery intelligence
  pipeline via `build_post_discovery_pipeline(...).delay()`. Incremental crawls
  skip this; their diffs are handled by targeted refresh tasks.

---

## Phases 1–4 — Intelligence Pipeline

`build_post_discovery_pipeline()` returns a Celery `chain` (with one parallel
`group` at the end). AI-driven onboarding is the **only** path — there is no
hardcoded-pack fallback branch.

```
apply_erpref_prior            ← (SAP B1 only) warm-start the crawled catalog from data/erpref_*
      │
run_ai_mapping                ← Claude maps crawled tables to business entities
      │
embed_entities                ← first embedding pass; chat gains basic DB understanding
      │
generate_ai_collection        ← Claude generates KPIs + tools from the REAL schema
      │
group(
  embed_entities,             ← re-embed entities after AI enrichment
  embed_tools,                ← embed tools for vector search
)
```

The only strict dependency is **Database → Discovery → Metadata** (done by
Phase 0). Everything after is enrichment. All task signatures are immutable
(`.si`); each task keeps its own retry policy; any stage can be re-run via its
admin endpoint.

### Step 0 — `semantic.apply_erpref_prior` → `ErpRefPrior` (SAP B1 warm-start)

- File: `app/services/semantic/erpref_prior.py`, task in
  `app/worker/tasks/semantic.py`.
- Runs **first**, before AI mapping. Gated on `mssql_fingerprint`: it only acts
  when the crawled catalog is detected as `sap_b1` (otherwise a no-op). Toggle
  with `settings.erpref_prior_enabled`.
- Loads the SAP B1 reference knowledge from `data/erpref_enriched_part*.json`
  (97 core tables — business names, descriptions, and the join graph B1 does not
  declare at the DB level) and applies it as a **prior** on the crawled catalog:
  - `MetadataTable.ai_description` ← business name + description (fill, never clobber).
  - `MetadataColumn.ai_description` ← column business names (fill, never clobber).
  - `MetadataRelation` rows ← prior joins, **intersection-filtered**: an edge is
    written only when both legs' table+column exist in the crawl and the edge is
    new. The join's plain-English `purpose` is stored in `MetadataRelation.notes`
    (migration `0006`) and surfaced in the `_load_relations` hint
    (`OINV.CardCode -> OCRD.CardCode  -- Get customer name…`), so both
    `generate_ai_collection` and **runtime** `text_to_sql` pick the right join.
    This fills the empty FK graph that B1 leaves at the DB level.
- **Schema-grounded invariant preserved:** the prior only ever annotates what was
  actually crawled — it never invents a table, column, or join leg. A wrong hint
  can at most cause a generated tool to be rejected by the sqlglot guard, never
  cause bad SQL to ship.

### Step 1 — `semantic.run_ai_mapping` → `AIEntityMapper`

- File: `app/services/semantic/ai_mapper.py`, task in
  `app/worker/tasks/semantic.py`.
- Finds crawled tables not yet mapped to a `SemanticEntity`. With the entity
  pack skipped, all tables are "unmapped", so Claude maps them all from their
  real columns.
- Sends table names + columns to Claude; Claude assigns each table a business
  entity. Writes `SemanticEntity` rows to Postgres.

### Step 2 — `embedding.embed_entities`

- Embeds entity names + descriptions into pgvector so the chat runtime has a
  basic understanding of the DB immediately.

### Step 3 — `tools.generate_ai_collection` → `AISchemaGenerator`

- File: `app/services/semantic/ai_generator.py`, task in
  `app/worker/tasks/tools.py`.
- Loads real tables / columns / FKs / sample values (PII-flagged samples are
  excluded) from the crawled catalog and builds a JSON schema context.
- Calls Claude (`settings.anthropic_generation_model` = `claude-opus-4-8`) with
  a strict system prompt: reference ONLY real tables/columns, write valid T-SQL
  (`SELECT TOP :limit`, `[schema].[table]` bracket-quoting), and parameterise
  every user input as a named `:placeholder`.
- Claude returns a single JSON object with `kpis[]` and `tools[]`.
- KPIs are persisted as `KpiDefinition` rows (domain normalized to one of
  finance / sales / purchasing / inventory / operations).
- **Validation guard (sqlglot):** every generated tool's SQL is parsed as
  `tsql` (named params first substituted with a harmless literal). Any
  reference to a table or column absent from the crawled catalog — SELECT
  aliases excepted — causes the tool to be **dropped** (tracked via a
  `rejected` counter). This is what prevents phantom-column SQL from ever
  being persisted.
- Valid tools are written as `Tool` rows with `pack_source="ai_generated"`,
  plus `ToolTableDependency` links to the referenced metadata tables.

### Step 4 — `embed_entities` + `embed_tools` (parallel group)

- Re-embeds updated entities and embeds all tools for vector semantic search
  at query time.

---

## Optional — Knowledge Graph

If `include_knowledge_graph=True`, a `build_full_kg` step is appended to the
chain. Disabled by default (out of the MVP pipeline). Build it later via
`POST /knowledge-graph/build` or by flipping the flag.

Document processing is **not** part of this pipeline — it is per-upload
(`embedding.embed_document`).

---

## What was removed / left behind

- **Removed (tools):** `app/services/tools/sap_b1_tools.py`,
  `app/services/tools/pack_loader.py`, the `tools.apply_tool_pack` Celery task,
  and the `POST /tools/actions/apply-pack` endpoint. `build_post_discovery_pipeline`
  no longer has a pack fallback branch — it always returns the AI chain.
- **Left in place (unused by the pipeline):** the semantic *entity* pack
  (`app/services/semantic/sap_b1_pack.py` and the semantic `pack_loader.py`).
  Only the tool pack was deleted.

---

## Key files

| Concern | Path |
| --- | --- |
| Discovery task + pipeline builder | `backend/app/worker/tasks/discovery.py` |
| ERPRef prior (SAP B1 warm-start) | `backend/app/services/semantic/erpref_prior.py` |
| AI entity mapping | `backend/app/services/semantic/ai_mapper.py` |
| AI KPI/tool generation + SQL guard | `backend/app/services/semantic/ai_generator.py` |
| Semantic task wrappers | `backend/app/worker/tasks/semantic.py` |
| Tool task wrappers | `backend/app/worker/tasks/tools.py` |
| Schema crawler | `backend/app/services/discovery/crawler.py` |
