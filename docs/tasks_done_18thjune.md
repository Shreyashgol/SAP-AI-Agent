You're welcome! Here's a quick state-of-play so we can pick up cleanly next time:

Done & verified this session
- Removed the hardcoded SAP B1 tool pack → AI-only onboarding; regenerated 12 catalog-valid tools on the live DB (5434).
- Fixed the runtime/analytical path: date defaulting, relative-date anchoring, trend CamelCase columns, ranker recall + domain filter.
- Fixed conversation memory: planner now uses the enriched question, broader follow-up markers, meta-question handler.
- Built long-term cross-conversation recall (migration 0005, ConversationMemoryService), verified A→B recall end-to-end.

Loose threads for next time (all noted in memory):
- Backfill embeddings for pre-0005 conversations (only new turns embed now).
- Polish the recall answer from raw "Q:/A:" into a natural summary.
- Known recall edge case: "average invoice value"-style phrasings still miss the ideal tool (embedding recall).
- Latent: app.worker.db engine lacks the JSON Decimal sanitizer that app.db.session has.
- Restart the backend (./run_local.sh --workers) to load this session's code changes.

All work is in the working tree (uncommitted) and the details are saved to project memory. Have a good one! 👋