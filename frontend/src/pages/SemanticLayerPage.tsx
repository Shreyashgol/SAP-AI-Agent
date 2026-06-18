import { useState } from "react";
import {
  SemanticEntity,
  useApplyPack,
  useCreateGlossaryTerm,
  useEntities,
  useGlossary,
  useKPIs,
  usePatchEntity,
  useRunAIMapping,
  useSeedKPIs,
} from "@/hooks/useSemantic";
import { useConnections } from "@/hooks/useConnections";

// ── Tab types ──────────────────────────────────────────────────────────────────

type Tab = "entities" | "kpis" | "glossary";

// ── Confidence badge ───────────────────────────────────────────────────────────

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80
      ? "bg-green-100 text-green-800 dark:text-green-300"
      : pct >= 50
      ? "bg-yellow-100 text-yellow-800"
      : "bg-red-100 text-red-700 dark:text-red-300";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${color}`}>
      {pct}%
    </span>
  );
}

// ── Domain pill ────────────────────────────────────────────────────────────────

const DOMAIN_COLORS: Record<string, string> = {
  finance:    "bg-blue-100 text-blue-800",
  sales:      "bg-green-100 text-green-800 dark:text-green-300",
  purchasing: "bg-orange-100 text-orange-800",
  inventory:  "bg-purple-100 text-purple-800",
  operations: "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300",
};

function DomainPill({ domain }: { domain: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${DOMAIN_COLORS[domain] ?? "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"}`}>
      {domain}
    </span>
  );
}

// ── Entity edit slide-over ─────────────────────────────────────────────────────

