"""
Schema crawler — interrogates HANA and MSSQL information schemas and
populates metadata_tables, metadata_columns, metadata_relations.

Performance target: 10 000 tables < 10 min (DC-002).
Incremental mode: re-crawls only tables whose metadata_hash changed (DC-010).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.metadata import MetadataColumn, MetadataRelation, MetadataTable
from app.services.discovery.pii_detector import assess_column_pii

log = get_logger(__name__)

SAMPLE_ROW_LIMIT = 20  # DC-008: 20 sample rows per column
MAX_SAMPLE_VALUES = 10  # top-10 distinct non-PII values stored


@dataclass
class ColumnMeta:
    column_name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    char_max_length: int | None = None


@dataclass
class TableMeta:
    schema_name: str
    table_name: str
    object_type: str  # "table" | "view"
    columns: list[ColumnMeta] = field(default_factory=list)


@dataclass
class FKMeta:
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str


# ── HANA queries ─────────────────────────────────────────────────────────────

_HANA_TABLES_SQL = text("""
    SELECT schema_name, table_name, 'table' AS object_type
    FROM sys.tables
    WHERE is_system_table = 'FALSE'
      AND schema_name NOT IN ('SYS', 'PUBLIC', '_SYS_BIC', '_SYS_BI', '_SYS_REPO')
    UNION ALL
    SELECT schema_name, view_name AS table_name, 'view' AS object_type
    FROM sys.views
    WHERE schema_name NOT IN ('SYS', 'PUBLIC', '_SYS_BIC', '_SYS_BI', '_SYS_REPO')
""")

_HANA_COLUMNS_SQL = text("""
    SELECT c.column_name, c.data_type_name AS data_type,
           c.position AS ordinal_position,
           CASE WHEN c.is_nullable = 'TRUE' THEN 1 ELSE 0 END AS is_nullable,
           CASE WHEN c.is_primary_key = 'TRUE' THEN 1 ELSE 0 END AS is_primary_key,
           0 AS is_foreign_key, c.length AS char_max_length
    FROM sys.table_columns c
    WHERE c.schema_name = :schema AND c.table_name = :table
    ORDER BY c.position
""")

_HANA_FKS_SQL = text("""
    SELECT rc.schema_name AS from_schema, rc.table_name AS from_table,
           rc.column_name AS from_column,
           rc.referenced_schema_name AS to_schema,
           rc.referenced_table_name AS to_table,
           rc.referenced_column_name AS to_column
    FROM sys.referential_columns rc
    WHERE rc.schema_name NOT IN ('SYS', 'PUBLIC', '_SYS_BIC', '_SYS_BI', '_SYS_REPO')
""")

# ── MSSQL queries ─────────────────────────────────────────────────────────────

_MSSQL_TABLES_SQL = text("""
    SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name,
           CASE TABLE_TYPE WHEN 'VIEW' THEN 'view' ELSE 'table' END AS object_type
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
""")

_MSSQL_COLUMNS_SQL = text("""
    SELECT c.COLUMN_NAME AS column_name, c.DATA_TYPE AS data_type,
           c.ORDINAL_POSITION AS ordinal_position,
           CASE c.IS_NULLABLE WHEN 'YES' THEN 1 ELSE 0 END AS is_nullable,
           CASE WHEN kcu.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key,
           0 AS is_foreign_key,
           c.CHARACTER_MAXIMUM_LENGTH AS char_max_length
    FROM INFORMATION_SCHEMA.COLUMNS c
    LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
           ON kcu.TABLE_SCHEMA = c.TABLE_SCHEMA
          AND kcu.TABLE_NAME = c.TABLE_NAME
          AND kcu.COLUMN_NAME = c.COLUMN_NAME
          AND EXISTS (
              SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
              WHERE tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
          )
    WHERE c.TABLE_SCHEMA = :schema AND c.TABLE_NAME = :table
    ORDER BY c.ORDINAL_POSITION
