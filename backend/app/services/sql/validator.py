"""
SQL Validator — AST-based safety checks via sqlglot.

Spec: SV-001, SV-002, SV-003, SV-004
  - SV-001: DML hard-block — INSERT/UPDATE/DELETE/MERGE/TRUNCATE/DROP/ALTER/CREATE
  - SV-002: Only a single statement per call (no statement chaining)
  - SV-003: No INFORMATION_SCHEMA / system catalogue access
  - SV-004: Column star (*) allowed but warns for large tables
  - SV-005: Subqueries allowed; CTEs allowed (SELECT-only CTEs)

Why sqlglot vs regex:
  - Regex can miss obfuscated DML inside CTEs or subqueries
  - sqlglot parses the full AST so nested DML in a CTE is caught
  - Dialect-aware: handles both T-SQL (MSSQL) and SAP HANA SQL

Strategy:
  1. Parse with sqlglot (lenient=True so partial SQL doesn't crash)
  2. Walk AST for forbidden node types
  3. Walk AST for forbidden table references (INFORMATION_SCHEMA)
  4. Ensure exactly one statement, and it is a SELECT / CTE-SELECT

Usage:
    result = validate_sql(sql, dialect="tsql")
    if not result.is_valid:
        raise ValueError(result.error)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

try:
    import sqlglot
    import sqlglot.expressions as exp
    _SQLGLOT_AVAILABLE = True
except ImportError:
    _SQLGLOT_AVAILABLE = False

import re

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_valid: bool
    error: str | None = None
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

# ── Forbidden AST node types ──────────────────────────────────────────────────

_FORBIDDEN_TYPES: tuple[type, ...] = ()  # populated after import check

_FORBIDDEN_TABLE_PATTERNS = re.compile(
    r"\b(INFORMATION_SCHEMA|SYS\.TABLES|SYS\.COLUMNS|SYS\.OBJECTS"
    r"|SYSOBJECTS|SYSCOLUMNS|MASTER\.\.|MSDB\.\.|MODEL\.\.)\b",
    re.IGNORECASE,
)

# Fallback DML regex when sqlglot unavailable (same as Sprint 6)
_DML_FALLBACK = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)

Dialect = Literal["tsql", "hana", "ansi"]


def validate_sql(
    sql: str,
    dialect: Dialect = "tsql",
) -> ValidationResult:
    """
    Validate SQL using sqlglot AST parsing.
    Falls back to regex-based validation if sqlglot is not installed.
    """
    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, error="SQL is empty")

    if not _SQLGLOT_AVAILABLE:
        return _regex_fallback(sql)

    return _ast_validate(sql, dialect)


def _ast_validate(sql: str, dialect: Dialect) -> ValidationResult:
    """Full AST-based validation."""
    # Map our dialect names to sqlglot dialect names
    dialect_map = {"tsql": "tsql", "hana": "hana", "ansi": None}
    sg_dialect = dialect_map.get(dialect)

    try:
        statements = sqlglot.parse(sql, dialect=sg_dialect, error_level=sqlglot.ErrorLevel.WARN)
    except Exception as exc:
        # Parse failure — fall back to regex
        return _regex_fallback(sql)

    if not statements:
        return ValidationResult(is_valid=False, error="Could not parse SQL statement")

    # SV-002: exactly one statement
    real_stmts = [s for s in statements if s is not None]
    if len(real_stmts) > 1:
        return ValidationResult(
            is_valid=False,
            error=f"Only a single SQL statement is allowed; got {len(real_stmts)}"
        )

    tree = real_stmts[0]

    # SV-001: top-level must be SELECT or a CTE (With) whose final body is SELECT
    if not _is_select_statement(tree):
        kind = type(tree).__name__
        return ValidationResult(
            is_valid=False,
            error=f"Only SELECT statements are allowed (got {kind})"
        )

    # SV-001: walk AST for any DML/DDL nodes even inside CTEs or subqueries
    dml_node = _find_dml_node(tree)
    if dml_node:
        return ValidationResult(
            is_valid=False,
            error=f"DML/DDL is forbidden inside queries (found {type(dml_node).__name__})"
        )

    # SV-003: no system catalogue references
    system_ref = _find_system_table(tree)
    if system_ref:
        return ValidationResult(
            is_valid=False,
            error=f"System catalogue access is not permitted: {system_ref}"
        )

    warnings: list[str] = []
    # SV-004: star select warning
    if _has_star_select(tree):
        warnings.append("SELECT * detected — consider specifying columns for performance")

    return ValidationResult(is_valid=True, warnings=warnings)


def _is_select_statement(tree: "exp.Expression") -> bool:
    """Return True if the statement is ultimately a SELECT."""
    if isinstance(tree, exp.Select):
        return True
    # CTE: With node wrapping a Select
    if isinstance(tree, exp.With):
        return isinstance(tree.args.get("expression"), exp.Select)
    return False


def _find_dml_node(tree: "exp.Expression") -> "exp.Expression | None":
    """Walk AST and return first DML/DDL node found, or None."""
    dml_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Merge,
        exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
        exp.Command,  # catches EXEC / raw commands
    )
    for node in tree.walk():
        if isinstance(node, dml_types) and node is not tree:
            return node
    return None


def _find_system_table(tree: "exp.Expression") -> str | None:
    """Return first system-catalogue table name found, or None."""
    for node in tree.walk():
        if isinstance(node, exp.Table):
            name = node.name or ""
            db = (node.args.get("db") or {})
            db_name = db.name if hasattr(db, "name") else str(db)
            full = f"{db_name}.{name}".upper() if db_name else name.upper()
            if _FORBIDDEN_TABLE_PATTERNS.search(full):
                return full
    return None


def _has_star_select(tree: "exp.Expression") -> bool:
    for node in tree.walk():
        if isinstance(node, exp.Star):
            return True
    return False


def _regex_fallback(sql: str) -> ValidationResult:
    """Regex-based fallback when sqlglot is not installed."""
    match = _DML_FALLBACK.search(sql)
    if match:
        return ValidationResult(
            is_valid=False,
            error=f"Statement contains forbidden keyword '{match.group().upper()}' (regex check)"
        )
    stripped = re.sub(r"--[^\n]*\n", "", sql).strip().upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
        return ValidationResult(
            is_valid=False,
            error="Only SELECT/WITH queries are allowed (regex check)"
        )
    sys_match = _FORBIDDEN_TABLE_PATTERNS.search(sql)
    if sys_match:
        return ValidationResult(
            is_valid=False,
            error=f"System catalogue access is not permitted: {sys_match.group()}"
        )
    return ValidationResult(is_valid=True)
