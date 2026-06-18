# Session Changelog — 2026-06-18: Conversational queries, ChatGPT-style UI, dark mode, text-to-SQL fallback, reasoning (end + live)

This document records everything changed in this session, **what** each change was
and **why**. It spans six pieces of work, in the order they were built:

1. Conversational / "human" queries answered properly (not the SQL pipeline)
2. ChatGPT-style chat UI (Markdown, example prompts, copy/regenerate, typewriter)
3. Dark theme with a toggle button
4. Text-to-SQL runtime fallback (when no curated tool matches)
5. Improved narrative system prompt (explanation + key insights)
6. Reasoning panel — first end-of-response, then **live** streaming as the agent thinks

Environment note (unchanged from prior session): the app runs natively. The chat
path uses the Anthropic API; the local key is invalid, so LLM-phrased replies fall
back to canned text and pure-data questions error at the LLM step. That is the
environment, not these changes. `pytest`/`pytest-asyncio`/`fakeredis` were installed
into `.venv` to run the suite (they are dev-only; `requirements.txt` untouched).

---

## 1. Conversational / "human" queries (context_agent)

**Problem:** "How many questions have I asked till now?" returned the generic
*"no tool matches against the available data"* error. Root cause: `context_agent`
only short-circuited three hard-coded meta patterns (previous question / previous
answer / summary). Anything else — counting, greetings, "who are you?", "what can
you do?" — fell through enrichment → intent_classifier → query_planner → no tool →
error_handler. The agent could route meta-questions but recognised only a narrow
slice.

**Changes — `backend/app/agents/context_agent.py`:**
- New detection regexes: `_META_COUNT` (how many questions/queries/times…),
  `_ASSIST_IDENTITY` (who/what are you, your name, are you a bot…),
  `_ASSIST_CAPABILITY` (what can you do / how can you help / how does this work),
  `_GREETING` and `_COURTESY` (anchored `^…$` so "hi"/"thanks" never fire inside a
  real data question like "say hi to customer X").
- New unified `_answer_conversational(...)` dispatcher, called whenever a
  `conversation_id` exists — so it works **even on the first turn** (no prior
  context). It returns `(intent_label, text, answer_data)` or `None` to pass a
  genuine data question through.
- **Counting is deterministic** — `_answer_count(...)` reads the real turn count
  from the DB (the Redis window only holds the last 10 turns), reports the
  current-conversation count plus the lifetime count across the user's
  conversations, and adds the in-flight (not-yet-persisted) question on top.
- **Replies are grounded LLM phrasing, not canned** — `_phrase(...)` sends the
  message to the LLM with a persona system prompt (`_CONVO_SYSTEM`) that keeps it
  an SAP B1 assistant (not a generic chatbot); `_capability_grounding(...)` pulls
  the tenant's **real active tools** (name/domain/description) from the DB and
  feeds them in, so identity/capability answers reflect what *this* connection can
  actually do and can't drift from the schema. The four `_FALLBACK_*` constants
  are used only if the LLM call fails, so the user always gets a sensible answer.
- The supervisor already routes a context_agent result with `answer_text` set to
  `END`, so these never reach the data pipeline.

**Why:** A multi-talent SAP B1 agent should handle the human/conversational layer
gracefully (counts, greetings, identity, capabilities) while preserving its
analytical power — without becoming a generic chatbot and without brittle canned
strings.

**Tests — `backend/tests/unit/test_conversation_memory.py`:** added count /
identity / capability / greeting / courtesy match (and negative) tests; LLM output
is used; fallback on LLM failure; greeting is LLM-phrased; capability is grounded
*and* the grounding text reaches the prompt; data questions still pass through
without calling the LLM.

---

## 2. ChatGPT-style chat UI

**Goal:** restructure the chat into a standard ChatGPT layout and add four
enhancements (chosen by the user): Markdown rendering, example-prompt empty state,
copy/regenerate, and streaming-style output.

**New deps:** `react-markdown`, `remark-gfm`, `@tailwindcss/typography`
(plugin wired into `frontend/tailwind.config.ts`).

**New files:**
- `frontend/src/components/chat/Markdown.tsx` — `react-markdown` + `remark-gfm`,
  styled with Tailwind Typography (`prose`). Renders assistant text (bold/bullets/
  tables/links). Needed because the new conversational + narrative replies use
  Markdown; previously assistant text was a plain `<p>` and would show raw `**`/`•`.
