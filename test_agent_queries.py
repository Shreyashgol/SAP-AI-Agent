"""Fire a battery of test queries at the /ask endpoint and verify routing.

Covers every agent path: Lookup / Aggregation / Trend / Comparative (analytical),
RCA, Document (RAG), Hybrid, and Web — against the MEGATRADE_DEMO MSSQL database.

Run:  .venv/bin/python test_agent_queries.py
Reuses the same admin/tenant bootstrap as onboard_megatrade.py.
"""
import os
import sys
import json
import time

import requests

POLICY_DOC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_company_policy.md")

BASE = "http://localhost:8000/api/v1"
TENANT_ID = "2d829cfe-fb6f-40b8-9276-699b82b9ff5e"  # Default tenant
ADMIN_EMAIL = "demo@example.com"
ADMIN_PW = "Demo123!pass"
TH = {"X-Tenant-ID": TENANT_ID}

# (question, expected_intent) — accept any of the listed intents.
QUERIES = [
    # ── Analytical: Lookup ────────────────────────────────────────────────
    ("Show me the details for customer C20000.",                ["Lookup"]),
    ("List all open sales orders.",                             ["Lookup", "Aggregation"]),
    # ── Analytical: Aggregation ───────────────────────────────────────────
    ("What is our total revenue this year?",                    ["Aggregation"]),
    ("How many open A/R invoices do we have?",                  ["Aggregation"]),
    ("What is the total outstanding receivables across all customers?", ["Aggregation"]),
    # Demo data lives in early 2025 — target it explicitly so the SQL returns rows.
    ("What was our total invoiced revenue in 2025?",            ["Aggregation"]),
    # ── Analytical: Trend ─────────────────────────────────────────────────
    ("Show the monthly revenue trend for the last 6 months.",   ["Trend"]),
    ("How have sales orders trended week over week this quarter?", ["Trend"]),
    ("Show the monthly sales trend across 2025.",               ["Trend"]),
    # ── Analytical: Comparative ───────────────────────────────────────────
    ("Top 10 customers by revenue this year.",                  ["Comparative", "Aggregation"]),
    ("Compare sales this quarter versus last quarter.",         ["Comparative"]),
    ("Top 5 customers by revenue in 2025.",                     ["Comparative", "Aggregation"]),
    # ── RCA ───────────────────────────────────────────────────────────────
    ("Why did sales drop last month?",                          ["RCA"]),
    ("What is driving the spike in overdue invoices?",          ["RCA"]),
    # ── Document / RAG ────────────────────────────────────────────────────
    ("What is our customer payment terms policy?",              ["Document"]),
    ("Summarize the return and refund policy.",                 ["Document"]),
    # ── Hybrid ────────────────────────────────────────────────────────────
    ("Which customers are exceeding the credit limit defined in our credit policy?", ["Hybrid"]),
    ("Are any open invoices past the payment terms stated in our policy?", ["Hybrid"]),
    # ── Web ───────────────────────────────────────────────────────────────
    ("What is the latest SAP Business One release version?",    ["Web"]),
    ("What is the current industry benchmark for DSO in distribution?", ["Web"]),
]


def pp(label, r):
    try:
        body = r.json()
    except Exception:
        body = r.text
    print(f"[{r.status_code}] {label}: {json.dumps(body)[:300]}")
    return body


def upload_and_wait(s, H, path, timeout=180):
    """Upload a policy doc and poll until it's embedded ('ready') so RAG/Hybrid
    have something to retrieve. Returns the document_id or None."""
    if not os.path.exists(path):
        print(f"!! policy doc not found at {path} — RAG/Hybrid will return 'no docs'")
        return None
    with open(path, "rb") as f:
        r = s.post(f"{BASE}/documents/upload", headers=H,
                   files={"file": (os.path.basename(path), f, "text/markdown")},
                   data={"document_type": "policy", "department": "operations"})
    if r.status_code not in (200, 201):
        pp("upload document", r)
        return None
    doc_id = r.json()["id"]
    print(f"Uploaded policy doc {doc_id} — waiting for embedding…")
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = s.get(f"{BASE}/documents/{doc_id}", headers=H).json()
        st = d.get("status")
        if st == "ready":
            print(f"  document ready after {int(time.time()-t0)}s\n")
            return doc_id
        if st == "error":
            print(f"  document embedding FAILED: {d.get('error_message')}\n")
            return doc_id
        time.sleep(3)
    print("  timed out waiting for embedding (worker running?)\n")
    return doc_id


