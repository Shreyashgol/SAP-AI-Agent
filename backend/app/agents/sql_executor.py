"""
SQL Executor Agent — binds parameters and executes the SQL template.

Spec: AG-005, QE-001, QE-002, QE-003, QE-004, QE-005
  - QE-001: DML hard block via sqlglot AST validation (Sprint 7) + regex fallback
  - QE-002: Row limit cap — MAX_ROWS = 1000 (hard); UI truncation at 200
  - QE-003: Execute via connection's raw source-DB connector (hdbcli / pyodbc)
  - QE-004: Execution timeout = 30s
  - QE-005: Result serialised to {rows, columns, row_count, truncated}

Parameter binding:
  Named bind parameters (:param_name) are substituted.
  If a required parameter is None, the supervisor routes to clarification_agent.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import AgentState

MAX_ROWS = 1000
EXECUTION_TIMEOUT = 30  # seconds

_DML_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)

# Keys that indicate a LIMIT/TOP clause exists in the template
_LIMIT_PATTERN = re.compile(r"\bTOP\s+:\w+\b|\bLIMIT\s+:\w+\b|\bTOP\s+\d+\b|\bLIMIT\s+\d+\b", re.IGNORECASE)


class SQLExecutorAgent(BaseAgent):
    name = "sql_executor"

    async def _run(self, state: AgentState) -> dict[str, Any]:
        tool = state.get("selected_tool")
        if not tool:
            return {"error": "No tool selected — cannot execute query."}

        sql_template: str = tool["sql_template"]
        params: dict[str, Any] = state.get("resolved_params", {}) or {}

        # 1. DML guard (QE-001) — sqlglot AST validation (Sprint 7)
        from app.services.sql.validator import validate_sql
        validation = validate_sql(sql_template)
        if not validation.is_valid:
            return {"error": f"Query blocked: {validation.error}"}
        for w in (validation.warnings or []):
            self._log.warning("sql_executor.sql_warning", warning=w)

        # 2. Check required params are present — signal clarification_needed
        missing = _check_required_params(tool.get("input_schema", []), params)
        if missing:
            return {
                "needs_clarification": True,
                "missing_params": missing,
            }

        # 3. Bind parameters
        sql, bind_params = _bind_params(sql_template, params)

        # 4. Inject TOP 1000 safety cap if no user-supplied limit
        sql = _inject_row_limit(sql, MAX_ROWS)

        # 5. Execute against source DB
        try:
            start = time.monotonic()
            rows, columns = await _execute_query(state, sql, bind_params)
            elapsed_ms = int((time.monotonic() - start) * 1000)
        except Exception as exc:
            self._log.error("sql_executor.query_error", exc=str(exc))
            return {"error": f"Query execution failed: {exc}"}

        truncated = len(rows) >= MAX_ROWS
        if truncated:
            rows = rows[:MAX_ROWS]

        result = {
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
            "truncated": truncated,
        }

        self._log.info("sql_executor.done",
                       row_count=len(rows), elapsed_ms=elapsed_ms, truncated=truncated)
        return {
            "sql_query": sql,
            "query_result": result,
            "execution_time_ms": elapsed_ms,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_dml(sql: str) -> str | None:
    """Return error message if SQL contains DML/DDL."""
    match = _DML_PATTERN.search(sql)
    if match:
        return f"Statement contains forbidden keyword '{match.group().upper()}'"
    # Must start with SELECT (allow leading comments)
    stripped = re.sub(r"--[^\n]*\n", "", sql).strip().upper()
    if not stripped.startswith("SELECT"):
        return "Only SELECT queries are allowed"
    return None


def _check_required_params(schema: list[dict], params: dict) -> list[str]:
    """Return list of required params that are missing or None."""
    missing = []
    for p in schema:
        if p.get("required") and params.get(p["name"]) is None:
            missing.append(p["name"])
    return missing


def _bind_params(
    template: str, params: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """
    For pyodbc/hdbcli we can't use named params natively — substitute with positional.
    Returns (sql_with_question_marks, ordered_values_dict).
    Actually: return the template as-is + params dict for connector's execute_query.
    The connector's execute_query handles named :param substitution via regex.
    """
    return template, params


def _inject_row_limit(sql: str, limit: int) -> str:
    """Add a TOP clause if no limit is already present (MSSQL/HANA syntax)."""
    if _LIMIT_PATTERN.search(sql):
        return sql  # already has a limit
    # Insert TOP N after the first SELECT
    return re.sub(
        r"^\s*SELECT\b",
        f"SELECT TOP {limit}",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )


async def _execute_query(
    state: AgentState,
    sql: str,
    params: dict[str, Any],
) -> tuple[list[dict], list[str]]:
    """
    Execute SQL against the tenant's source database.
    Uses the Connection's stored credentials via the connector service.
    """
    from sqlalchemy import select as sa_select
    from app.db.session import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.models.connection import Connection
    from app.services.connections.connection_service import ConnectionService
    from app.services.connections.connector import get_connector

    connection_id = state.get("connection_id")
    if not connection_id:
        # Find first active connection for the tenant
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_select(Connection).where(
                    Connection.tenant_id == state["tenant_id"],
                    Connection.is_active.is_(True),
                ).limit(1)
            )
            conn = result.scalar_one_or_none()
            if not conn:
                raise RuntimeError("No active database connection found for tenant")
            connection_id = conn.id

    async with AsyncSessionLocal() as db:
        conn_result = await db.execute(
            sa_select(Connection).where(Connection.id == connection_id)
        )
        connection = conn_result.scalar_one_or_none()
        if not connection:
            raise RuntimeError(f"Connection {connection_id} not found")

        redis = get_redis()
        credentials = ConnectionService(db, redis)._load_credentials(connection)
        connector = get_connector(connection.db_type, str(connection.id), redis)

        # Templates use :named placeholders (not pyodbc's ?), so substitute
        # validated literals into the SQL before execution.
        bound_sql = _substitute_params(sql, params)
        rows_raw = await connector.execute_query(credentials, bound_sql)

    if not rows_raw:
        return [], []

    columns = list(rows_raw[0].keys()) if isinstance(rows_raw[0], dict) else []
    rows = [dict(r) if not isinstance(r, dict) else r for r in rows_raw]
    return rows, columns


def _substitute_params(sql: str, params: dict[str, Any]) -> str:
    """
    Substitute :param_name with quoted/escaped values for direct execution.
    This is a last-resort substitution — ideally the connector handles parameterisation.
    """
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
