import { useState } from "react";
import {
  useKGEdges,
  useKGNodes,
  useConfirmEdge,
  useTriggerKGBuild,
  type KGEdge,
  type KGNode,
} from "@/hooks/useKnowledgeGraph";
import { useTheme } from "@/hooks/useTheme";

const DOMAIN_COLORS: Record<string, string> = {
  finance: "#6366f1",
  sales: "#22c55e",
  purchasing: "#f59e0b",
  inventory: "#14b8a6",
  operations: "#ef4444",
};

const CONFIDENCE_LABEL = (c: number) =>
  c >= 0.9 ? "High" : c >= 0.7 ? "Medium" : "Low";
const CONFIDENCE_CLASS = (c: number) =>
  c >= 0.9
    ? "bg-green-100 text-green-800 dark:text-green-300"
    : c >= 0.7
    ? "bg-yellow-100 text-yellow-800"
    : "bg-red-100 text-red-800";

export default function KnowledgeGraphPage() {
  const [connectionId, setConnectionId] = useState("");
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [showUnconfirmed, setShowUnconfirmed] = useState(false);
  const [buildJobId, setBuildJobId] = useState<string | null>(null);

  const { data: nodes = [], isLoading: nodesLoading } = useKGNodes(
    connectionId || undefined
  );
  const { data: edges = [], isLoading: edgesLoading } = useKGEdges(showUnconfirmed);

  const buildKG = useTriggerKGBuild(connectionId);

  const handleBuild = () => {
    if (!connectionId) return;
    buildKG.mutate(undefined, {
      onSuccess: (res: any) => setBuildJobId(res.data?.job_id),
    });
  };

  const loading = nodesLoading || edgesLoading;

  return (
    <div className="flex h-full">
      {/* Left panel */}
      <div className="w-80 border-r bg-white dark:bg-gray-800 flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Knowledge Graph</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Entity relationship map
          </p>
        </div>

        {/* Filters */}
        <div className="p-4 space-y-3 border-b">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Connection ID
            </label>
            <input
              type="text"
              placeholder="Filter by connection…"
              value={connectionId}
              onChange={(e) => setConnectionId(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={showUnconfirmed}
              onChange={(e) => setShowUnconfirmed(e.target.checked)}
              className="rounded"
            />
            Show unconfirmed edges only
          </label>
        </div>

        {/* Build action */}
        <div className="p-4 border-b">
          <button
            onClick={handleBuild}
            disabled={!connectionId || buildKG.isPending}
            className="w-full px-3 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {buildKG.isPending ? "Queuing…" : "Build KG"}
          </button>
          {buildJobId && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">Job: {buildJobId}</p>
          )}
        </div>

        {/* Stats */}
        <div className="p-4 grid grid-cols-2 gap-3">
          <StatCard label="Nodes" value={nodes.length} />
          <StatCard
            label="Edges"
            value={edges.length}
          />
          <StatCard
            label="Confirmed"
            value={edges.filter((e) => e.is_admin_confirmed).length}
          />
          <StatCard
            label="Pending"
            value={edges.filter((e) => !e.is_admin_confirmed).length}
          />
        </div>

        {/* Domain legend */}
        <div className="p-4 border-t mt-auto">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">DOMAINS</p>
          {Object.entries(DOMAIN_COLORS).map(([domain, color]) => (
            <div key={domain} className="flex items-center gap-2 mb-1.5">
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-gray-700 dark:text-gray-300 capitalize">{domain}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
            Loading graph…
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-gray-500 dark:text-gray-400 text-sm">No nodes found.</p>
              <p className="text-gray-400 dark:text-gray-500 text-xs mt-1">
                Enter a connection ID and click Build KG to generate.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-hidden flex">
            {/* Graph canvas (D3 placeholder — rendered as node list until D3 is wired) */}
            <div className="flex-1 overflow-auto p-4">
              <GraphCanvas
                nodes={nodes}
                edges={edges}
                selectedNode={selectedNode}
                onSelectNode={setSelectedNode}
              />
            </div>

            {/* Node detail panel */}
            {selectedNode && (
              <NodeDetailPanel
                node={selectedNode}
                edges={edges.filter(
                  (e) =>
                    e.from_node_id === selectedNode.id ||
                    e.to_node_id === selectedNode.id
                )}
                onClose={() => setSelectedNode(null)}
              />
            )}
          </div>
        )}

        {/* Unconfirmed edge review section */}
        {showUnconfirmed && edges.length > 0 && (
          <UnconfirmedEdgeList edges={edges} />
        )}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800/60 rounded-lg p-3 text-center">
      <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</p>
    </div>
  );
}

function GraphCanvas({
  nodes,
  edges,
  selectedNode,
  onSelectNode,
}: {
  nodes: KGNode[];
  edges: KGEdge[];
  selectedNode: KGNode | null;
  onSelectNode: (n: KGNode) => void;
}) {
  // Group nodes by domain for layout
  const byDomain: Record<string, KGNode[]> = {};
  for (const n of nodes) {
    const d = n.domain || "unknown";
    (byDomain[d] = byDomain[d] || []).push(n);
  }

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
        {nodes.length} nodes · {edges.length} edges
        {" · "}
        <span className="text-indigo-500">
          Install D3.js to enable force-directed layout
        </span>
      </p>
      <div className="space-y-4">
        {Object.entries(byDomain).map(([domain, domainNodes]) => (
          <div key={domain}>
            <p
              className="text-xs font-semibold uppercase mb-2 tracking-wider"
              style={{ color: DOMAIN_COLORS[domain] || "#6b7280" }}
            >
              {domain}
            </p>
            <div className="flex flex-wrap gap-2">
              {domainNodes.map((node) => (
                <NodeChip
                  key={node.id}
                  node={node}
                  selected={selectedNode?.id === node.id}
                  onClick={() => onSelectNode(node)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function NodeChip({
  node,
  selected,
  onClick,
}: {
  node: KGNode;
  selected: boolean;
  onClick: () => void;
}) {
  const color = DOMAIN_COLORS[node.domain || ""] || "#6b7280";
  const dark = useTheme((s) => s.theme === "dark");
  const restBg = dark ? "#1f2937" : "white"; // gray-800 in dark
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
        selected
          ? "shadow-md scale-105"
          : "hover:shadow-sm hover:scale-102"
      }`}
      style={{
        borderColor: color,
        backgroundColor: selected ? color : restBg,
        color: selected ? "white" : color,
      }}
    >
      {node.node_label}
    </button>
  );
}

function NodeDetailPanel({
  node,
  edges,
  onClose,
}: {
  node: KGNode;
  edges: KGEdge[];
  onClose: () => void;
}) {
  return (
    <div className="w-80 border-l bg-white dark:bg-gray-800 overflow-y-auto">
      <div className="p-4 border-b flex items-center justify-between">
        <div>
          <p className="font-semibold text-gray-900 dark:text-gray-100">{node.node_label}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{node.domain}</p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none"
        >
          ×
        </button>
      </div>

      <div className="p-4">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-3">
          Connections ({edges.length})
        </p>
        {edges.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">No edges.</p>
        ) : (
          <div className="space-y-2">
            {edges.map((edge) => (
              <EdgeCard key={edge.id} edge={edge} currentNodeId={node.id} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EdgeCard({
  edge,
  currentNodeId,
}: {
  edge: KGEdge;
  currentNodeId: string;
}) {
  const confirmEdge = useConfirmEdge(edge.id);
  const direction = edge.from_node_id === currentNodeId ? "→" : "←";

  return (
    <div className="border rounded-lg p-3 text-sm">
      <div className="flex items-center justify-between mb-1">
        <span className="font-medium text-gray-700 dark:text-gray-300">
          {direction} {edge.relation_name}
        </span>
        <span
          className={`text-xs px-1.5 py-0.5 rounded-full ${CONFIDENCE_CLASS(edge.confidence)}`}
        >
          {CONFIDENCE_LABEL(edge.confidence)}
        </span>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">
        {edge.join_condition}
      </p>
      {!edge.is_admin_confirmed && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => confirmEdge.mutate(true)}
            disabled={confirmEdge.isPending}
            className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            Confirm
          </button>
          <button
            onClick={() => confirmEdge.mutate(false)}
            disabled={confirmEdge.isPending}
            className="px-2 py-1 text-xs bg-red-100 text-red-700 dark:text-red-300 rounded hover:bg-red-200 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
      {edge.is_admin_confirmed && (
        <span className="inline-block mt-1 text-xs text-green-600 dark:text-green-400">✓ Confirmed</span>
      )}
    </div>
  );
}

function UnconfirmedEdgeList({ edges }: { edges: KGEdge[] }) {
  return (
    <div className="border-t bg-yellow-50 p-4">
      <p className="text-sm font-semibold text-yellow-800 mb-2">
        Pending Review — {edges.length} edge{edges.length !== 1 ? "s" : ""} awaiting confirmation
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-yellow-700">
              <th className="pb-1 pr-4">Relation</th>
              <th className="pb-1 pr-4">Type</th>
              <th className="pb-1 pr-4">Confidence</th>
              <th className="pb-1">Join Condition</th>
            </tr>
          </thead>
          <tbody>
            {edges.slice(0, 20).map((e) => (
              <tr key={e.id} className="border-t border-yellow-200">
                <td className="py-1 pr-4 font-medium text-gray-700 dark:text-gray-300">{e.relation_name}</td>
                <td className="py-1 pr-4 text-gray-500 dark:text-gray-400">{e.edge_type}</td>
                <td className="py-1 pr-4">
                  <span className={`px-1.5 py-0.5 rounded-full ${CONFIDENCE_CLASS(e.confidence)}`}>
                    {(e.confidence * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="py-1 font-mono text-gray-500 dark:text-gray-400 truncate max-w-xs">{e.join_condition}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {edges.length > 20 && (
          <p className="text-xs text-yellow-600 mt-1">
            Showing 20 of {edges.length}. Use the node panel to review remaining edges.
          </p>
        )}
      </div>
    </div>
  );
}
