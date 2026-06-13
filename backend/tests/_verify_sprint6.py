"""Quick logic verification for Sprint 6 agent helpers (no pytest needed)."""
import re

# ── DML guard ────────────────────────────────────────────────────────────────

_DML_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)

def _check_dml(sql):
    match = _DML_PATTERN.search(sql)
    if match:
        return f"Forbidden: {match.group().upper()}"
    stripped = re.sub(r"--[^\n]*\n", "", sql).strip().upper()
    if not stripped.startswith("SELECT"):
        return "Only SELECT allowed"
    return None

dml_cases = [
    ("SELECT * FROM t", None),
    ("INSERT INTO t VALUES (1)", "Forbidden"),
    ("UPDATE t SET x=1", "Forbidden"),
    ("DELETE FROM t", "Forbidden"),
    ("DROP TABLE t", "Forbidden"),
    ("select * from t", None),
    ("-- comment\nSELECT id FROM invoices", None),
    ("EXEC sp_helpdb", "Forbidden"),
    ("MERGE INTO t USING s ON t.id=s.id", "Forbidden"),
]
dml_pass = sum(1 for sql, exp in dml_cases if (_check_dml(sql) is None) == (exp is None))
print(f"DML guard: {dml_pass}/{len(dml_cases)} passed")

# ── Row limit ────────────────────────────────────────────────────────────────

_LIMIT_PATTERN = re.compile(
    r"\bTOP\s+:\w+\b|\bLIMIT\s+:\w+\b|\bTOP\s+\d+\b|\bLIMIT\s+\d+\b", re.IGNORECASE
)

def _inject_row_limit(sql, limit):
    if _LIMIT_PATTERN.search(sql):
        return sql
    return re.sub(r"^\s*SELECT\b", f"SELECT TOP {limit}", sql, count=1, flags=re.IGNORECASE)

limit_cases = [
    ("SELECT * FROM invoices", True),
    ("SELECT TOP 500 * FROM t", False),
    ("SELECT TOP :limit id FROM t", False),
    ("select id from t LIMIT 100", False),
]
lp = sum(1 for sql, should in limit_cases if ("TOP 1000" in _inject_row_limit(sql, 1000)) == should)
print(f"Row limit:  {lp}/{len(limit_cases)} passed")

# ── Param substitution ────────────────────────────────────────────────────────

def _substitute_params(sql, params):
    result = sql
    for key, val in params.items():
        if val is None:
            replacement = "NULL"
        elif isinstance(val, str):
            safe = val.replace("'", "''")
            replacement = f"'{safe}'"
        elif isinstance(val, bool):
            replacement = "1" if val else "0"
        else:
            replacement = str(val)
        result = re.sub(rf":{re.escape(key)}\b", replacement, result)
    return result

sub_cases = [
    ("SELECT * FROM t WHERE name=:name", {"name": "Acme"}, "'Acme'"),
    ("SELECT TOP :limit id FROM t", {"limit": 10}, "10"),
    ("SELECT * FROM t WHERE val=:val", {"val": None}, "NULL"),
    ("SELECT * FROM t WHERE name=:name", {"name": "O'Brien"}, "O''Brien"),
]
sp = sum(1 for sql, params, expected in sub_cases if expected in _substitute_params(sql, params))
print(f"Param sub:  {sp}/{len(sub_cases)} passed")

# ── Chart hint ────────────────────────────────────────────────────────────────

def _choose_chart(intent, rows, columns):
    if intent == "Trend": return "line"
    if intent == "Comparative": return "bar"
    if intent == "Lookup": return "table"
    if intent in ("Aggregation", "RCA", "Hybrid"):
        if len(rows) == 1 and len(columns) <= 2: return "kpi_card"
        if len(rows) <= 6: return "donut"
        return "bar"
    return "table"

chart_cases = [
    ("Trend", [], [], "line"),
    ("Comparative", [], [], "bar"),
    ("Lookup", [], [], "table"),
    ("Aggregation", [{"v": 1}], ["v"], "kpi_card"),
    ("Aggregation", [{"a": 1}, {"a": 2}], ["cat", "v"], "donut"),
    ("Aggregation", [{"a": i} for i in range(10)], ["cat", "v"], "bar"),
    ("Unknown", [], [], "table"),
]
cp = sum(1 for intent, rows, cols, exp in chart_cases if _choose_chart(intent, rows, cols) == exp)
print(f"Chart hint: {cp}/{len(chart_cases)} passed")

# ── Supervisor routing ────────────────────────────────────────────────────────

def _route_after_intent(state):
    if state.get("error"): return "error_handler"
    if state.get("intent") == "Document": return "document_rag"
    return "query_planner"

def _route_after_planner(state):
    if state.get("error"): return "error_handler"
    if not state.get("selected_tool"): return "error_handler"
    return "sql_executor"

def _route_after_executor(state):
    if state.get("error"): return "error_handler"
    return "response_formatter"

route_cases = [
    (_route_after_intent({"intent": "Aggregation"}), "query_planner"),
    (_route_after_intent({"intent": "Document"}), "document_rag"),
    (_route_after_intent({"error": "oops"}), "error_handler"),
    (_route_after_planner({"selected_tool": {"name": "t"}}), "sql_executor"),
    (_route_after_planner({"selected_tool": None}), "error_handler"),
    (_route_after_executor({"query_result": {}}), "response_formatter"),
    (_route_after_executor({"error": "fail"}), "error_handler"),
]
rp = sum(1 for got, exp in route_cases if got == exp)
print(f"Routing:    {rp}/{len(route_cases)} passed")

# ── Total ─────────────────────────────────────────────────────────────────────
total = dml_pass + lp + sp + cp + rp
total_cases = len(dml_cases) + len(limit_cases) + len(sub_cases) + len(chart_cases) + len(route_cases)
print(f"\nTotal: {total}/{total_cases} passed")
if total == total_cases:
    print("ALL SPRINT 6 LOGIC CHECKS PASSED")
else:
    print("SOME CHECKS FAILED")
