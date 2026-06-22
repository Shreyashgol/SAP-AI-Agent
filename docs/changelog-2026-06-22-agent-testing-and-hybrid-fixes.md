# 2026-06-22 — Agent test harness, Hybrid routing fixes, findings

Built an end-to-end test harness that exercises every agent against the
`MEGATRADE_DEMO` MSSQL database, used it to surface routing/data issues, and
fixed the two that were in scope (Hybrid intent detection + clarification
follow-up intent). Two further issues are diagnosed but deferred.

## What was added

| File | Purpose |
|---|---|
| `test_agent_queries.py` (repo root) | Fires 20 queries covering all agents at `POST /conversations/{id}/ask`, checks routed `intent` + `has_error`, prints a pass/fail summary. Uploads a policy doc first (so RAG/Hybrid have content) and runs a 2-turn Hybrid "clarify then blend" check. `--hybrid-only` flag for the fast path. |
| `sample_company_policy.md` (repo root) | Demo policy doc (payment terms, credit, returns, procurement) with concrete numbers so RAG/Hybrid answers can cite them. |
| `docs/test-queries-by-agent.md` | Copy-paste query reference by agent (Lookup/Aggregation/Trend/Comparative/RCA/Document/Hybrid/Web) for running locally in the chat UI, with prerequisites and caveats. |

## Environment notes discovered

- The live backend is the **native** uvicorn (`.venv/bin/uvicorn app.main:app
  --reload`) on PG **port 5434** — the Docker Postgres (5433) is stopped. `.env`
  says 5433 but the process env overrides to 5434.
- Working tenant/creds for the 5434 DB: tenant `2d829cfe-…` ("Default"), login
  `demo@example.com` / `Demo123!pass`. Active MSSQL connection `dum`
  (`49b60019-…`). (The `onboarder@testcorp.com` / `a480c09a-…` creds belong to
  the stopped Docker 5433 DB.)
- API base is `/api/v1`; health is `/api/v1/health/live`.

## Test results

- **Routing: 20/20** queries classified to the correct agent.
- **RAG works** once `sample_company_policy.md` is uploaded — answered Net-30
  payment terms and the return policy with citations.
- **Web** returns real, sourced answers (SAP B1 version, DSO benchmark).
- **Analytical** returns real data when queries use an **explicit year**
  ("…in 2025" → $870k across 4 customers).

## Fixes applied

### 1. Hybrid intent under-detection — `backend/app/agents/intent_classifier.py`

The classifier tagged policy-grounded data questions (e.g. "Are any open
invoices past the payment terms stated in our policy?") as Lookup, so
`hybrid_agent` never ran. Strengthened the Hybrid intent definition with explicit
cues ("per our policy", "stated in our policy", "defined in our credit policy")
and examples. Result: both demo Hybrid queries now classify as Hybrid, and the
**single-turn blend works** — the payment-terms query runs `hybrid_agent` and
cites the policy.

### 2. Clarification follow-ups losing intent — `backend/app/agents/context_agent.py`

When a Hybrid query asked a clarifying question and the user answered, the
follow-up was re-classified as plain Aggregation (intent lost → no blend). Two
changes:
- Added an enrichment rule: if the latest message answers a clarifying question,
  rewrite it back into the **original** question with the new detail filled in,
  preserving references to a policy/document.
- Stopped the marker-skip heuristic from bypassing enrichment on a clarification
  follow-up (detected via the prior assistant turn ending in `?`).

Result: the follow-up turn now correctly **stays Hybrid**.

## Issues diagnosed but NOT fixed (deferred)

### A. Hybrid 2-turn blend still blocked by a tool/param gap

The "customers exceeding the credit limit per our policy" query stays Hybrid but
re-clarifies instead of blending. Root cause is in `query_planner` / `ToolRanker`:
it selects a **customer-scoped tool** whose required param can't be satisfied by
"all customers", so `_extract_params` leaves it null and `sql_executor` clarifies
again. The catalog has no "all customers over credit limit" tool. **Fix needed:**
add such a tool, or a planner/text-to-SQL fallback when a required param is
unsatisfiable. (The blend path itself is proven via the payment-terms query.)

### B. SQL validator rejects `UNION` of SELECTs

`backend/app/services/sql/validator.py` `_is_select_statement` only accepts
`exp.Select` / `exp.With`, but sqlglot parses `SELECT … UNION SELECT …` as
`exp.Union`, so a read-only UNION is rejected ("Only SELECT statements are allowed
(got Union)"). RCA's `text_to_sql` intermittently emits UNION for
period-over-period comparison, so the RCA query errors flakily. **Fix needed:**
allow `exp.Union` / set-operations when all leaves are SELECT (`_find_dml_node`
already guards against DML inside).

## Other observations

- **Relative dates** ("this year"/"this quarter") anchor to 2026 and miss the
  Jan-2025 demo data; handling is inconsistent (some tools ignore the filter,
  some apply it). Phrase analytical tests with explicit years.
- **Trend** always reports a "single data point" — the demo DB has only one month
  (Jan 2025) of data. Data limitation, not a bug.
- **Lookup over-clarifies** — "show customer C20000" asks "how many details?"
  instead of returning the record.
- RCA routing is non-deterministic on "why did sales drop last month?".

## Suggested next steps

1. Apply the **UNION validator fix** (small, safe, makes RCA reliable).
2. Add a **"customers over credit limit" tool** (or unsatisfiable-param fallback)
   to close the Hybrid 2-turn blend.
3. Load **multi-month demo data** so Trend/Comparative have something to show.
