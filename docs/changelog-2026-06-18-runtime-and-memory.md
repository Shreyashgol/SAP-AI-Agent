# Session Changelog — 2026-06-17/18: Onboarding cleanup, Runtime fixes, Conversation memory

This document records everything changed in this session, **what** each change was
and **why**. All changes landed in commit `908ea3d`
("runtime phase completed and st and long term memory implemented").

Environment note: the app runs natively (no Docker). `run_local.sh` exports
`DATABASE_URL` pointing at the **native Postgres 17 on port 5434** (overriding the
`.env` value of 5433). The 5434 DB is the live one used by the app. Embeddings are
local (`BAAI/bge-large-en-v1.5`, 1024-dim, CPU).

---

## 1. Celery beat crash on startup (`ModuleNotFoundError: redbeat`)

**Problem:** `./run_local.sh --workers` crashed `celery beat` because it launches with
`--scheduler redbeat.RedBeatScheduler`, but the dependency was commented out in
`requirements.txt` and written under the wrong distribution name. The app genuinely
uses RedBeat (`celery_app.py` sets `redbeat_key_prefix`; report/discovery schedules
rely on it), so dropping the scheduler flag was not an option.

**Change:** `backend/requirements.txt` — `#redbeat==2.2.0` → `celery-redbeat==2.2.0`
(the PyPI distribution is `celery-redbeat`; it imports as `redbeat`). Installed it into
`.venv`.

**Why:** Restores scheduled discovery/report jobs without disabling the scheduler.

---

## 2. Removed the hardcoded SAP B1 tool pack (onboarding → AI-only)

**Problem:** Chat queries failed with `Invalid object name 'OPCH' / 'OITB'`. Root cause:
the connected dataset has only 6 tables (`INV1, OCRD, OINV, OITM, ORDR, OWHS`), but the
hardcoded SAP B1 tool pack seeded 80+ tools referencing HANA tables that don't exist
here. 51 such tools were active in the live DB; 27 referenced non-existent tables. This
contradicted the documented AI-onboarding design (tools should be generated from the
real crawled schema and SQL-validated against the catalog).

**Changes:**
- Deleted `backend/app/services/tools/sap_b1_tools.py` (the 80+ hardcoded tools) and
  `backend/app/services/tools/pack_loader.py` (`ToolPackLoader`).
- `backend/app/worker/tasks/tools.py` — removed the `tools.apply_tool_pack` Celery task
  and `_run_apply_pack`.
- `backend/app/api/v1/endpoints/tools.py` — removed the `POST /tools/actions/apply-pack`
  endpoint and its import.
- `backend/app/worker/tasks/discovery.py` — removed the hardcoded-pack fallback branch;
  `build_post_discovery_pipeline` now **always** runs the AI chain
  (`run_ai_mapping → embed → generate_ai_collection → embed`).
- Tests: deleted `test_sap_b1_tools.py`; updated `test_pipeline_chain.py` to the AI-only
  chain shape.
- DB cleanup: deleted all `pack_source='sap_b1'` tool rows on the live DB.
- Regenerated tools from the real schema via `AISchemaGenerator` → **12 catalog-valid
  tools**, embedded for retrieval.

**Why:** Tools must match the actual connected schema. Generating from the crawled
catalog (with SQL validated against it) eliminates the "Invalid object name" class of
errors and aligns onboarding with its intended AI-driven design.

---

## 3. Runtime / analytical path fixes (complex-query stress testing)

Stress-tested 9 complex queries across all intents. Fixes:

### 3a. Over-eager clarification on undated questions
**Problem:** AI-generated tools mark `date_from`/`date_to` as **required**, so undated
questions ("compare sales by city", "top 5 customers", RCA) bounced to clarification.
**Change:** `query_planner.py` `_apply_date_defaults` — missing date-range params default
to an all-time window (`from`→`1900-01-01`, `to`/`as_of`→today). Non-date required params
(e.g. a low-stock `threshold`) still clarify.
**Why:** Most BI questions are undated and should return all-time data, not interrogate
the user.

### 3b. Relative dates resolved to the wrong year
**Problem:** "this year" resolved to 2024 — the param-extraction LLM had no "today" anchor.
**Change:** `query_planner.py` — inject `TODAY'S DATE` into the extraction prompt.
**Why:** Relative dates ("this year", "last quarter", "recently") must resolve against
the real current date.

### 3c. Trend agent picked the wrong columns (CamelCase)
**Problem:** For `[SalesYear, SalesMonth, TotalSales, InvoiceCount]` the agent picked
`SalesYear` as the metric (narrating "total sales of 2,025") because `\byear\b`/`\btotal\b`
don't match inside CamelCase SAP column names.
**Change:** `trend_agent.py` `_normalize` splits CamelCase/snake_case before pattern
matching; date columns are excluded from metric candidates; a year+month pair composes a
`YYYY-MM` period label.
**Why:** SAP/MSSQL columns are CamelCase; the metric must be the real measure, not a date
dimension.

### 3d. Ranker recall + out-of-data precision
**Problem:** When every tool scored below the 0.60 similarity threshold the ranker
returned "no tool found" (the keyword fallback only fired when there were *zero*
embeddings, and it matched the whole query as one substring — effectively dead).
**Changes:** `vector_search.py` — fall back to keyword search when nothing clears the
threshold; rewrote `_tool_keyword_fallback` to tokenise the question and require **≥2
token hits** (so a single common word like "total" doesn't match an unrelated tool for a
genuinely out-of-data question such as accounts-payable).
**Why:** Improves recall for answerable questions while still correctly returning "no tool
matches" for data the schema doesn't contain.

