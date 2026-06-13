import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useCustomBuildTool,
  useRankedTools,
  useTriggerEmbedTools,
  useTriggerEmbedEntities,
  type RankedToolResult,
} from "@/hooks/useEmbeddings";
import type { Tool } from "@/hooks/useTools";

const DOMAIN_BADGE: Record<string, string> = {
  finance:    "bg-indigo-100 text-indigo-800",
  sales:      "bg-green-100 text-green-800",
  purchasing: "bg-amber-100 text-amber-800",
  inventory:  "bg-teal-100 text-teal-800",
  operations: "bg-red-100 text-red-800",
};

export default function CustomToolBuilderPage() {
  const [description, setDescription] = useState("");
  const [contextTables, setContextTables] = useState("");
  const [builtTool, setBuiltTool] = useState<Tool | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);

  // Semantic search test panel
  const [searchQuery, setSearchQuery] = useState("");
  const [searchEnabled, setSearchEnabled] = useState(false);

  const buildTool = useCustomBuildTool();
  const embedTools = useTriggerEmbedTools();
  const embedEntities = useTriggerEmbedEntities();
  const qc = useQueryClient();

  const { data: rankedTools = [], isFetching: rankingLoading } = useRankedTools(
    searchQuery,
    undefined,
    searchEnabled && searchQuery.length >= 2
  );

  const handleBuild = () => {
    if (!description.trim()) return;
    setBuildError(null);
    setBuiltTool(null);

    const tables = contextTables
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    buildTool.mutate(
      { description, context_tables: tables.length ? tables : undefined },
      {
        onSuccess: (res: any) => {
          if (res.data?.success && res.data?.tool) {
            setBuiltTool(res.data.tool);
            qc.invalidateQueries({ queryKey: ["tools"] });
          } else {
            setBuildError(res.data?.error ?? "Unknown error from builder");
          }
        },
        onError: (err: any) => {
          setBuildError(err?.response?.data?.detail ?? "Build request failed");
        },
      }
    );
  };

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Custom Tool Builder</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Describe what you want to query in plain English — Claude will generate a
          validated, parameterised SQL tool.
        </p>
      </div>

      {/* Embedding controls */}
      <div className="flex gap-3 flex-wrap">
        <EmbedButton
          label="Embed All Tools"
          isPending={embedTools.isPending}
          onClick={() => embedTools.mutate(false)}
        />
        <EmbedButton
          label="Embed All Entities"
          isPending={embedEntities.isPending}
          onClick={() => embedEntities.mutate(false)}
        />
        <EmbedButton
          label="Force Re-embed Tools"
          isPending={embedTools.isPending}
          onClick={() => embedTools.mutate(true)}
          variant="outline"
        />
      </div>

      {/* Builder form */}
      <div className="bg-white border rounded-xl p-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-900">Generate New Tool</h2>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Description <span className="text-red-500">*</span>
          </label>
          <textarea
            rows={4}
            placeholder="e.g. Show me the total sales revenue and invoice count by month for a given date range"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Context tables{" "}
            <span className="text-gray-400 font-normal">(optional, comma-separated)</span>
          </label>
          <input
            type="text"
            placeholder="e.g. OINV, INV1, OCRD"
            value={contextTables}
            onChange={(e) => setContextTables(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
        </div>

        <button
          onClick={handleBuild}
          disabled={!description.trim() || buildTool.isPending}
          className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {buildTool.isPending ? "Generating…" : "Generate Tool with Claude"}
        </button>

        {buildError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            <p className="font-medium">Build failed</p>
            <p className="mt-0.5">{buildError}</p>
          </div>
        )}

        {builtTool && <BuiltToolCard tool={builtTool} />}
      </div>

      {/* Semantic Search / Ranking Test Panel */}
      <div className="bg-white border rounded-xl p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Tool Ranking Preview</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Test how the ranking engine responds to a natural-language question.
          </p>
        </div>

        <div className="flex gap-3">
          <input
            type="text"
            placeholder="e.g. What is our total AR balance this quarter?"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSearchEnabled(false);
            }}
            className="flex-1 border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
          />
          <button
            onClick={() => setSearchEnabled(true)}
            disabled={searchQuery.length < 2}
            className="px-4 py-2 bg-gray-900 text-white text-sm rounded-lg hover:bg-gray-700 disabled:opacity-50"
          >
            Rank
          </button>
        </div>

        {rankingLoading && (
          <p className="text-sm text-gray-400">Ranking…</p>
        )}

        {!rankingLoading && searchEnabled && rankedTools.length === 0 && (
          <p className="text-sm text-gray-400">
            No matching tools found. Try embedding tools first.
          </p>
        )}

        {rankedTools.length > 0 && (
          <div className="space-y-2">
            {rankedTools.map((t, idx) => (
              <RankedToolCard key={t.tool_id} tool={t} rank={idx + 1} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function EmbedButton({
  label,
  isPending,
  onClick,
  variant = "primary",
}: {
  label: string;
  isPending: boolean;
  onClick: () => void;
  variant?: "primary" | "outline";
}) {
  return (
    <button
      onClick={onClick}
      disabled={isPending}
      className={`px-3 py-2 text-sm rounded-lg disabled:opacity-50 transition-colors ${
        variant === "primary"
          ? "bg-indigo-600 text-white hover:bg-indigo-700"
          : "border text-gray-700 hover:bg-gray-50"
      }`}
    >
      {isPending ? "Running…" : label}
    </button>
  );
}

function BuiltToolCard({ tool }: { tool: Tool }) {
  const [showSQL, setShowSQL] = useState(false);

  return (
    <div className="border border-green-200 bg-green-50 rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold text-green-800">Tool created successfully</p>
          <p className="text-sm text-green-700 mt-0.5 font-mono">{tool.name}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          DOMAIN_BADGE[tool.domain] || "bg-gray-100 text-gray-700"
        }`}>
          {tool.domain}
        </span>
      </div>

      <p className="text-sm text-gray-700">{tool.description}</p>

      {tool.input_schema.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Parameters</p>
          <div className="flex flex-wrap gap-1.5">
            {tool.input_schema.map((p) => (
              <span
                key={p.name}
                className="text-xs bg-white border px-2 py-0.5 rounded font-mono text-gray-700"
              >
                :{p.name}
                <span className="text-gray-400 ml-1">({p.type})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => setShowSQL((s) => !s)}
        className="text-xs text-indigo-600 hover:underline"
      >
        {showSQL ? "Hide SQL" : "Show SQL template"}
      </button>

      {showSQL && (
        <pre className="bg-gray-900 text-green-400 text-xs p-3 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono">
          {tool.sql_template}
        </pre>
      )}
    </div>
  );
}

function RankedToolCard({
  tool,
  rank,
}: {
  tool: RankedToolResult;
  rank: number;
}) {
  const scoreColor =
    tool.final_score >= 0.8
      ? "text-green-700"
      : tool.final_score >= 0.6
      ? "text-yellow-700"
      : "text-red-600";

  return (
    <div className="border rounded-lg p-3 flex items-start gap-3">
      <span className="w-7 h-7 rounded-full bg-gray-100 text-gray-600 text-xs font-bold flex items-center justify-center flex-shrink-0">
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-medium text-gray-900 text-sm">{tool.tool_name}</p>
          <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
            DOMAIN_BADGE[tool.domain] || "bg-gray-100 text-gray-700"
          }`}>
            {tool.domain}
          </span>
          <span className="text-xs text-gray-400">{tool.category.replace("_", " ")}</span>
        </div>
        {tool.description && (
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{tool.description}</p>
        )}
        {/* Score breakdown */}
        <div className="flex gap-3 mt-1.5 text-xs text-gray-400">
          <span className={`font-semibold ${scoreColor}`}>
            {(tool.final_score * 100).toFixed(1)}% final
          </span>
          <span>sim {(tool.semantic_similarity * 100).toFixed(0)}%</span>
          <span>success {(tool.success_rate * 100).toFixed(0)}%</span>
          <span>feedback {(tool.feedback_weight * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}
