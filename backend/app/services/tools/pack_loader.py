"""
Tool Pack Loader — seeds SAP B1 tool templates as Tool records for a tenant.

Spec: TG-003, TG-004
- Loads SAP_B1_TOOLS list into the Tool table
- Respects human overrides (is_human_override=True tools are never overwritten)
- Versions tools whose sql_template changes
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tool import Tool
from app.services.tools.sap_b1_tools import SAP_B1_TOOLS

log = get_logger(__name__)


class ToolPackLoader:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def apply(self, pack_source: str = "sap_b1") -> dict[str, int]:
        """Upsert all tools from the SAP B1 pack. Returns {inserted, updated, skipped}."""
        inserted = updated = skipped = 0

        for entry in SAP_B1_TOOLS:
            existing_result = await self.db.execute(
                select(Tool).where(
                    Tool.tenant_id == self.tenant_id,
                    Tool.name == entry["name"],
                ).order_by(Tool.version.desc()).limit(1)
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                if existing.is_human_override:
                    skipped += 1
                    continue
                if existing.sql_template == entry["sql_template"]:
                    skipped += 1
                    continue
                # Template changed — deprecate old, insert new version
                existing.status = "deprecated"
                version = existing.version + 1
                updated += 1
            else:
                version = 1
                inserted += 1

            tool = Tool(
                tenant_id=self.tenant_id,
                name=entry["name"],
                description=entry["description"],
                category=entry["category"],
                domain=entry["domain"],
                status="active",
                version=version,
                is_system=True,
                is_human_override=False,
                pack_source=pack_source,
                sql_template=entry["sql_template"],
                input_schema=entry["input_schema"],
                output_schema=entry["output_schema"],
                permissions={"required_domains": [entry["domain"]]},
            )
            self.db.add(tool)

        await self.db.flush()
        log.info("tool_pack.apply.done",
                 pack_source=pack_source, inserted=inserted,
                 updated=updated, skipped=skipped)
        return {"inserted": inserted, "updated": updated, "skipped": skipped}