def ask(s, H, conv_id, conn_id, question, timeout=180):
    r = s.post(f"{BASE}/conversations/{conv_id}/ask", headers=H,
               json={"question": question, "connection_id": conn_id}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def test_hybrid_clarify_then_blend(s, H, conn_id):
    """Verify the chosen 'Clarify, then blend' behavior end to end: a Hybrid
    question that needs a SQL parameter should (turn 1) ask a clarifying question,
    then (turn 2, after the answer) route through hybrid_agent and blend the
    policy document into the final answer."""
    print("\n" + "=" * 70)
    print("HYBRID 'clarify then blend' (2-turn) check")
    print("=" * 70)
    r = s.post(f"{BASE}/conversations", headers=H,
               json={"title": "Hybrid clarify-then-blend", "connection_id": conn_id})
    conv_id = r.json()["id"]

    q1 = "Which customers are exceeding the credit limit defined in our credit policy?"
    d1 = ask(s, H, conv_id, conn_id, q1)
    print(f"Turn 1: intent={d1.get('intent')}  needs_clarification={d1.get('needs_clarification')}")
    print(f"  agents: {d1.get('agents_invoked')}")
    print(f"  Q: {q1}")
    print(f"  -> {d1.get('clarification_question') or (d1.get('answer_text') or '')[:160]}")

    # Turn 2: answer the clarification. The policy default limit is 50,000.
    q2 = "Use 50000 as the credit limit threshold for all customers."
    d2 = ask(s, H, conv_id, conn_id, q2)
    agents = d2.get("agents_invoked") or []
    blended = "hybrid_agent" in agents
    print(f"\nTurn 2: intent={d2.get('intent')}  hybrid_agent_ran={blended}")
    print(f"  agents: {agents}")
    print(f"  Q: {q2}")
    print(f"  A: {(d2.get('answer_text') or '')[:240]}")
    lineage = d2.get("lineage") or {}
    print(f"  hybrid_docs in lineage: {bool(lineage.get('hybrid_docs'))}")
    print("\nRESULT:", "✅ blended data + policy" if blended else
          "⚠️ did NOT reach hybrid_agent — follow-up was not re-tagged Hybrid")
    return blended


def main():
    s = requests.Session()

    # 1. Login
    r = s.post(f"{BASE}/auth/login", headers=TH,
               json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    if r.status_code != 200:
        pp("login", r)
        print("LOGIN FAILED — aborting"); sys.exit(1)
    b = r.json()
    token = b["data"]["access_token"] if "data" in b else b["access_token"]
    H = {"Authorization": f"Bearer {token}", "X-Tenant-ID": TENANT_ID}

    # 2. Find the MEGATRADE MSSQL connection (most recent active one)
    r = s.get(f"{BASE}/connections", headers=H)
    conns = (r.json() or {}).get("data") or r.json()
    if isinstance(conns, dict):
        conns = conns.get("items") or conns.get("connections") or []
    mssql = [c for c in conns if c.get("db_type") == "mssql"]
    conn_id = mssql[-1]["id"] if mssql else (conns[-1]["id"] if conns else None)
    print(f"Using connection_id={conn_id}  (found {len(conns)} connection(s))")

    # 3. Create a conversation
    r = s.post(f"{BASE}/conversations", headers=H,
               json={"title": "Agent routing test", "connection_id": conn_id})
    if r.status_code not in (200, 201):
        pp("create conversation", r); sys.exit(1)
    conv_id = r.json()["id"]
    print(f"conversation_id={conv_id}\n")

    # 3b. Upload a policy doc so RAG + Hybrid have content to retrieve
    upload_and_wait(s, H, POLICY_DOC)

    # Fast path: only run the 2-turn Hybrid clarify-then-blend check.
    if "--hybrid-only" in sys.argv:
        test_hybrid_clarify_then_blend(s, H, conn_id)
        return

    # 4. Fire each query
    results = []
    for i, (q, expected) in enumerate(QUERIES, 1):
        t0 = time.time()
        try:
            r = s.post(f"{BASE}/conversations/{conv_id}/ask", headers=H,
                       json={"question": q, "connection_id": conn_id}, timeout=180)
        except Exception as e:
            print(f"{i:>2}. EXC  {q!r}: {e}")
            results.append({"q": q, "ok": False, "exc": str(e)})
            continue
        dt = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            print(f"{i:>2}. HTTP {r.status_code}  {q!r}: {r.text[:200]}")
            results.append({"q": q, "ok": False, "http": r.status_code, "body": r.text[:200]})
            continue
        d = r.json()
        intent = d.get("intent")
        agents = d.get("agents_invoked") or []
        has_err = d.get("has_error")
        err = d.get("error_message")
        ans = (d.get("answer_text") or "")[:120].replace("\n", " ")
        intent_ok = intent in expected
        mark = "OK " if (intent_ok and not has_err) else ("INT" if not intent_ok else "ERR")
        print(f"{i:>2}. [{mark}] intent={intent} (exp {expected})  err={has_err}  {dt}ms")
        print(f"      Q: {q}")
        print(f"      agents: {agents}")
        if has_err:
            print(f"      ERROR: {err}")
        if d.get("needs_clarification"):
            print(f"      CLARIFY: {d.get('clarification_question')}")
        if ans:
            print(f"      A: {ans}")
        if d.get("sql_query"):
            print(f"      SQL: {d['sql_query'][:160]}")
        print()
        results.append({
            "q": q, "intent": intent, "expected": expected, "intent_ok": intent_ok,
            "has_error": has_err, "error": err, "agents": agents, "ms": dt,
        })

    # 5. Summary
    print("=" * 70)
    total = len(results)
    routed_ok = sum(1 for x in results if x.get("intent_ok"))
    no_error = sum(1 for x in results if x.get("has_error") is False)
    errored = [x for x in results if x.get("has_error") or x.get("http") or x.get("exc")]
    misrouted = [x for x in results if "intent_ok" in x and not x["intent_ok"]]
    print(f"SUMMARY: {total} queries | routed correctly: {routed_ok}/{total} | "
          f"no execution error: {no_error}/{total}")
    if misrouted:
        print("\nMISROUTED:")
        for x in misrouted:
            print(f"  - got {x['intent']} expected {x['expected']}: {x['q']}")
    if errored:
        print("\nERRORS:")
        for x in errored:
            print(f"  - {x.get('error') or x.get('body') or x.get('exc')}: {x['q']}")
    if not misrouted and not errored:
        print("\nAll queries routed correctly and executed without error. ✅")

    # 6. Dedicated end-to-end Hybrid 'clarify then blend' verification
    test_hybrid_clarify_then_blend(s, H, conn_id)


if __name__ == "__main__":
    main()