""")

_MSSQL_FKS_SQL = text("""
    SELECT
        tp.TABLE_SCHEMA AS from_schema,
        tp.TABLE_NAME   AS from_table,
        kfk.COLUMN_NAME AS from_column,
        tr.TABLE_SCHEMA AS to_schema,
        tr.TABLE_NAME   AS to_table,
        kpk.COLUMN_NAME AS to_column
    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
         ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk
         ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
    JOIN INFORMATION_SCHEMA.TABLES tp
         ON tp.TABLE_NAME = fk.TABLE_NAME AND tp.TABLE_SCHEMA = fk.TABLE_SCHEMA
    JOIN INFORMATION_SCHEMA.TABLES tr
         ON tr.TABLE_NAME = pk.TABLE_NAME AND tr.TABLE_SCHEMA = pk.TABLE_SCHEMA
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kfk
         ON kfk.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kpk
         ON kpk.CONSTRAINT_NAME = pk.CONSTRAINT_NAME
        AND kpk.ORDINAL_POSITION = kfk.ORDINAL_POSITION
    WHERE fk.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
""")


def _compute_table_hash(table_meta: TableMeta) -> str:
    """SHA-256 fingerprint for incremental change detection (DC-010)."""
    payload = {
        "schema": table_meta.schema_name,
        "table": table_meta.table_name,
        "columns": [
            {
                "name": c.column_name,
                "type": c.data_type,
                "nullable": c.is_nullable,
                "pk": c.is_primary_key,
            }
            for c in table_meta.columns
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class SchemaCrawler:
    """
    Crawls HANA or MSSQL schema metadata using a raw async connection.

    Usage:
        async with engine.connect() as conn:
            crawler = SchemaCrawler(db=pg_session, src_conn=conn, db_type="mssql",
                                    tenant_id=tid, connection_id=cid)
            await crawler.run_full()
    """

    def __init__(
        self,
        db: AsyncSession,
        src_conn: Any,  # raw hdbcli or pyodbc connection (sync)
        db_type: str,   # "hana" | "mssql"
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> None:
        self.db = db
        self.src_conn = src_conn
        self.db_type = db_type
        self.tenant_id = tenant_id
        self.connection_id = connection_id

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_full(self) -> dict[str, int]:
        """Full discovery: crawl everything, upsert, return counts."""
        tables = await self._fetch_tables()
        log.info("discovery.full.start", table_count=len(tables),
                 connection_id=str(self.connection_id))

        fks = await self._fetch_fks()
        fk_index = self._build_fk_index(fks)

        upserted = 0
        for table in tables:
            table.columns = await self._fetch_columns(table.schema_name, table.table_name)
            await self._upsert_table(table, fk_index)
            upserted += 1

        await self._upsert_relations(fks)
        await self.db.commit()
        log.info("discovery.full.done", upserted=upserted,
                 connection_id=str(self.connection_id))
        return {"tables": upserted, "relations": len(fks)}

    async def run_incremental(self) -> dict[str, int]:
        """
        Incremental discovery: only crawl tables whose metadata_hash changed.
        """
        tables = await self._fetch_tables()
        existing = await self._load_existing_hashes()
        changed, skipped = 0, 0

        fks = await self._fetch_fks()
        fk_index = self._build_fk_index(fks)

        for table in tables:
            table.columns = await self._fetch_columns(table.schema_name, table.table_name)
            new_hash = _compute_table_hash(table)
            key = f"{table.schema_name}.{table.table_name}"
            if existing.get(key) == new_hash:
                skipped += 1
                continue
            await self._upsert_table(table, fk_index, override_hash=new_hash)
            changed += 1

        if changed:
            await self._upsert_relations(fks)
            await self.db.commit()

        log.info("discovery.incremental.done", changed=changed, skipped=skipped,
                 connection_id=str(self.connection_id))
        return {"changed": changed, "skipped": skipped}

    # ── Source DB fetch (sync wrappers run in threadpool via asyncio) ─────────

    async def _fetch_tables(self) -> list[TableMeta]:
        import asyncio
        sql = _HANA_TABLES_SQL if self.db_type == "hana" else _MSSQL_TABLES_SQL

        def _run() -> list[tuple]:
            cursor = self.src_conn.cursor()
            cursor.execute(str(sql))
            return cursor.fetchall()

        rows = await asyncio.get_event_loop().run_in_executor(None, _run)
        return [TableMeta(schema_name=r[0], table_name=r[1], object_type=r[2]) for r in rows]

    async def _fetch_columns(self, schema: str, table: str) -> list[ColumnMeta]:
        import asyncio
        sql = _HANA_COLUMNS_SQL if self.db_type == "hana" else _MSSQL_COLUMNS_SQL

        def _run() -> list[tuple]:
            cursor = self.src_conn.cursor()
            cursor.execute(str(sql), {"schema": schema, "table": table})
            return cursor.fetchall()

        rows = await asyncio.get_event_loop().run_in_executor(None, _run)
        return [
            ColumnMeta(
                column_name=r[0],
                data_type=r[1],
                ordinal_position=int(r[2]),
                is_nullable=bool(r[3]),
                is_primary_key=bool(r[4]),
                is_foreign_key=bool(r[5]),
                char_max_length=r[6] if len(r) > 6 else None,
            )
            for r in rows
        ]

    async def _fetch_fks(self) -> list[FKMeta]:
        import asyncio
        sql = _HANA_FKS_SQL if self.db_type == "hana" else _MSSQL_FKS_SQL

        def _run() -> list[tuple]:
            cursor = self.src_conn.cursor()
            cursor.execute(str(sql))
            return cursor.fetchall()

        rows = await asyncio.get_event_loop().run_in_executor(None, _run)
        return [
            FKMeta(
                from_schema=r[0], from_table=r[1], from_column=r[2],
                to_schema=r[3], to_table=r[4], to_column=r[5],
            )
            for r in rows
        ]

    async def _fetch_sample_values(
        self, schema: str, table: str, column: str
    ) -> list[str]:
        """Fetch up to SAMPLE_ROW_LIMIT distinct non-null values for PII/stats."""
        import asyncio

        quoted = (
            f'"{schema}"."{table}"'
            if self.db_type == "hana"
            else f"[{schema}].[{table}]"
        )

        def _run() -> list[tuple]:
            cursor = self.src_conn.cursor()
            if self.db_type == "hana":
                cursor.execute(
                    f'SELECT DISTINCT "{column}" FROM {quoted} '
                    f'WHERE "{column}" IS NOT NULL LIMIT {SAMPLE_ROW_LIMIT}'
                )
            else:
                cursor.execute(
                    f"SELECT DISTINCT TOP {SAMPLE_ROW_LIMIT} [{column}] "
                    f"FROM {quoted} WHERE [{column}] IS NOT NULL"
                )
            return cursor.fetchall()

        try:
            rows = await asyncio.get_event_loop().run_in_executor(None, _run)
            return [str(r[0]) for r in rows]
        except Exception:
            return []

    # ── PostgreSQL upserts ────────────────────────────────────────────────────

    async def _load_existing_hashes(self) -> dict[str, str]:
        """Return {schema.table → metadata_hash} for existing rows."""
        result = await self.db.execute(
            select(
                MetadataTable.schema_name,
                MetadataTable.table_name,
                MetadataTable.metadata_hash,
            ).where(
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.tenant_id == self.tenant_id,
            )
        )
        return {
            f"{r.schema_name}.{r.table_name}": r.metadata_hash
            for r in result.fetchall()
            if r.metadata_hash
        }

    async def _upsert_table(
        self,
        table: TableMeta,
        fk_index: set[tuple[str, str, str]],
        override_hash: str | None = None,
    ) -> None:
        hash_val = override_hash or _compute_table_hash(table)

        # Upsert MetadataTable
        existing_result = await self.db.execute(
            select(MetadataTable).where(
                MetadataTable.tenant_id == self.tenant_id,
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.schema_name == table.schema_name,
                MetadataTable.table_name == table.table_name,
            )
        )
        mt = existing_result.scalar_one_or_none()
        if mt is None:
            mt = MetadataTable(
                tenant_id=self.tenant_id,
                connection_id=self.connection_id,
                schema_name=table.schema_name,
                table_name=table.table_name,
                object_type=table.object_type,
                metadata_hash=hash_val,
            )
            self.db.add(mt)
            await self.db.flush()
        else:
            mt.metadata_hash = hash_val
            mt.object_type = table.object_type
            mt.discovery_version += 1
            await self.db.flush()

        # Upsert columns
        for col in table.columns:
            col_is_fk = (table.schema_name, table.table_name, col.column_name) in fk_index

            # Sample values + PII check
            samples = await self._fetch_sample_values(
                table.schema_name, table.table_name, col.column_name
            )
            is_pii = assess_column_pii(col.column_name, samples)
            safe_samples = [] if is_pii else samples[:MAX_SAMPLE_VALUES]

            existing_col = await self.db.execute(
                select(MetadataColumn).where(
                    MetadataColumn.table_id == mt.id,
                    MetadataColumn.column_name == col.column_name,
                )
            )
            mc = existing_col.scalar_one_or_none()
            if mc is None:
                mc = MetadataColumn(
                    tenant_id=self.tenant_id,
                    table_id=mt.id,
                    column_name=col.column_name,
                    data_type=col.data_type,
                    is_nullable=col.is_nullable,
                    is_primary_key=col.is_primary_key,
                    is_foreign_key=col_is_fk,
                    is_pii_flagged=is_pii,
                    ordinal_position=col.ordinal_position,
                    sample_values={"values": safe_samples} if safe_samples else None,
                )
                self.db.add(mc)
            else:
                mc.data_type = col.data_type
                mc.is_nullable = col.is_nullable
                mc.is_primary_key = col.is_primary_key
                mc.is_foreign_key = col_is_fk
                mc.is_pii_flagged = is_pii
                if not is_pii:
                    mc.sample_values = {"values": safe_samples} if safe_samples else None

    async def _upsert_relations(self, fks: list[FKMeta]) -> None:
        for fk in fks:
            # Resolve table IDs
            from_t = await self._get_table_id(fk.from_schema, fk.from_table)
            to_t = await self._get_table_id(fk.to_schema, fk.to_table)
            if not from_t or not to_t:
                continue

            from_c = await self._get_column_id(from_t, fk.from_column)
            to_c = await self._get_column_id(to_t, fk.to_column)
            if not from_c or not to_c:
                continue

            exists = await self.db.execute(
                select(MetadataRelation).where(
                    MetadataRelation.from_table_id == from_t,
                    MetadataRelation.from_column_id == from_c,
                    MetadataRelation.to_table_id == to_t,
                    MetadataRelation.to_column_id == to_c,
                )
            )
            if exists.scalar_one_or_none() is None:
                self.db.add(MetadataRelation(
                    tenant_id=self.tenant_id,
                    from_table_id=from_t,
                    from_column_id=from_c,
                    to_table_id=to_t,
                    to_column_id=to_c,
                    relation_type="explicit_fk",
                    confidence=1.0,
                    is_admin_confirmed=True,
                ))

    async def _get_table_id(self, schema: str, table: str) -> uuid.UUID | None:
        result = await self.db.execute(
            select(MetadataTable.id).where(
                MetadataTable.connection_id == self.connection_id,
                MetadataTable.schema_name == schema,
                MetadataTable.table_name == table,
            )
        )
        row = result.scalar_one_or_none()
        return row

    async def _get_column_id(self, table_id: uuid.UUID, column: str) -> uuid.UUID | None:
        result = await self.db.execute(
            select(MetadataColumn.id).where(
                MetadataColumn.table_id == table_id,
                MetadataColumn.column_name == column,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _build_fk_index(fks: list[FKMeta]) -> set[tuple[str, str, str]]:
        """Build (schema, table, column) set for fast FK lookup during column upsert."""
        return {(f.from_schema, f.from_table, f.from_column) for f in fks}
