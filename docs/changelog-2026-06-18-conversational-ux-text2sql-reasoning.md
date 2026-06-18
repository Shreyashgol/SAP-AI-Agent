# Session Changelog — 2026-06-18: Conversational queries, ChatGPT-style UI, dark mode, text-to-SQL fallback, reasoning (end + live)

This document records everything changed in this session, **what** each change was
and **why**. It spans six pieces of work, in the order they were built:

1. Conversational / "human" queries answered properly (not the SQL pipeline)
2. ChatGPT-style chat UI (Markdown, example prompts, copy/regenerate, typewriter)
3. Dark theme with a toggle button — shell + chat, then all feature pages (§ 3a)
4. Text-to-SQL runtime fallback (when no curated tool matches)
5. Improved narrative system prompt (explanation + key insights)
6. Reasoning panel — first end-of-response, then **live** streaming as the agent thinks
7. Authentication — self-serve Sign Up (new org) + email Sign In + Forgot password,
   real auth flow (incl. a demo-login bug fix)

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

**Caveat (at the time):** initially only the shell + chat were themed; the other
feature pages were completed later — see § 3a.

### 3a. Dark theme across all feature pages (follow-up)
**Goal (user request):** make Dashboards, Connections, Catalog (Discovery), Semantic,
KG, Tools, Documents, Alerts and Admin work in dark/light. These were light-only
Tailwind (`bg-white`, `text-gray-900`, `border-gray-200`, …) with **no** `dark:`
variants. Fixed in three layers:

1. **Global dark defaults (`frontend/src/index.css`)** — two `@layer base` rules:
   - Form controls (`input`/`select`/`textarea`) → `bg-gray-900 text-gray-100
     border-gray-700` + dark placeholder, so un-backgrounded inputs are readable.
     Controls with an explicit `dark:bg-*` (chat composer, themed selects) override it.
   - Default border colour → Tailwind preflight defaults every border to light
     gray-200, so bare `border`/`border-b`/`border-l` would be bright lines on dark;
     a `.dark *` rule sets gray-700 (explicit `border-*`/`dark:border-*` still win).
2. **Systematic `dark:` variants** — **525 substitutions** across the 9 pages +
   `CustomToolBuilderPage` via a one-shot mapping script (cards `bg-white →
   dark:bg-gray-800`, text greys, borders, dividers, hovers, and status tints
   green/red/amber/blue/brand). The script was removed after running.
3. **Manual fixes** the class pass couldn't reach:
   - KG graph nodes hardcoded `backgroundColor:"white"` inline → theme-aware via the
     `useTheme` store (gray-800 in dark).
   - Leftover tokens: chat avatar, Discovery progress-bar track, Tool-catalogue
     indigo selection/hover; composer textarea got `dark:bg-transparent` to survive
     the new form-control base rule.

**Note:** rules-based pass (not visually rendered here) — vivid KG domain hex colours
are intentionally kept; chart axis/grid libraries may still need their own dark props.

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

## 7. Authentication — Sign Up + Sign In

**Goal (user request):** add/complete the auth feature that had been removed. Before
this, the backend had `login`/`refresh`/`logout`/`me` but **no register endpoint**,
and the frontend had **no login UI** — `AuthGate` silently auto-logged-in with
hardcoded demo credentials.

**Product decisions (chosen by the user):** Sign Up creates a **new organization
(tenant)** with the signer as `platform_admin`; Sign In is **by email** (email is
globally unique, so the tenant is resolved from the email — no org field); a
**"Continue as demo"** fallback is kept for quick testing.

### Backend
- `backend/app/schemas/auth.py` — new `RegisterRequest` (organization_name,
  full_name, email, password ≥ 8).
- `backend/app/services/auth/auth_service.py`:
  - `register_organization(...)` — enforces **global email uniqueness**, derives a
    unique tenant slug (`_unique_slug`), calls the existing
    `RBACService.bootstrap_tenant(...)` (tenant + 4 system roles + first
    `platform_admin`), then auto-signs-in.
  - `resolve_tenant_for_email(...)` — returns the tenant when exactly one active
    user has that email (used by email-only login).
  - `_issue_session(...)` — token issuance (access + refresh jti in Redis) factored
    out and shared by `login` and `register`.
- `backend/app/api/v1/endpoints/auth.py`:
  - `POST /auth/register` (201) — creates the org and sets the httpOnly refresh
    cookie.
  - `POST /auth/login` — resolves the tenant **from the email** when no valid
    `X-Tenant-ID` header is present; the header path still works (demo account).
- Tests — `backend/tests/integration/test_auth_register.py`: register creates org +
  signs in; email-only login; duplicate email → 409; short password → 422. (These
  need the integration test DB; they collect cleanly and run in CI.)

### Frontend
- `frontend/src/pages/SignInPage.tsx` / `SignUpPage.tsx` (new) — dark-themed forms
  with validation/error states; sign-in includes the **Continue as demo** button.
- `frontend/src/stores/auth.ts` (new) — zustand auth store
  (`status: loading|authed|anon`, `user`, `init/signIn/signUp/continueAsDemo/signOut`).
- `frontend/src/lib/api.ts` — `signIn`/`signUp` (raw axios with **no** tenant header
  so the backend resolves by email), `fetchMe`, `signOut`, `continueAsDemo`,
  `AuthUser` type; the 401 interceptor now does a **silent token refresh** (httpOnly
  cookie) instead of the old demo-relogin; `clearAuth` clears the tenant too; exported
  `getTenant`.
