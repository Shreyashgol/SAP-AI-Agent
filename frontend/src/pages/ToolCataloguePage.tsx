import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useTools,
  usePatchTool,
  useDeleteTool,
  useApplyToolPack,
  useGenerateKPITools,
  type Tool,
  type ToolsFilter,
} from "@/hooks/useTools";

const DOMAIN_BADGE: Record<string, string> = {
  finance:    "bg-indigo-100 text-indigo-800",
  sales:      "bg-green-100 text-green-800 dark:text-green-300",
  purchasing: "bg-amber-100 text-amber-800",
  inventory:  "bg-teal-100 text-teal-800",
  operations: "bg-red-100 text-red-800",
};

const CATEGORY_BADGE: Record<string, string> = {
  aggregate:     "bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300",
  entity_summary:"bg-purple-50 text-purple-700",
  filter:        "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300",
  trend:         "bg-pink-50 text-pink-700",
  kpi:           "bg-orange-50 text-orange-700",
  join:          "bg-cyan-50 text-cyan-700",
};

const DOMAINS = ["finance", "sales", "purchasing", "inventory", "operations"];
const CATEGORIES = ["aggregate", "entity_summary", "filter", "trend", "kpi", "join"];

export default function ToolCataloguePage() {
  const [filters, setFilters] = useState<ToolsFilter>({});
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [jobMessage, setJobMessage] = useState<string | null>(null);

  const { data: tools = [], isLoading } = useTools(filters);
  const applyPack = useApplyToolPack();
  const generateKPIs = useGenerateKPITools();

  const handleApplyPack = () => {
    applyPack.mutate(undefined, {
      onSuccess: (res: any) =>
        setJobMessage(`Pack job queued — ID: ${res.data?.job_id}`),
    });
  };

  const handleGenerateKPIs = () => {
    generateKPIs.mutate(undefined, {
      onSuccess: (res: any) =>
        setJobMessage(`KPI tools job queued — ID: ${res.data?.job_id}`),
    });
  };

  return (
    <div className="flex h-full">
      {/* Left panel — filters + actions */}
      <div className="w-64 border-r bg-white dark:bg-gray-800 flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Tool Catalogue</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{tools.length} active tools</p>
        </div>

        {/* Search */}
        <div className="p-4 border-b space-y-3">
          <input
            type="text"
            placeholder="Search tools…"
            value={filters.search ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value || undefined }))}
            className="w-full border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />

          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">DOMAIN</p>
            <div className="space-y-1">
              <FilterBtn
                label="All"
                active={!filters.domain}
                onClick={() => setFilters((f) => ({ ...f, domain: undefined }))}
              />
              {DOMAINS.map((d) => (
                <FilterBtn
                  key={d}
                  label={d}
                  active={filters.domain === d}
                  onClick={() => setFilters((f) => ({ ...f, domain: d }))}
                />
              ))}
            </div>
          </div>

          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">CATEGORY</p>
            <div className="space-y-1">
              <FilterBtn
                label="All"
                active={!filters.category}
                onClick={() => setFilters((f) => ({ ...f, category: undefined }))}
              />
              {CATEGORIES.map((c) => (
                <FilterBtn
                  key={c}
                  label={c.replace("_", " ")}
                  active={filters.category === c}
                  onClick={() => setFilters((f) => ({ ...f, category: c }))}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="p-4 space-y-2">
          <button
            onClick={handleApplyPack}
            disabled={applyPack.isPending}
            className="w-full px-3 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {applyPack.isPending ? "Applying…" : "Apply SAP B1 Pack"}
          </button>
          <button
            onClick={handleGenerateKPIs}
            disabled={generateKPIs.isPending}
            className="w-full px-3 py-2 bg-white dark:bg-gray-800 border text-sm text-gray-700 dark:text-gray-300 rounded hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            {generateKPIs.isPending ? "Generating…" : "Generate KPI Tools"}
          </button>
          {jobMessage && (
            <p className="text-xs text-gray-500 dark:text-gray-400 break-all">{jobMessage}</p>
          )}
          <Link
            to="/tools/builder"
            className="block w-full text-center px-3 py-2 text-sm text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-900 rounded hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors"
          >
            Custom Tool Builder →
          </Link>
        </div>
      </div>

      {/* Main table */}
      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-500">
            Loading…
          </div>
        ) : tools.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-gray-500 dark:text-gray-400 text-sm">No tools found.</p>
              <p className="text-gray-400 dark:text-gray-500 text-xs mt-1">
                Apply the SAP B1 Pack to seed 50 pre-built tools.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800/60 sticky top-0 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-300">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-300">Domain</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-300">Category</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-300">Version</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 dark:text-gray-300">Source</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {tools.map((tool) => (
                <ToolRow
                  key={tool.id}
                  tool={tool}
                  selected={selectedTool?.id === tool.id}
                  onClick={() => setSelectedTool(tool)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail slide-over */}
      {selectedTool && (
        <ToolDetailPanel
          tool={selectedTool}
          onClose={() => setSelectedTool(null)}
        />
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FilterBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left text-xs px-2 py-1 rounded capitalize transition-colors ${
        active
          ? "bg-indigo-100 text-indigo-800 font-medium"
          : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
      }`}
    >
      {label}
    </button>
  );
}

function ToolRow({
  tool,
  selected,
  onClick,
}: {
  tool: Tool;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors ${
        selected ? "bg-indigo-50 dark:bg-indigo-950/40" : ""
      }`}
    >
      <td className="px-4 py-3">
        <p className="font-medium text-gray-900 dark:text-gray-100">{tool.name}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">{tool.description}</p>
      </td>
      <td className="px-4 py-3">
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            DOMAIN_BADGE[tool.domain] || "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          }`}
        >
          {tool.domain}
        </span>
      </td>
      <td className="px-4 py-3">
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${
            CATEGORY_BADGE[tool.category] || "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          }`}
        >
          {tool.category.replace("_", " ")}
        </span>
      </td>
      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">v{tool.version}</td>
      <td className="px-4 py-3">
        {tool.is_human_override ? (
          <span className="text-xs text-orange-600 font-medium">Custom</span>
        ) : tool.pack_source === "sap_b1" ? (
          <span className="text-xs text-indigo-600">SAP B1 Pack</span>
        ) : (
          <span className="text-xs text-gray-400 dark:text-gray-500">{tool.pack_source}</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-indigo-600 text-xs">View →</td>
    </tr>
  );
}

function ToolDetailPanel({
  tool,
  onClose,
}: {
  tool: Tool;
  onClose: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(tool.description ?? "");
  const patchTool = usePatchTool(tool.id);
  const deleteTool = useDeleteTool(tool.id);

  const handleSave = () => {
    patchTool.mutate({ description }, { onSuccess: () => setEditing(false) });
  };

  const handleDelete = () => {
    if (!confirm(`Deprecate tool "${tool.name}"?`)) return;
    deleteTool.mutate(undefined, { onSuccess: onClose });
  };

  return (
    <div className="w-[480px] border-l bg-white dark:bg-gray-800 overflow-y-auto flex flex-col">
      {/* Header */}
      <div className="p-4 border-b flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">{tool.name}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                DOMAIN_BADGE[tool.domain] || "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
              }`}
            >
              {tool.domain}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded font-medium ${
                CATEGORY_BADGE[tool.category] || "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"
              }`}
            >
              {tool.category.replace("_", " ")}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">v{tool.version}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-xl ml-2 leading-none flex-shrink-0"
        >
          ×
        </button>
      </div>

      <div className="flex-1 p-4 space-y-5">
        {/* Description */}
        <section>
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Description</p>
            {!editing && (
              <button
                onClick={() => setEditing(true)}
                className="text-xs text-indigo-600 hover:underline"
              >
                Edit
              </button>
            )}
          </div>
          {editing ? (
            <div className="space-y-2">
              <textarea
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleSave}
                  disabled={patchTool.isPending}
                  className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {patchTool.isPending ? "Saving…" : "Save"}
                </button>
                <button
                  onClick={() => { setEditing(false); setDescription(tool.description ?? ""); }}
                  className="px-3 py-1.5 text-xs border rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-700 dark:text-gray-300">{tool.description || "—"}</p>
          )}
        </section>

        {/* Input schema */}
        <section>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1.5">
            Parameters ({tool.input_schema.length})
          </p>
          {tool.input_schema.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">No parameters.</p>
          ) : (
            <div className="space-y-1.5">
              {tool.input_schema.map((p) => (
                <div key={p.name} className="flex items-start gap-2 text-sm">
                  <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs text-gray-800 dark:text-gray-100 font-mono">
                    :{p.name}
                  </code>
                  <span className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {p.type}
                    {p.required ? " · required" : ` · optional (default: ${p.default ?? "null"})`}
                  </span>
                  {p.description && (
                    <span className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">— {p.description}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* SQL template */}
        <section>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1.5">
            SQL Template
          </p>
          <pre className="bg-gray-900 text-green-400 text-xs p-3 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
            {tool.sql_template}
          </pre>
        </section>

        {/* Output schema */}
        {tool.output_schema.columns.length > 0 && (
          <section>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-1.5">
              Output Columns
            </p>
            <div className="flex flex-wrap gap-1.5">
              {tool.output_schema.columns.map((col) => (
                <span
                  key={col.name}
                  className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded font-mono text-gray-700 dark:text-gray-300"
                >
                  {col.name}
                  <span className="text-gray-400 dark:text-gray-500 ml-1">:{col.type}</span>
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Metadata */}
        <section className="border-t pt-4 text-xs text-gray-400 dark:text-gray-500 space-y-1">
          <p>Source: {tool.pack_source || "—"}</p>
          <p>System: {tool.is_system ? "Yes" : "No"}</p>
          <p>Human override: {tool.is_human_override ? "Yes" : "No"}</p>
          {tool.last_validated_at && <p>Last validated: {tool.last_validated_at}</p>}
        </section>
      </div>

      {/* Footer actions */}
      <div className="p-4 border-t flex justify-end">
        <button
          onClick={handleDelete}
          disabled={deleteTool.isPending}
          className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900 rounded hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-50"
        >
          {deleteTool.isPending ? "Deprecating…" : "Deprecate Tool"}
        </button>
      </div>
    </div>
  );
}