function EntityEditPanel({
  entity,
  onClose,
}: {
  entity: SemanticEntity;
  onClose: () => void;
}) {
  const [name, setName] = useState(entity.entity_name);
  const [domain, setDomain] = useState(entity.domain);
  const [desc, setDesc] = useState(entity.description ?? "");
  const patch = usePatchEntity(entity.id);

  const handleSave = () => {
    patch.mutate(
      { entity_name: name, domain, description: desc },
      { onSuccess: onClose }
    );
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex justify-end">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 h-full overflow-y-auto shadow-xl flex flex-col">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Edit Entity</h2>
          <button onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-700 text-xl">×</button>
        </div>

        <div className="p-4 space-y-4 flex-1">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Entity Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Domain</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {["finance", "sales", "purchasing", "inventory", "operations"].map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={4}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="pt-2 border-t text-xs text-gray-400 dark:text-gray-500 space-y-1">
            <p>Source: <span className="font-mono">{entity.pack_source}</span></p>
            <p>Version: {entity.semantic_version}</p>
            {entity.is_human_override && (
              <p className="text-blue-600 dark:text-blue-400 font-medium">Human override — AI won't overwrite this.</p>
            )}
            {entity.is_ai_generated && !entity.is_human_override && (
              <p className="text-yellow-600">AI-generated — saving will lock it as human override.</p>
            )}
          </div>
        </div>

        <div className="p-4 border-t flex gap-2">
          <button
            onClick={handleSave}
            disabled={patch.isPending}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium
                       disabled:opacity-50 hover:bg-blue-700"
          >
            {patch.isPending ? "Saving…" : "Save Override"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md text-sm"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Entities tab ───────────────────────────────────────────────────────────────

function EntitiesTab({ connectionId }: { connectionId: string }) {
  const [domainFilter, setDomainFilter] = useState("");
  const [aiOnly, setAiOnly] = useState(false);
  const [editEntity, setEditEntity] = useState<SemanticEntity | null>(null);

  const { data, isLoading } = useEntities({
    connection_id: connectionId || undefined,
    domain: domainFilter || undefined,
    ai_only: aiOnly,
    page_size: 100,
  });
  const entities = data?.data ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All domains</option>
          {["finance", "sales", "purchasing", "inventory", "operations"].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={aiOnly}
            onChange={(e) => setAiOnly(e.target.checked)}
            className="rounded"
          />
          Unreviewed AI only
        </label>

        <span className="text-sm text-gray-400 dark:text-gray-500 ml-auto">{total} entities</span>
      </div>

      {/* Entity table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-400 dark:text-gray-500">Loading entities…</div>
        ) : entities.length === 0 ? (
          <div className="p-8 text-center text-gray-400 dark:text-gray-500">
            No entities found. Apply a pack or run AI mapping first.
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-800/60 border-b">
              <tr className="text-xs text-gray-400 dark:text-gray-500 uppercase">
                <th className="text-left py-3 px-4">Entity Name</th>
                <th className="text-left py-3 px-4">Domain</th>
                <th className="text-left py-3 px-4">Source</th>
                <th className="text-left py-3 px-4">Confidence</th>
                <th className="text-left py-3 px-4">Status</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr key={e.id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  <td className="py-2.5 px-4 font-medium text-gray-900 dark:text-gray-100 text-sm">{e.entity_name}</td>
                  <td className="py-2.5 px-4">
                    <DomainPill domain={e.domain} />
                  </td>
                  <td className="py-2.5 px-4 text-xs text-gray-400 dark:text-gray-500 font-mono">{e.pack_source}</td>
                  <td className="py-2.5 px-4">
                    <ConfidenceBadge value={e.confidence} />
                  </td>
                  <td className="py-2.5 px-4">
                    {e.is_human_override ? (
                      <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">Human override</span>
                    ) : e.is_ai_generated ? (
                      <span className="text-xs text-yellow-600">AI — pending review</span>
                    ) : (
                      <span className="text-xs text-green-600 dark:text-green-400">Pack</span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 text-right">
                    <button
                      onClick={() => setEditEntity(e)}
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editEntity && (
        <EntityEditPanel entity={editEntity} onClose={() => setEditEntity(null)} />
      )}
    </div>
  );
}

// ── KPIs tab ───────────────────────────────────────────────────────────────────

function KPIsTab() {
  const [domainFilter, setDomainFilter] = useState("");
  const seedKPIs = useSeedKPIs();
  const { data, isLoading } = useKPIs(domainFilter || undefined);
  const kpis = data?.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All domains</option>
          {["finance", "sales", "purchasing", "inventory", "operations"].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <button
          onClick={() => seedKPIs.mutate()}
          disabled={seedKPIs.isPending}
          className="ml-auto px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm
                     hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          {seedKPIs.isPending ? "Seeding…" : "Seed System KPIs"}
        </button>

        <span className="text-sm text-gray-400 dark:text-gray-500">{data?.total ?? 0} KPIs</span>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg border overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-400 dark:text-gray-500">Loading KPIs…</div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-gray-800/60 border-b">
              <tr className="text-xs text-gray-400 dark:text-gray-500 uppercase">
                <th className="text-left py-3 px-4">Display Name</th>
                <th className="text-left py-3 px-4">Domain</th>
                <th className="text-left py-3 px-4">Method</th>
                <th className="text-left py-3 px-4">Unit</th>
                <th className="text-left py-3 px-4">Formula</th>
              </tr>
            </thead>
            <tbody>
              {kpis.map((k) => (
                <tr key={k.id} className="border-b hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="py-2.5 px-4">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{k.display_name}</p>
                    {k.description && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 line-clamp-1">{k.description}</p>
                    )}
                  </td>
                  <td className="py-2.5 px-4"><DomainPill domain={k.domain} /></td>
                  <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400">{k.aggregation_method}</td>
                  <td className="py-2.5 px-4 text-xs text-gray-500 dark:text-gray-400">{k.unit ?? "—"}</td>
                  <td className="py-2.5 px-4 max-w-xs">
                    <code className="text-xs text-gray-400 dark:text-gray-500 line-clamp-1">{k.formula ?? "—"}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Glossary tab ───────────────────────────────────────────────────────────────

function GlossaryTab() {
  const [domainFilter, setDomainFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newTerm, setNewTerm] = useState("");
  const [newDef, setNewDef] = useState("");
  const createTerm = useCreateGlossaryTerm();
  const { data, isLoading } = useGlossary(domainFilter || undefined);
  const terms = data?.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All domains</option>
          {["finance", "sales", "purchasing", "inventory", "operations"].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <button
          onClick={() => setShowAdd(!showAdd)}
          className="ml-auto px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
        >
          + Add Term
        </button>
        <span className="text-sm text-gray-400 dark:text-gray-500">{data?.total ?? 0} terms</span>
      </div>

      {showAdd && (
        <div className="bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900 rounded-lg p-4 space-y-3">
          <input
            placeholder="Term (e.g. Outstanding Balance)"
            value={newTerm}
            onChange={(e) => setNewTerm(e.target.value)}
            className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <textarea
            placeholder="Definition"
            value={newDef}
            onChange={(e) => setNewDef(e.target.value)}
            rows={2}
            className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (newTerm && newDef) {
                  createTerm.mutate(
                    { term: newTerm, definition: newDef, domain: domainFilter || undefined },
                    { onSuccess: () => { setNewTerm(""); setNewDef(""); setShowAdd(false); } }
                  );
                }
              }}
              disabled={!newTerm || !newDef || createTerm.isPending}
              className="px-4 py-1.5 bg-blue-600 text-white rounded-md text-sm disabled:opacity-50"
            >
              Save
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="px-4 py-1.5 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg border divide-y">
        {isLoading ? (
          <div className="p-8 text-center text-gray-400 dark:text-gray-500">Loading glossary…</div>
        ) : terms.length === 0 ? (
          <div className="p-8 text-center text-gray-400 dark:text-gray-500">
            No glossary terms yet. Add terms above or run AI mapping.
          </div>
        ) : (
          terms.map((t) => (
            <div key={t.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t.term}</p>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{t.definition}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {t.domain && <DomainPill domain={t.domain} />}
                  {t.is_ai_generated && (
                    <span className="text-xs text-yellow-600 bg-yellow-50 px-1.5 py-0.5 rounded">AI</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Action toolbar ─────────────────────────────────────────────────────────────

function ActionToolbar({ connectionId }: { connectionId: string }) {
  const applyPack = useApplyPack();
  const aiMap = useRunAIMapping();

  return (
    <div className="flex items-center gap-3 p-4 bg-white dark:bg-gray-800 border rounded-lg">
      <div className="flex-1">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Semantic layer actions</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Apply entity pack, then run AI mapping for any unmapped tables.
        </p>
      </div>
      <button
        onClick={() => applyPack.mutate({ connection_id: connectionId })}
        disabled={!connectionId || applyPack.isPending}
        className="px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm disabled:opacity-50 hover:bg-blue-700"
      >
        {applyPack.isPending ? "Applying…" : "Apply Pack"}
      </button>
      <button
        onClick={() => aiMap.mutate({ connection_id: connectionId, limit: 50 })}
        disabled={!connectionId || aiMap.isPending}
        className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm disabled:opacity-50 hover:bg-gray-200 dark:hover:bg-gray-700"
      >
        {aiMap.isPending ? "Mapping…" : "AI Map Unmapped"}
      </button>
      {(applyPack.isSuccess || aiMap.isSuccess) && (
        <span className="text-xs text-green-600 dark:text-green-400 font-medium">Job queued ✓</span>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SemanticLayerPage() {
  const [activeTab, setActiveTab] = useState<Tab>("entities");
  const [connectionId, setConnectionId] = useState("");
  const { data: connsData } = useConnections();
  const connections = connsData ?? [];

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "entities", label: "Entities" },
    { id: "kpis",     label: "KPI Library" },
    { id: "glossary", label: "Glossary" },
  ];

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Semantic Layer</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Review and override AI-generated business entity mappings, KPIs, and glossary terms.
        </p>
      </div>

      {/* Connection selector */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-600 dark:text-gray-300">Connection:</label>
        <select
          value={connectionId}
          onChange={(e) => setConnectionId(e.target.value)}
          className="border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">All connections</option>
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.db_type.toUpperCase()})
            </option>
          ))}
        </select>
      </div>

      {/* Pack / AI actions */}
      {connectionId && <ActionToolbar connectionId={connectionId} />}

      {/* Tabs */}
      <div className="border-b">
        <nav className="flex gap-6">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === t.id
                  ? "border-blue-600 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === "entities" && <EntitiesTab connectionId={connectionId} />}
      {activeTab === "kpis"     && <KPIsTab />}
      {activeTab === "glossary" && <GlossaryTab />}
    </div>
  );
}
