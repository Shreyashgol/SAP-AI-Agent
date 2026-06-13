import { useState } from "react";
import {
  CatalogTable,
  CatalogTableDetail,
  useCatalogTable,
  useCatalogTables,
  usePatchCatalogTable,
  useTriggerDiscovery,
  useDiscoveryStatus,
} from "@/hooks/useDiscovery";
import { useConnections } from "@/hooks/useConnections";

// ── Progress bar ───────────────────────────────────────────────────────────────

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full bg-gray-200 rounded-full h-2">
      <div
        className="bg-blue-600 h-2 rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ── Discovery trigger panel ────────────────────────────────────────────────────

function DiscoveryPanel({ connectionId }: { connectionId: string }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const trigger = useTriggerDiscovery(connectionId);
  const status = useDiscoveryStatus(connectionId, jobId, !!jobId);

  const stage = status.data?.stage ?? "";
  const isRunning = !!jobId && stage !== "done" && stage !== "error";

  return (
    <div className="bg-white rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-3">
        <button
          onClick={() =>
            trigger.mutateAsync("full").then((r) => setJobId(r.job_id))
          }
          disabled={isRunning || trigger.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium
                     disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700"
        >
          {isRunning ? "Running…" : "Full Discovery"}
        </button>
        <button
          onClick={() =>
            trigger.mutateAsync("incremental").then((r) => setJobId(r.job_id))
          }
          disabled={isRunning || trigger.isPending}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md text-sm font-medium
                     disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-200"
        >
          Incremental
        </button>
        {status.data && (
          <span className="text-sm text-gray-500 capitalize">
            {status.data.stage} — {status.data.pct}%
          </span>
        )}
      </div>
      {isRunning && <ProgressBar pct={status.data?.pct ?? 0} />}
      {stage === "done" && (
        <p className="text-sm text-green-600 font-medium">
          Discovery complete. {status.data?.detail}
        </p>
      )}
      {stage === "error" && (
        <p className="text-sm text-red-600">Error: {status.data?.detail}</p>
      )}
    </div>
  );
}

// ── Column detail row ──────────────────────────────────────────────────────────

function ColumnRow({ col }: { col: CatalogTableDetail["columns"][0] }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-3 font-mono text-sm text-gray-800">{col.column_name}</td>
      <td className="py-2 pr-3 text-sm text-gray-500">{col.data_type}</td>
      <td className="py-2 pr-3 text-center">
        {col.is_primary_key && (
          <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded">PK</span>
        )}
        {col.is_foreign_key && (
          <span className="ml-1 text-xs bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">FK</span>
        )}
      </td>
      <td className="py-2 pr-3 text-center">
        {col.is_pii_flagged && (
          <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">PII</span>
        )}
      </td>
      <td className="py-2 text-sm text-gray-400 max-w-xs truncate">
        {col.sample_values?.values?.slice(0, 3).join(", ")}
      </td>
    </tr>
  );
}

// ── Table detail panel ─────────────────────────────────────────────────────────

