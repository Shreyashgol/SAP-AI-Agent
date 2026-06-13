# Intelligence Pipeline — MSSQL → Chat

How a connected MSSQL (SAP B1) database becomes answerable questions.
As of 2026-06-13 the entire pipeline runs **automatically** after a full
discovery — no manual admin steps are required for chat to work.

This is **not** a strict sequential pipeline. The only strict dependency is:

```
Database → Discovery → Metadata Storage
```

After metadata exists, enrichment engines run independently and in
parallel, and **chat becomes usable before every advanced feature is
fully generated** (an early embedding pass follows the entity pack).

```
MSSQL (user DB)
   │  POST /discovery/{connection_id}/start
   ▼
Phase A    Discovery Engine → Metadata Catalog
           crawler.py — metadata_tables / columns / relations
   │  (auto-triggered on success — build_post_discovery_pipeline)
   ▼
Foundation Entity Pack + first embedding pass
           mssql_fingerprint.py detects ERP → sap_b1 pack (no LLM);
           embed_entities → chat already understands the schema
   │
   ├───────────────┬───────────────┐
   ▼               ▼               ▼
Phase B    AI Metadata     KPI Engine          Tool Engine        (parallel
           ai_mapper.py    seed KPIs →         tool pack →         Celery
           (Claude)        KPI tools           connection tools    workers)
   └───────────────┴───────────────┘
                   ▼
Phase C    Embedding Engine (entities ∥ tools) → pgvector
           HNSW (m=16, ef_construction=128)
                   ▼
Phase D    Chat Runtime — LangGraph agents, tsql dialect,
           sqlglot-validated, TOP-capped → POST /conversations/{id}/ask
```

## Where the orchestration lives

`backend/app/worker/tasks/discovery.py` → `build_post_discovery_pipeline()`,
enqueued automatically after a successful **full** crawl.

| Phase | Tasks | Notes |
|---|---|---|
| Foundation | `semantic.apply_pack`, `embedding.embed_entities` | Deterministic, fast; chat gets basic understanding here |
| B — AI Metadata | `semantic.run_ai_mapping` | Claude maps tables the pack didn't cover |
| B — KPI Engine | `semantic.seed_kpis` → `tools.generate_kpi_tools` | Internal order only (KPI tools need KPI defs) |
| B — Tool Engine | `tools.apply_tool_pack` → `tools.generate_for_connection` | Internal order only |
| C — Join | `embedding.embed_entities`, `embedding.embed_tools` | Final pass picks up everything Phase B produced |

**MVP scope (deliberate):** the knowledge graph is *not* in the default
pipeline — pass `include_knowledge_graph=True` or trigger
`POST /knowledge-graph/build` when you want it. Advanced analytics, report
intelligence, and scheduled insights are likewise on-demand features, not
pipeline stages. Document processing is per-upload
(`embedding.embed_document`), independent of this pipeline.

Operational notes:
- Phase B branches run on parallel prefork workers (one process per CPU).
- Mid-chain groups become chords → require the Celery result backend
  (Redis — already configured).
- A failed branch (after its own retries) blocks Phase C; chat still works
  on the Foundation embeddings, and any stage can be re-run via its admin
  endpoint (below) to resume.
- Incremental re-discovery does **not** re-run the pipeline; schema diffs go
  through targeted refresh tasks (`kg.build_for_entity`, `tools.deprecate_for_table`).

## SAP B1 on MSSQL detection (SL-011)

`app/services/semantic/mssql_fingerprint.py` scores crawled table names
against ERP signatures. SAP B1 is detected via its characteristic tables
(`OCRD`, `OINV`, `ORDR`, `OITM`, `OJDT`, …) and maps to the full `sap_b1`
entity pack — the same pack used for HANA. Dynamics BC and Sage 300 map to
their packs; unrecognized schemas fall back to AI-only mapping.

## Watching it run

```bash
docker compose logs -f worker          # stage-by-stage progress
docker compose exec api python -c "..."  # or query the tables directly:
```

Sanity queries (psql, host port 5433):

```sql
SELECT COUNT(*) FROM metadata_tables;     -- after discovery
SELECT COUNT(*) FROM semantic_entities;   -- after pack/AI mapping
SELECT COUNT(*) FROM kpi_definitions;     -- after KPI seed
SELECT COUNT(*) FROM knowledge_graph_nodes;
SELECT COUNT(*), status FROM tools GROUP BY status;
SELECT COUNT(*) FROM tool_embeddings;     -- chat is ready when > 0
```

## Manual triggers (rerun a single stage)

Each stage still has its admin endpoint: `/semantic/apply-pack`,
`/semantic/ai-map`, `/semantic/kpis/seed`, `/knowledge-graph/build`,
`/tools/apply-pack`, `/tools/generate`, `/tools/generate-kpis`,
`/embeddings/tools`, `/embeddings/entities`.

## Related tests

- `backend/tests/unit/test_pipeline_chain.py` — chain stage order/args +
  SAP B1 / Dynamics / fallback fingerprint detection.
- `backend/tests/unit/test_sap_b1_pack.py`, `test_semantic_layer.py`,
  `test_knowledge_graph.py`, `test_agent_graph.py` — per-stage suites.
