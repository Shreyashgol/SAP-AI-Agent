Done. The UI now shows all the fresh data.

  Root cause

  The frontend never sent auth — no Authorization token and no X-Tenant-ID header anywhere. Every data call (connections, KPIs,
  tools, semantic, catalog) was getting a 401, so all the pages came up empty regardless of what was in the database.

  What I changed (frontend/)

  1. src/lib/api.ts — the shared axios client now:
    - attaches X-Tenant-ID + Authorization: Bearer on every request (interceptor),
    - ensureAuth() bootstraps a login with the seeded admin and stores the token,
    - on a 401 it re-logs-in and retries once (handles token expiry).
  2. src/App.tsx — added an AuthGate that blocks first render until the token exists, so the initial queries are authenticated.
  3. Three hooks used raw axios (useTools, useKnowledgeGraph, useEmbeddings) and bypassed the interceptor — switched them to the
  shared client.
  4. useTools now requests limit=200 so the freshly generated tools aren't hidden past the default page of 50.

  Verified end-to-end (through the Vite proxy, same path the browser uses)

  connections: 2    tools: 131 (80 AI-generated, incl. the new schema-grounded ones)
  KPIs: 59          entities: 12      catalog: 12
  Typecheck and production build both pass.
  
  To view

  The dev server is running at http://localhost:5173 — check:
  - /connections (fresh connections), /discovery (catalog tables), /semantic (entities + KPIs), /tools (catalogue incl.
  AI-generated).

  Two notes:
  - This is a demo auto-login (seeded admin + tenant, overridable via VITE_TENANT_ID / VITE_DEMO_EMAIL / VITE_DEMO_PASSWORD), not
  a real login screen — wiring a proper login form would be the production follow-up.
  - The connections list shows 2 because the list endpoint returns only active connections (the earlier soft-deleted/renamed ones
  are filtered out).