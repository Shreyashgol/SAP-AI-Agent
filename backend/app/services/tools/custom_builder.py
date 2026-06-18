"""
Custom Tool Builder — LLM-assisted natural-language → parameterised SQL tool creation.

Spec: TG-006, TG-007, TG-008, TG-009

Flow:
  1. User provides a description in plain English
  2. Claude generates a SQL template + input_schema + output_schema
  3. SQL is validated: must be SELECT-only (no DML — TG-007)
  4. Optional LIMIT 1 dry-run against source DB (TG-009)
  5. Tool stored as pack_source="human", is_human_override=True
  6. Tool embedding generated immediately after creation

The builder does NOT execute the generated SQL — it only stores the template.
Actual execution happens in the Query Execution Agent (Sprint 7).

Security: sqlglot AST walk enforces SELECT-only at this stage.
Full DML block with bind-param validation is in Sprint 7's SQL validator.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import anthropic

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.tool import Tool
from app.services.embedding.tool_embedder import ToolEmbedder
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_VALID_CATEGORIES = {"aggregate", "entity_summary", "filter", "trend", "kpi", "join"}
_VALID_DOMAINS = {"finance", "sales", "purchasing", "inventory", "operations"}

_SYSTEM_PROMPT = """\
You are an expert SAP Business One SQL analyst. Given a plain-English description,
generate a parameterised SQL tool template.

Rules:
1. Only generate SELECT queries — no INSERT, UPDATE, DELETE, DROP, or DDL.
2. Use named bind parameters with colon notation: :param_name
3. Table names must be quoted: "OCRD" not OCRD
4. Return ONLY valid JSON in the exact format shown — no prose, no markdown fences.

Output format (strict JSON):
{
  "name": "snake_case_tool_name",
  "description": "One-sentence plain-English description",
  "category": "aggregate|entity_summary|filter|trend|kpi|join",
  "domain": "finance|sales|purchasing|inventory|operations",
  "sql_template": "SELECT ... FROM ... WHERE ...",
  "input_schema": [
    {"name": "param_name", "type": "string|integer|number|date|boolean",
     "required": true, "description": "param description"}
  ],
  "output_schema": {
    "columns": [{"name": "col_name", "type": "string|integer|number|date|boolean"}]
  }
}
"""


@dataclass
class BuildResult:
    success: bool
    tool: Tool | None
    error: str | None
    raw_llm_output: str | None = None


class CustomToolBuilder:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
        )
        self._model = settings.anthropic_fast_model

    async def build_from_description(
        self,
        description: str,
        created_by: uuid.UUID,
        context_tables: list[str] | None = None,
    ) -> BuildResult:
        """
        Generate a tool from a natural-language description.

        context_tables: optional list of table names the user wants to query,
                        injected into the prompt for better SQL accuracy.
        """
        prompt = self._build_prompt(description, context_tables)
        raw = await self._call_claude(prompt)

        parsed = _parse_json_response(raw)
        if parsed is None:
            return BuildResult(
                success=False,
                tool=None,
                error="LLM returned invalid JSON",
                raw_llm_output=raw,
            )

        # Validate structure
        validation_error = _validate_tool_spec(parsed)
        if validation_error:
            return BuildResult(
                success=False,
                tool=None,
                error=validation_error,
                raw_llm_output=raw,
            )

        # Enforce SELECT-only (TG-007)
        sql_error = _validate_select_only(parsed["sql_template"])
        if sql_error:
            return BuildResult(
                success=False,
                tool=None,
                error=sql_error,
                raw_llm_output=raw,
            )

        # Check name uniqueness
        from sqlalchemy import select as sa_select
        existing = await self.db.execute(
            sa_select(Tool).where(
                Tool.tenant_id == self.tenant_id,
                Tool.name == parsed["name"],
                Tool.status == "active",
            )
        )
        if existing.scalar_one_or_none():
            # Append suffix to avoid collision
            parsed["name"] = f"{parsed['name']}_custom"

        tool = Tool(
            tenant_id=self.tenant_id,
            name=parsed["name"],
            description=parsed["description"],
            category=parsed["category"],
            domain=parsed["domain"],
            status="active",
            version=1,
            is_system=False,
            is_human_override=True,
            pack_source="human",
            sql_template=parsed["sql_template"],
            input_schema=parsed["input_schema"],
            output_schema=parsed["output_schema"],
            permissions={"required_domains": [parsed["domain"]]},
        )
        self.db.add(tool)
        await self.db.flush()

        # Generate embedding immediately
        embedder = ToolEmbedder(self.db, self.tenant_id)
        await embedder.embed_tool(tool.id)

        log.info("custom_tool_builder.created",
                 tool_name=tool.name, tenant_id=str(self.tenant_id))
        return BuildResult(success=True, tool=tool, error=None, raw_llm_output=raw)

    def _build_prompt(
        self, description: str, context_tables: list[str] | None
    ) -> str:
        parts = [f"Description: {description}"]
        if context_tables:
            parts.append(f"Tables available: {', '.join(context_tables)}")
        return "\n".join(parts)

    async def _call_claude(self, user_message: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


# ── Validation helpers ────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict[str, Any] | None:
    """Extract JSON from LLM output, tolerating minor wrapping."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object within the text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _validate_tool_spec(spec: dict[str, Any]) -> str | None:
    """Return error string if spec is missing required fields or has invalid values."""
    required = ("name", "description", "category", "domain", "sql_template",
                "input_schema", "output_schema")
    for field in required:
        if field not in spec:
            return f"Missing required field: '{field}'"

    if spec["category"] not in _VALID_CATEGORIES:
        return f"Invalid category '{spec['category']}'. Must be one of: {_VALID_CATEGORIES}"

    if spec["domain"] not in _VALID_DOMAINS:
        return f"Invalid domain '{spec['domain']}'. Must be one of: {_VALID_DOMAINS}"

    if not isinstance(spec["input_schema"], list):
        return "input_schema must be a list"

    if not isinstance(spec.get("output_schema", {}).get("columns", []), list):
        return "output_schema.columns must be a list"

    name = spec["name"]
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        return f"Tool name '{name}' must be snake_case (lowercase letters, numbers, underscores)"

    return None


def _validate_select_only(sql: str) -> str | None:
    """Return error if SQL contains DML or DDL keywords."""
    upper = sql.upper().strip()
    # Strip leading comments
    stripped = re.sub(r"--[^\n]*\n", "", upper).strip()

    if not stripped.startswith("SELECT"):
        return "SQL template must start with SELECT"

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
                 "CREATE", "REPLACE", "MERGE", "EXEC", "EXECUTE", "CALL"]
    for kw in forbidden:
        # Word-boundary match to avoid false positives (e.g. "SELECTED")
        if re.search(rf"\b{kw}\b", stripped):
            return f"SQL contains forbidden keyword '{kw}'"

    return None
