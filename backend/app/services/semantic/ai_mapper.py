"""
AI entity/attribute mapper — Claude-driven mapping for tables not in any pack.

Sends table+column context to Claude, receives structured entity/attribute
suggestions with confidence scores. Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.metadata import MetadataColumn, MetadataTable
from app.models.semantic import SemanticAttribute, SemanticEntity

log = get_logger(__name__)
settings = get_settings()

VALID_DOMAINS = ["finance", "sales", "purchasing", "inventory", "operations"]
VALID_SEMANTIC_TYPES = ["currency", "date", "quantity", "code", "text",
                         "boolean", "percentage", "id", "datetime"]

_SYSTEM_PROMPT = """\
You are a business data analyst specialising in ERP systems.
Given a database table name, its columns, data types, and sample values,
produce a JSON object that maps the table to a business entity.

Respond ONLY with valid JSON matching this schema:
{
  "entity_name": "<human-readable business name>",
  "domain": "<finance|sales|purchasing|inventory|operations>",
  "description": "<1-2 sentence description of what this table represents>",
  "confidence": <0.0-1.0 float>,
  "attributes": {
    "<column_name>": {
      "display_name": "<human-readable label>",
      "semantic_type": "<currency|date|quantity|code|text|boolean|percentage|id|datetime>",
      "description": "<optional short description>"
    }
  }
}

Rules:
- Only include attributes for columns you are confident about.
- Use "code" for status/type columns with short enumerated values.
- Use "id" for foreign keys and primary keys.
- If you are not sure about the entity, set confidence below 0.5.
- Do not include PII-marked columns in attribute descriptions.
"""


class AIEntityMapper:
    """Uses Claude to suggest semantic entity/attribute mappings for unknown tables."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def map_unmapped_tables(
        self, connection_id: uuid.UUID, limit: int = 50
    ) -> dict[str, int]:
        """
        Find tables without a SemanticEntity and generate AI mappings.
        Skips system/PII-flagged tables.
        Returns {mapped, skipped, errors}.
        """
        # Tables without an entity mapping
        mapped_table_ids_result = await self.db.execute(
            select(SemanticEntity.table_id).where(
                SemanticEntity.tenant_id == self.tenant_id
            )
        )
        already_mapped = {r[0] for r in mapped_table_ids_result.fetchall()}

        tables_result = await self.db.execute(
            select(MetadataTable).where(
                MetadataTable.tenant_id == self.tenant_id,
                MetadataTable.connection_id == connection_id,
                MetadataTable.is_system_table.is_(False),
                MetadataTable.is_pii_flagged.is_(False),
            ).limit(limit * 2)  # fetch extra, filter in-loop
        )
        tables = [t for t in tables_result.scalars().all()
                  if t.id not in already_mapped][:limit]

        mapped, skipped, errors = 0, 0, 0
        for table in tables:
            try:
                success = await self._map_table(table)
                if success:
                    mapped += 1
                else:
                    skipped += 1
            except Exception as exc:
                log.warning("ai_mapper.table.error", table=table.table_name, error=str(exc))
                errors += 1

        await self.db.flush()
        log.info("ai_mapper.done", mapped=mapped, skipped=skipped, errors=errors)
        return {"mapped": mapped, "skipped": skipped, "errors": errors}

    async def _map_table(self, table: MetadataTable) -> bool:
        cols_result = await self.db.execute(
            select(MetadataColumn)
            .where(MetadataColumn.table_id == table.id)
            .order_by(MetadataColumn.ordinal_position)
            .limit(30)
        )
        columns = cols_result.scalars().all()
        if not columns:
            return False

        # Build compact context for Claude
        col_context = []
        for c in columns:
            entry: dict = {
                "name": c.column_name,
                "type": c.data_type,
                "nullable": c.is_nullable,
                "pk": c.is_primary_key,
                "fk": c.is_foreign_key,
            }
            if c.sample_values and not c.is_pii_flagged:
                samples = c.sample_values.get("values", [])[:5]
                if samples:
                    entry["samples"] = samples
            col_context.append(entry)

        user_message = (
            f"Table: {table.schema_name}.{table.table_name}\n"
            f"Columns:\n{json.dumps(col_context, indent=2)}"
        )

        result = await self._call_claude(user_message)
        if not result:
            return False

        confidence: float = float(result.get("confidence", 0.0))
        if confidence < 0.3:
            log.info("ai_mapper.low_confidence", table=table.table_name,
                     confidence=confidence)
            return False

        # Persist entity
        entity = SemanticEntity(
            tenant_id=self.tenant_id,
            table_id=table.id,
            entity_name=result.get("entity_name", table.table_name),
            domain=self._validated_domain(result.get("domain", "operations")),
            description=result.get("description"),
            is_ai_generated=True,
            is_human_override=False,
            confidence=confidence,
            pack_source="ai_generated",
        )
        self.db.add(entity)
        await self.db.flush()

        # Persist attributes
        attr_map: dict = result.get("attributes", {})
        for col in columns:
            attr_def = attr_map.get(col.column_name)
            if not attr_def:
                continue
            self.db.add(SemanticAttribute(
                tenant_id=self.tenant_id,
                entity_id=entity.id,
                column_id=col.id,
                attribute_name=col.column_name,
                display_name=attr_def.get("display_name", col.column_name),
                semantic_type=self._validated_semantic_type(
                    attr_def.get("semantic_type", "text")
                ),
                description=attr_def.get("description"),
                is_human_override=False,
                is_ai_generated=True,
            ))

        return True

    async def _call_claude(self, user_message: str) -> dict | None:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            message = await client.messages.create(
                model=settings.anthropic_fast_model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = "".join(block.text for block in message.content if block.type == "text").strip()
            # Strip markdown code fence if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as exc:
            log.warning("ai_mapper.claude_error", error=str(exc))
            return None

    @staticmethod
    def _validated_domain(domain: str) -> str:
        return domain if domain in VALID_DOMAINS else "operations"

    @staticmethod
    def _validated_semantic_type(stype: str) -> str:
        return stype if stype in VALID_SEMANTIC_TYPES else "text"