- `frontend/src/hooks/useTypewriter.ts` — client-side "streaming-style" reveal of a
  freshly-arrived answer (the backend returned full responses; real token streaming
  came later in item 6 for *reasoning*, while the final answer still types out).

**`frontend/src/pages/ChatPage.tsx` — full restructure:**
- Centered `max-w-3xl` column, full-width alternating user/assistant rows with
  avatars (user glyph; gradient ✨ for the assistant), subtle tint on assistant
  rows, sticky rounded composer with a hint line.
- Markdown rendering for assistant text (`AnswerText` → `Markdown`, with the
  typewriter applied to the newest answer).
- Example-prompt cards on empty conversations (4 SAP starters); clicking
  auto-creates a conversation if needed, then sends.
- Per-assistant-message **Copy** (answer text) and **Regenerate** (re-ask the
  question).
- Animated typing indicator replacing the old "Thinking…".
- All existing SAP richness preserved inside the assistant message: data tables,
  trend charts, SQL toggle, lineage, confidence/latency, feedback 👍👎, pin-to-
  dashboard, follow-up chips, clarification card.

---

## 3. Dark theme + toggle

**Infrastructure:**
- `frontend/tailwind.config.ts` — `darkMode: "class"`.
- `frontend/index.html` — inline pre-paint script applies the saved/system theme
  before React renders (no flash of light).
- `frontend/src/hooks/useTheme.ts` — zustand store (`theme`, `toggle`, `setTheme`);
  toggling flips the `dark` class on `<html>` and persists to `localStorage`.
- `frontend/src/components/layout/ThemeToggle.tsx` — Sun/Moon button.

**Wiring + styling:**
- `frontend/src/components/layout/AppShell.tsx` — toggle button at the bottom of
  the global left nav (reachable from every page); shell, logo, nav items and
  content background fully themed.
- `ChatPage.tsx`, `Markdown.tsx` (`dark:prose-invert`), and later `ReasoningPanel`/
  `LiveReasoning` carry full `dark:` variants — sidebar, rows, tables, follow-up
  chips, composer, empty states, etc.

**Caveat (documented):** the shell + chat experience are fully themed. The other
feature pages (Dashboards, Connections, Catalog, Tools, …) don't yet have their own
per-element `dark:` classes, so their light cards still render light inside the dark
shell until they get the same pass.

---

## 4. Text-to-SQL runtime fallback

**Goal (user request):** in the runtime phase, when **no curated tool** matches a
query, execute a text-to-SQL agent instead of erroring.

**New file — `backend/app/agents/text_to_sql.py` (`TextToSQLAgent`):**
- Loads the crawled schema catalog (tables/columns/FKs) for the connection (reuses
  `AISchemaGenerator._load_tables/_load_columns/_load_relations`).
- Asks the model (default/stronger model) for ONE T-SQL `SELECT`, grounded in the
  schema, resolving relative dates against today; returns `NONE` if unanswerable.
- `_clean_sql(...)` strips markdown fences/prose and isolates the `SELECT`/`WITH`.
- **Two guards before execution:** (1) `validate_sql()` — SELECT-only / DML block;
  (2) `AISchemaGenerator._validate_sql(...)` — every referenced table/column must
  exist in the crawled catalog (no phantom names). On failure → `error`.
- On success writes a synthetic `selected_tool` (`name="ad_hoc_text_to_sql"`,
  generated SQL as `sql_template`, empty `input_schema`), so the existing
  `sql_executor → response_formatter` path runs unchanged.

**Wiring:**
- `backend/app/agents/state.py` — added `use_text_to_sql: bool`.
- `backend/app/agents/query_planner.py` — the no-tool branch now sets
  `use_text_to_sql=True` (and logs) instead of returning an `error`.
- `backend/app/agents/supervisor.py` — new `text_to_sql` node; `_route_after_planner`
  routes a tool-less result with the flag to `text_to_sql`; new
  `_route_after_text_to_sql` → `sql_executor` on success, `error_handler` on
  failure; graph edges + topology docstring updated.

**Tests — `backend/tests/unit/test_text_to_sql.py`:** fallback routing (no tool →
text_to_sql; no flag → error; tool present → executor; text_to_sql success/failure
routing), `_clean_sql` (fences, leading prose, CTE, NONE sentinel), and the
reasoning builder.

---

## 5. Improved narrative system prompt (explanation + key insights)