### 3e. Ranker hard domain filter removed
**Problem:** "invoiced revenue" was classified `finance` but the matching tool is tagged
`sales`; the ranker hard-filtered candidates by domain → zero candidates.
**Change:** `ranker.py` — domain is no longer a retrieval filter, only a soft `+W_DOMAIN`
scoring bonus.
**Why:** LLM domain classification is fuzzy; it should never zero out all candidates.

### 3f. Stale error message
**Change:** `query_planner.py` — replaced "Try applying the SAP B1 tool pack" (the pack is
gone) with an accurate "no tool matches against the available data" message.

---

## 4. Conversation memory — short-term fixes

### 4a. Planner ignored resolved context (the big one)
**Problem:** `context_agent` correctly rewrote follow-ups ("show the top 3 of those" →
"top 3 cities by total sales"), but `query_planner` ranked tools on the raw
`state["question"]`, throwing the resolution away → every drill-down failed.
**Change:** `query_planner.py` — use `state.get("enriched_question") or state["question"]`.
**Why:** Every other terminal agent already used the enriched question; the planner was the
lone exception, which broke all follow-ups.

### 4b. Short follow-ups not enriched
**Change:** `context_agent.py` — broadened `_REFERENCE_MARKERS` (added "what about", "the
top/lowest one", "drill", etc.) and now also enrich any question ≤7 words when prior
context exists.
**Why:** Short follow-ups like "what about the lowest one?" had no marker and were skipped.

### 4c. Meta-questions mis-routed
**Problem:** "what was my previous question?" got rewritten *into* the previous question
and sent to the SQL planner.
**Change:** `context_agent.py` `_answer_meta` answers previous-question / previous-answer /
recap requests directly from the Redis window; `supervisor.py` routes to `END` when
`answer_text` is already set (added `END: END` to the context node's conditional edges).
**Why:** Questions about the conversation must be answered from history, not the database.

---

## 5. Conversation memory — long-term (cross-conversation recall)

Short-term memory (within one conversation, Redis window) already existed. Long-term
memory (across conversations) did not, so it was built as RAG over conversation history.

**Changes:**
- `backend/alembic/versions/0005_conversation_turn_embeddings.py` — new
  `conversation_turn_embeddings` table: `vector(1024)` + HNSW cosine index, scoped to
  tenant + user. `turn_id` has **no FK** because `conversation_turns` has a composite PK
  `(id, created_at)` for partitioning (a single-column FK is rejected); cleanup rides the
  `conversation_id` CASCADE to `conversations`.
- `backend/app/models/conversation.py` — `ConversationTurnEmbedding` ORM model.
- `backend/app/services/conversation/memory.py` — `ConversationMemoryService`:
  `embed_turn` (embeds "Q:…/A:…", upsert per turn, non-fatal) and `recall` (pgvector
  `cosine_distance`, tenant+user scoped, excludes the current conversation, top-3,
  ≥0.55 similarity).
- `backend/app/services/conversation/manager.py` — `save_turn` embeds each turn after
  persisting (non-fatal).
- `backend/app/agents/context_agent.py` — recalls relevant prior turns **before** the
  no-context early exit. If the question matches `_RECALL_INTENT` ("what did we discuss…",
  "remind me…", "did we look at…") and there are hits, it answers **directly from memory**
  (`intent="Recall"`, short-circuits to END). Otherwise recalled turns are injected into
  the enrichment history and surfaced in `lineage.recalled_memory`.

**Why:** Lets the assistant remember and reuse what was discussed in earlier sessions,
user-scoped, without re-querying the database — while not hijacking normal data questions.

**Verified E2E:** seeded conversation A (sales-by-city, inventory-by-category) → a new
conversation B recalled both from memory; a plain data question ("how many open sales
orders?") was not hijacked (recall hits=0).

---

## 6. Tests

- Added `backend/tests/unit/test_runtime_fixes.py` — date defaulting, trend CamelCase
  column detection, composite period labels.
- Added `backend/tests/unit/test_conversation_memory.py` — meta-question handling,
  follow-up markers, recall-intent regex, memory content building.
- Updated `backend/tests/unit/test_pipeline_chain.py` to the AI-only pipeline shape.
- Deleted `backend/tests/unit/test_sap_b1_tools.py`.
- Full runtime/agent/conversation suite passes. The only failing tests are pre-existing
  and unrelated: `test_sprint13` (missing prod Docker/nginx/redis files in this native
  setup) and 2 in `test_mssql_connection` (a `SimpleNamespace` fixture drift).

---

## 7. Known gaps / next steps

- **Backfill** embeddings for pre-`0005` conversations (only new turns embed going forward).
- **Polish** the recall answer from the raw "Q:…/A:…" snippet into a natural summary.
- **Embedding-recall edge case:** phrasings like "average invoice value" still embed <0.60
  and miss the ideal tool — degrades gracefully to "no tool matches".
- **Latent:** `app.worker.db`'s engine lacks the JSON Decimal/datetime sanitizer that
  `app.db.session` has — harmless for the chat path (uses `db.session`), but a worker path
  persisting Decimals to JSONB would crash.
- After pulling these changes, restart the backend with `./run_local.sh --workers`.
