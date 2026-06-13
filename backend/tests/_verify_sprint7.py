"""Standalone verification for Sprint 7 logic (no pytest, no imports from app)."""
import re
import uuid

# ─────────────────────────────────────────────────────────────────────────────
# 1. SQL Validator — regex fallback (self-contained)
# ─────────────────────────────────────────────────────────────────────────────

_DML_FALLBACK = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)
_FORBIDDEN_TABLE_PATTERNS = re.compile(
    r"\b(INFORMATION_SCHEMA|SYS\.TABLES|SYS\.COLUMNS|SYS\.OBJECTS"
    r"|SYSOBJECTS|SYSCOLUMNS|MASTER\.\.|MSDB\.\.|MODEL\.\.)\b",
    re.IGNORECASE,
)

def _regex_validate(sql):
    if not sql or not sql.strip():
        return False, "empty"
    if _DML_FALLBACK.search(sql):
        return False, "dml"
    stripped = re.sub(r"--[^\n]*\n", "", sql).strip().upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
        return False, "not select"
    if _FORBIDDEN_TABLE_PATTERNS.search(sql):
        return False, "system table"
    return True, None

regex_cases = [
    ("SELECT * FROM OINV",                          True),
    ("SELECT DocTotal FROM OINV WHERE x='y'",       True),
    ("WITH cte AS (SELECT 1) SELECT * FROM cte",    True),
    ("INSERT INTO t VALUES (1)",                    False),
    ("UPDATE t SET x=1",                            False),
    ("DELETE FROM t",                               False),
    ("DROP TABLE t",                                False),
    ("TRUNCATE TABLE t",                            False),
    ("CREATE TABLE t (id INT)",                     False),
    ("EXEC sp_help",                                False),
    ("SELECT * FROM INFORMATION_SCHEMA.TABLES",     False),
    ("SELECT * FROM SYS.TABLES",                    False),
    ("",                                            False),
    ("   ",                                         False),
]

rv_pass = 0
for sql, expected_valid in regex_cases:
    ok, _ = _regex_validate(sql)
    if ok == expected_valid:
        rv_pass += 1
    else:
        print(f"  FAIL regex: {sql[:60]!r} => {ok} (expected {expected_valid})")
print(f"SQL validator (regex): {rv_pass}/{len(regex_cases)} passed")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Context agent — reference marker detection
# ─────────────────────────────────────────────────────────────────────────────

_REFERENCE_MARKERS = re.compile(
    r"\b(it|its|they|them|their|that|those|this|these|"
    r"the same|previous|prior|last|above|aforementioned|"
    r"do the same|show me more|break it down|why|how about)\b",
    re.IGNORECASE,
)

marker_cases = [
    ("Show me more about it",                       True),
    ("Do the same for last month",                  True),
    ("Why did sales drop?",                         True),
    ("Show previous quarter",                       True),
    ("Total revenue in Q3 2024",                    False),
    ("Revenue from Acme Corp in January 2024",      False),
    ("Show total invoices for 2024",                False),
]

cm_pass = 0
for q, should_match in marker_cases:
    matched = bool(_REFERENCE_MARKERS.search(q))
    if matched == should_match:
        cm_pass += 1
    else:
        print(f"  FAIL marker: {q!r} => {matched} (expected {should_match})")
print(f"Context markers:       {cm_pass}/{len(marker_cases)} passed")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Clarification agent — param humanisation
# ─────────────────────────────────────────────────────────────────────────────

def _humanise_params(missing, schema):
    schema_map = {p["name"]: p.get("description", "") for p in schema}
    result = []
    for name in missing:
        desc = schema_map.get(name, "")
        if desc and len(desc) < 60:
            result.append(desc)
        else:
            result.append(name.replace("_", " ").title())
    return result

hum_cases = [
    (["start_date"], [{"name": "start_date", "description": "Start of period"}], ["Start of period"]),
    (["customer_code"], [{"name": "customer_code", "description": ""}], ["Customer Code"]),
    (["item_code"], [], ["Item Code"]),
    ([], [], []),
    (
        ["start_date", "end_date"],
        [{"name": "start_date", "description": "From"},
         {"name": "end_date", "description": "To"}],
        ["From", "To"],
    ),
]

hp_pass = 0
for missing, schema, expected in hum_cases:
    result = _humanise_params(missing, schema)
    if result == expected:
        hp_pass += 1
    else:
        print(f"  FAIL humanise: {missing} => {result!r} (expected {expected!r})")
print(f"Param humanisation:    {hp_pass}/{len(hum_cases)} passed")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Supervisor routing — clarification branch
# ─────────────────────────────────────────────────────────────────────────────

def _route_after_executor(state):
    if state.get("needs_clarification"):
        return "clarification_agent"
    if state.get("error"):
        return "error_handler"
    return "response_formatter"

def _route_after_context(state):
    if state.get("error"):
        return "error_handler"
    return "intent_classifier"

route_cases = [
    (_route_after_executor({"needs_clarification": True}),                     "clarification_agent"),
    (_route_after_executor({"needs_clarification": False}),                    "response_formatter"),
    (_route_after_executor({"needs_clarification": True, "error": "boom"}),    "error_handler"),
    (_route_after_executor({"error": "fail"}),                                 "error_handler"),
    (_route_after_executor({}),                                                "response_formatter"),
    (_route_after_context({}),                                                 "intent_classifier"),
    (_route_after_context({"error": "ctx fail"}),                              "error_handler"),
]

rp_pass = sum(1 for got, exp in route_cases if got == exp)
for got, exp in route_cases:
    if got != exp:
        print(f"  FAIL route: got {got!r} expected {exp!r}")
print(f"Routing:               {rp_pass}/{len(route_cases)} passed")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Feedback rating validation (pure logic)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_rating(r):
    return r in (1, -1)

fb_cases = [(1, True), (-1, True), (0, False), (2, False), (-2, False)]
fb_pass = sum(1 for r, expected in fb_cases if _validate_rating(r) == expected)
print(f"Feedback rating:       {fb_pass}/{len(fb_cases)} passed")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

total = rv_pass + cm_pass + hp_pass + rp_pass + fb_pass
total_cases = len(regex_cases) + len(marker_cases) + len(hum_cases) + len(route_cases) + len(fb_cases)
print(f"\nTotal: {total}/{total_cases} passed")
print("ALL SPRINT 7 LOGIC CHECKS PASSED" if total == total_cases else "SOME CHECKS FAILED")