- `frontend/src/App.tsx` — public `/signin` + `/signup`; the rest behind
  `RequireAuth` (anon → `/signin`, spinner while validating the token on load via
  `useAuth.init()`); `PublicOnly` redirects already-authed users away from the auth
  pages. Replaces the old auto-login `AuthGate`.
- `frontend/src/components/layout/AppShell.tsx` — shows the signed-in user + a
  **Sign out** button next to the theme toggle.

**Note:** global email uniqueness is enforced at signup; if older seeded data shares
an email across tenants, email-only login returns a safe "invalid credentials"
rather than guessing. The demo account is unaffected (it uses the tenant-header path).

### 7a. Demo sign-in bug + stale credentials (follow-up)
**Problem:** "Continue as demo" showed "Demo sign-in is unavailable." Two causes:
(1) the demo defaults (`onboarder@testcorp.com`, tenant `a480c09a…`) didn't exist —
the DB only had tenant `2d829cfe…` ("Default") with `admin@example.com`; and (2) a
**latent backend bug** — when `_get_user_by_email` finds no user it runs a
timing-safe dummy `verify_password` against a **malformed** placeholder hash
(`"$2b$12$dummy_hash_padding_for_timing"`), which passlib rejects with `ValueError`
→ **HTTP 500** instead of a clean 401.

**Changes:**
- `backend/app/services/auth/auth_service.py` — replaced the malformed placeholder
  with a valid bcrypt hash (`_DUMMY_HASH`, computed once); unknown-email logins now
  return a proper **401**, not a 500.
- Seeded a real demo account `demo@example.com` / `Demo123!pass` (platform_admin) in
  the Default tenant (additive; doesn't touch `admin@example.com`).
- `frontend/src/lib/api.ts` — repointed demo defaults to tenant `2d829cfe…` /
  `demo@example.com`; `continueAsDemo` is now a single login call (no fragile
  second `/auth/me`).
- `frontend/src/pages/SignInPage.tsx` — surfaces the **real** error (backend
  unreachable / server error / API message) instead of a blanket "unavailable".

### 7b. Admin password reset + Forgot-password flow
- Reset `admin@example.com` to `Admin123!pass` (its original password was a discarded
  random `secrets.token_urlsafe(24)` from `deps.py`, so it was unrecoverable).
- **Forgot/reset password (new):**
  - `backend/app/schemas/auth.py` — `ForgotPasswordRequest/Response`,
    `ResetPasswordRequest`.
  - `backend/app/services/auth/auth_service.py` — `request_password_reset(...)`
    (single-use token in Redis, 30-min TTL; `None` if no single user matches) and
    `reset_password(...)` (consumes token, sets new hash, clears lockout).
  - `backend/app/api/v1/endpoints/auth.py` — `POST /auth/forgot-password` (always
    200, never reveals whether an email exists; returns the token in the response in
    **non-production** since no email service is configured) and
    `POST /auth/reset-password`.
  - Frontend — `ForgotPasswordPage` + `ResetPasswordPage`, a **Forgot password?**
    link on sign-in, routes `/forgot-password` + `/reset-password`,
    `forgotPassword`/`resetPassword` API helpers, and a shared `lib/authError.ts`
    (`authErrMessage`) adopted across the auth pages.
  - Tests — added to `tests/integration/test_auth_register.py`: forgot→reset→login,
    unknown-email-is-safe-200, bad-token-401.

---

## Verification

- **Backend:** affected unit suites pass (agent graph, runtime fixes, conversation
  memory, sprint7/8/9, text-to-SQL) — 278 passing at the text-to-SQL milestone,
  plus the new conversation tests. Graph compiles with the `text_to_sql` node;
  `_stream_step` mapper sanity-checked.
- **Frontend:** `tsc -b` clean and `vite build` succeeds at every milestone
  (CSS grew as Markdown/typography + dark variants were added). The all-pages dark
  pass (§ 3a) builds clean; coverage audited (every `bg-white` has a dark counterpart,
  plus `bg-gray-200`/`bg-indigo-50`/hex spot-checks).
- **Auth:** backend unit suites still pass after the `auth_service` refactor; the new
  register/login integration tests collect cleanly (they need the integration DB to
  execute, so they run in CI). Frontend `tsc`/`build` green with the new auth pages,
  store and routing.

## Known gaps / next steps

- Extend the full reasoning step-trace to the Trend / RCA / Document / Web agents
  (they build their own lineage, so their panel currently shows intent/confidence
  at minimum).
- Dark mode now covers all feature pages (§ 3a); remaining polish is visual-only —
  verify charts/graph visualizations in the running app and tune any vivid colours.
- True token-level streaming of the final answer (and within-node LLM streaming)
  remains a future enhancement; today's streaming is node-granular for reasoning,
  with a client-side typewriter for the final answer.
- Text-to-SQL recall edge cases (some phrasings embed below threshold) still degrade
  to the fallback, which is the intended safety behaviour.
- Auth follow-ups: password reset now exists, but there's no real **email delivery**
  (the reset token is returned in-response in non-production — wire SMTP/provider for
  prod), no email verification, and no invite-teammates-to-an-existing-org flow yet
  (signup always creates a new org). Silent refresh on 401 relies on the httpOnly
  refresh cookie round-tripping through the dev proxy.