function TableDetailPanel({
  tableId,
  onClose,
}: {
  tableId: string;
  onClose: () => void;
}) {
  const { data: table, isLoading } = useCatalogTable(tableId);
  const patch = usePatchCatalogTable(tableId);
  const [desc, setDesc] = useState("");
  const [editing, setEditing] = useState(false);

  if (isLoading) return <div className="p-6 text-gray-400">Loading…</div>;
  if (!table) return null;

  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex justify-end">
      <div className="w-full max-w-2xl bg-white h-full overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <h2 className="font-semibold text-gray-900">
              {table.schema_name}.{table.table_name}
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {table.object_type} · v{table.discovery_version}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl">
            ×
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* PII flag */}
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={table.is_pii_flagged}
                onChange={(e) =>
                  patch.mutate({ is_pii_flagged: e.target.checked })
                }
                className="rounded"
              />
              <span className="text-sm text-gray-700">Table contains PII</span>
            </label>
          </div>

          {/* AI description */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-700">
                AI Description
              </span>
              <button
                onClick={() => {
                  setDesc(table.ai_description ?? "");
                  setEditing(true);
                }}
                className="text-xs text-blue-600 hover:underline"
              >
                Edit
              </button>
            </div>
            {editing ? (
              <div className="space-y-2">
                <textarea
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  rows={3}
                  className="w-full border rounded-md p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      patch.mutate({ ai_description: desc });
                      setEditing(false);
                    }}
                    className="text-xs px-3 py-1 bg-blue-600 text-white rounded-md"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="text-xs px-3 py-1 text-gray-600 hover:bg-gray-100 rounded-md"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-500 italic">
                {table.ai_description || "No description yet."}
              </p>
            )}
          </div>

          {/* Columns */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              Columns ({table.columns.length})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-xs text-gray-400 uppercase border-b">
                    <th className="pb-2 pr-3">Name</th>
                    <th className="pb-2 pr-3">Type</th>
                    <th className="pb-2 pr-3">Keys</th>
                    <th className="pb-2 pr-3">PII</th>
                    <th className="pb-2">Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {table.columns.map((col) => (
                    <ColumnRow key={col.id} col={col} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Table row in catalog list ──────────────────────────────────────────────────

function CatalogRow({
  table,
  onClick,
}: {
  table: CatalogTable;
  onClick: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className="border-b hover:bg-gray-50 cursor-pointer transition-colors"
    >
      <td className="py-2.5 pr-3 font-mono text-sm text-blue-700">{table.schema_name}</td>
      <td className="py-2.5 pr-3 font-mono text-sm font-medium text-gray-900">
        {table.table_name}
      </td>
      <td className="py-2.5 pr-3">
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            table.object_type === "view"
              ? "bg-purple-100 text-purple-700"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {table.object_type}
        </span>
      </td>
      <td className="py-2.5 pr-3 text-sm text-gray-400">
        {table.row_count_estimate?.toLocaleString() ?? "—"}
      </td>
      <td className="py-2.5 text-center">
        {table.is_pii_flagged && (
          <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">PII</span>
        )}
      </td>
    </tr>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function DiscoveryPage() {
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [search, setSearch] = useState("");
  const [piiOnly, setPiiOnly] = useState(false);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);

  const { data: connsData } = useConnections();
  const connections = connsData ?? [];

  const { data: catalogData, isLoading } = useCatalogTables({
    connection_id: selectedConnectionId || undefined,
    search: search || undefined,
    pii_only: piiOnly,
    page_size: 100,
  });

  const tables = catalogData?.data ?? [];
  const total = catalogData?.total ?? 0;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Metadata Catalog</h1>
        <p className="text-gray-500 mt-1">
          Discover and browse your source database schemas.
        </p>
      </div>

      {/* Connection selector + discovery trigger */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <select
            value={selectedConnectionId}
            onChange={(e) => setSelectedConnectionId(e.target.value)}
            className="border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All connections</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.db_type.toUpperCase()})
              </option>
            ))}
          </select>
        </div>
        {selectedConnectionId && (
          <DiscoveryPanel connectionId={selectedConnectionId} />
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          placeholder="Search tables…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={piiOnly}
            onChange={(e) => setPiiOnly(e.target.checked)}
            className="rounded"
          />
          PII only
        </label>
        <span className="text-sm text-gray-400 ml-auto">
          {total.toLocaleString()} tables
        </span>
      </div>

      {/* Table list */}
      <div className="bg-white rounded-lg border overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-400">Loading catalog…</div>
        ) : tables.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            No tables found. Run a discovery job to populate the catalog.
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr className="text-xs text-gray-400 uppercase">
                <th className="text-left py-3 px-4">Schema</th>
                <th className="text-left py-3 px-4">Table</th>
                <th className="text-left py-3 px-4">Type</th>
                <th className="text-left py-3 px-4">Rows</th>
                <th className="text-center py-3 px-4">Flags</th>
              </tr>
            </thead>
            <tbody className="px-4">
              {tables.map((t) => (
                <CatalogRow
                  key={t.id}
                  table={t}
                  onClick={() => setSelectedTableId(t.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Table detail slide-over */}
      {selectedTableId && (
        <TableDetailPanel
          tableId={selectedTableId}
          onClose={() => setSelectedTableId(null)}
        />
      )}
    </div>
  );
}