**Change — `backend/app/agents/response_formatter.py` `_NARRATIVE_SYSTEM`:**
rewritten to produce **Markdown**: (1) a direct headline answer with the actual
numbers, (2) a **Key insights** bullet list (2–4 points citing real figures —
largest/smallest, gaps, comparisons, trends), (3) an optional interpretation/
caveat. Strict rules: use only numbers present in the result (no fabrication), no
SQL/technical jargon, no preamble, empty-result handling. Pairs with the new
Markdown rendering from item 2.

---

## 6. Reasoning — end-of-response panel, then live streaming

### 6a. Backend reasoning data
- `backend/app/agents/state.py` — added `reasoning: str | None`.
- `backend/app/agents/intent_classifier.py` — now surfaces the classifier's
  one-line `reasoning` (previously discarded).
- `backend/app/agents/response_formatter.py` — `_build_reasoning(...)` assembles a
  readable step trace (intent + domain → rationale → tool chosen *or* "generated
  SQL from schema" → tables queried → rows/time) into `lineage.reasoning`; lineage
  now **merges** the incoming `state.lineage` (preserving `text_to_sql` /
  `tables_used` / recalled memory) instead of overwriting it; also stores `intent`
  and `intent_reasoning`.

### 6b. End-of-response panel
- `frontend/src/components/chat/ReasoningPanel.tsx` (new) — a collapsible
  **🧠 Reasoning** button per assistant message showing the numbered steps, intent
  + confidence, tables queried, and tools considered (with scores). Wired into the
  answer card, fully dark-themed.

### 6c. Live reasoning (streamed as the agent thinks)
**User request:** show the reasoning *while* the AI is thinking, step-by-step, not
assembled at the end.

**Backend — `backend/app/api/v1/endpoints/conversations.py`:**
- New `POST /conversations/{id}/ask/stream` returning a `StreamingResponse` of
  NDJSON. It runs the compiled graph with LangGraph `astream(stream_mode="updates")`,
  accumulating state and emitting one `{"type":"step", node, label, intent}` line
  as **each node finishes** (so each step reflects the real per-query decision —
  intent + rationale, tool selected or text-to-SQL, row count, etc.). After the
  stream it persists the turn (fresh `AsyncSessionLocal`) and emits a final
  `{"type":"final","data":{…AskResponse…}}`.
- `_stream_step(node, state)` maps each graph node to a user-facing label.
- The original non-streaming `POST /ask` is kept (used as a fallback).

**Frontend:**
- `frontend/src/lib/api.ts` — exported `getTenant` for the streaming fetch.
- `frontend/src/hooks/useAskStream.ts` (new) — `askStream(...)` POSTs with `fetch`
  (axios can't read a streamed body), parses NDJSON lines, calls `onStep` as steps
  arrive and `onFinal` with the final payload. Throws on non-OK so callers can fall
  back.
- `frontend/src/components/chat/LiveReasoning.tsx` (new) — the live trace shown
  while thinking; steps appear as nodes finish, the most recent one pulses.
- `frontend/src/pages/ChatPage.tsx` — send flow reworked to stream: `busy` /
  `pendingQuestion` / `liveSteps` state; `handleSend` streams via `askStream`
  (falling back to the `useAsk` mutation if streaming is unavailable), then
  invalidates the turns query so the saved turn renders with its collapsed
  `ReasoningPanel`; the pending block shows the user's question + `LiveReasoning`.

**Note on granularity:** LLM calls inside a node aren't token-streamed; steps
appear at **node** granularity as each decision is made. That is the live
step-by-step "thinking" the reasoning panel shows.

---

## Verification

- **Backend:** affected unit suites pass (agent graph, runtime fixes, conversation
  memory, sprint7/8/9, text-to-SQL) — 278 passing at the text-to-SQL milestone,
  plus the new conversation tests. Graph compiles with the `text_to_sql` node;
  `_stream_step` mapper sanity-checked.
- **Frontend:** `tsc -b` clean and `vite build` succeeds at every milestone
  (CSS grew as Markdown/typography + dark variants were added).

## Known gaps / next steps

- Extend the full reasoning step-trace to the Trend / RCA / Document / Web agents
  (they build their own lineage, so their panel currently shows intent/confidence
  at minimum).
- Give the non-chat feature pages a `dark:` pass for full dark-mode coverage.
- True token-level streaming of the final answer (and within-node LLM streaming)
  remains a future enhancement; today's streaming is node-granular for reasoning,
  with a client-side typewriter for the final answer.
- Text-to-SQL recall edge cases (some phrasings embed below threshold) still degrade
  to the fallback, which is the intended safety behaviour.
