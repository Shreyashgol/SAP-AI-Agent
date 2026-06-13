"""
Entity pack loader — applies SAP B1 (or MSSQL) pack data to the semantic layer.

Upserts SemanticEntity, SemanticAttribute, and BusinessRule records.
Human overrides (is_human_override=True) are never overwritten (SL-009).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.metadata import MetadataColumn, MetadataTable
from app.models.semantic import BusinessRule, SemanticAttribute, SemanticEntity
from app.services.semantic.sap_b1_pack import EntityPackEntry, get_entry, get_pack_tables

log = get_logger(__name__)


class PackLoader:
    """Loads an entity pack into the semantic layer for a specific connection."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        pack_source: str = "sap_b1",
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.connection_id = connection_id
        self.pack_source = pack_source

    async def apply(self, schema_name: str | None = None) -> dict[str, int]:
        """
        Apply pack entries for all crawled tables that match pack table names.
        If schema_name is provided, only tables in that schema are processed.
        Returns counts: {entities, attributes, rules}.
        """
        covered = get_pack_tables()
        entities_upserted = 0
        attributes_upserted = 0
        rules_upserted = 0

        for table_name in covered:
            entry = get_entry(table_name)
            if not entry:
                continue

            # Find the crawled MetadataTable record for this table
            q = select(MetadataTable).where(
                MetadataTable.tenant_id == self.tenant_id,
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.table_name == table_name,
            )
            if schema_name:
                q = q.where(MetadataTable.schema_name == schema_name)

            result = await self.db.execute(q)
            mt = result.scalar_one_or_none()
            if not mt:
                continue  # Table not yet crawled — skip

            entity = await self._upsert_entity(mt, entry)
            entities_upserted += 1

            attr_count = await self._upsert_attributes(entity, mt.id, entry)
            attributes_upserted += attr_count

            rule_count = await self._upsert_rules(entity, entry)
            rules_upserted += rule_count

        await self.db.flush()
        log.info(
            "pack_loader.apply.done",
            pack_source=self.pack_source,
            entities=entities_upserted,
            attributes=attributes_upserted,
            rules=rules_upserted,
        )
        return {
            "entities": entities_upserted,
            "attributes": attributes_upserted,
            "rules": rules_upserted,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _upsert_entity(
        self, table: MetadataTable, entry: EntityPackEntry
    ) -> SemanticEntity:
        result = await self.db.execute(
            select(SemanticEntity).where(
                SemanticEntity.tenant_id == self.tenant_id,
                SemanticEntity.table_id == table.id,
            )
        )
        entity = result.scalar_one_or_none()

        if entity is None:
            entity = SemanticEntity(
                tenant_id=self.tenant_id,
                table_id=table.id,
                entity_name=entry.get("entity_name", table.table_name),
                domain=entry.get("domain", "operations"),
                description=entry.get("description"),
                is_ai_generated=False,
                is_human_override=False,
                confidence=1.0,
                pack_source=self.pack_source,
            )
            self.db.add(entity)
            await self.db.flush()
        elif not entity.is_human_override:
            # Only update if no human override exists
            entity.entity_name = entry.get("entity_name", entity.entity_name)
            entity.domain = entry.get("domain", entity.domain)
            entity.description = entry.get("description", entity.description)
            entity.pack_source = self.pack_source
            entity.semantic_version += 1

        return entity

    async def _upsert_attributes(
        self,
        entity: SemanticEntity,
        table_id: uuid.UUID,
        entry: EntityPackEntry,
    ) -> int:
        attr_map = entry.get("attributes", {})
        count = 0

        for col_name, attr_def in attr_map.items():
            # Find MetadataColumn
            col_result = await self.db.execute(
                select(MetadataColumn).where(
                    MetadataColumn.table_id == table_id,
                    MetadataColumn.column_name == col_name,
                )
            )
            mc = col_result.scalar_one_or_none()
            if not mc:
                continue  # Column not in crawled schema — skip

            # Find or create SemanticAttribute
            attr_result = await self.db.execute(
                select(SemanticAttribute).where(
                    SemanticAttribute.entity_id == entity.id,
                    SemanticAttribute.column_id == mc.id,
                )
            )
            sa = attr_result.scalar_one_or_none()

            if sa is None:
                sa = SemanticAttribute(
                    tenant_id=self.tenant_id,
                    entity_id=entity.id,
                    column_id=mc.id,
                    attribute_name=col_name,
                    display_name=attr_def.get("display_name", col_name),
                    semantic_type=attr_def.get("semantic_type", "text"),
                    description=attr_def.get("description"),
                    is_human_override=False,
                    is_ai_generated=False,
                )
                self.db.add(sa)
                count += 1
            elif not sa.is_human_override:
                sa.display_name = attr_def.get("display_name", sa.display_name)
                sa.semantic_type = attr_def.get("semantic_type", sa.semantic_type)
                sa.description = attr_def.get("description", sa.description)
                count += 1

        return count

    async def _upsert_rules(
        self, entity: SemanticEntity, entry: EntityPackEntry
    ) -> int:
        rules = entry.get("rules", [])
        count = 0

        for rule_def in rules:
            rule_result = await self.db.execute(
                select(BusinessRule).where(
                    BusinessRule.entity_id == entity.id,
                    BusinessRule.rule_name == rule_def["rule_name"],
                )
            )
            br = rule_result.scalar_one_or_none()

            if br is None:
                self.db.add(BusinessRule(
                    tenant_id=self.tenant_id,
                    entity_id=entity.id,
                    rule_name=rule_def["rule_name"],
                    predicate_sql=rule_def["predicate_sql"],
                    description=rule_def.get("description"),
                    is_default=rule_def.get("is_default", False),
                    is_system=True,
                    pack_source=self.pack_source,
                ))
                count += 1
            else:
                # Never override human-customised rules
                if br.pack_source != "human":
                    br.predicate_sql = rule_def["predicate_sql"]
                    br.description = rule_def.get("description", br.description)
                    count += 1

        return count
