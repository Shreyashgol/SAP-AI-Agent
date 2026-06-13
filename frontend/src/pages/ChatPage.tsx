import { useState, useRef, useEffect } from "react";
import {
  Send, Plus, Trash2, MessageSquare, BarChart2,
  Table2, TrendingUp, ThumbsUp, ThumbsDown, HelpCircle,
  LayoutDashboard,
} from "lucide-react";
import {
  useConversations,
  useConversationTurns,
  useCreateConversation,
  useDeleteConversation,
  useAsk,
  type AskResponse,
  type ConversationTurn,
} from "@/hooks/useConversations";
import { useConnections } from "@/hooks/useConnections";
import { useSubmitFeedback } from "@/hooks/useFeedback";
import { useCreateDashboard, useDashboards } from "@/hooks/useDashboards";
import TrendChart from "@/components/chat/TrendChart";
import AnomalyBadge from "@/components/chat/AnomalyBadge";
import LineagePanel from "@/components/chat/LineagePanel";
import ExportButton from "@/components/chat/ExportButton";

// ── Chart hint icon ──────────────────────────────────────────────────────────

function ChartIcon({ hint }: { hint: string | null }) {
  if (hint === "line" || hint === "area") return <TrendingUp className="w-4 h-4 text-blue-500" />;
  if (hint === "bar" || hint === "donut") return <BarChart2 className="w-4 h-4 text-violet-500" />;
  return <Table2 className="w-4 h-4 text-gray-400" />;
}

// ── Clarification card ────────────────────────────────────────────────────────

function ClarificationCard({
  question,
  onAnswer,
}: {
  question: string;
  onAnswer: (answer: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="border border-amber-200 bg-amber-50 rounded-xl p-4 space-y-3">
      <div className="flex items-start gap-2">
        <HelpCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900 font-medium">{question}</p>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && value.trim()) {
              onAnswer(value.trim());
              setValue("");
            }
          }}
          placeholder="Type your answer…"
          className="flex-1 text-sm border border-amber-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
        />
        <button
          onClick={() => { if (value.trim()) { onAnswer(value.trim()); setValue(""); } }}
          className="px-3 py-1.5 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600 disabled:opacity-40"
          disabled={!value.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}

// ── Feedback buttons ──────────────────────────────────────────────────────────

function FeedbackButtons({ turnId }: { turnId: string }) {
  const [voted, setVoted] = useState<1 | -1 | null>(null);
  const submit = useSubmitFeedback();

  function vote(rating: 1 | -1) {
    if (voted !== null) return;
    setVoted(rating);
    submit.mutate({ conversation_turn_id: turnId, rating });
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => vote(1)}
        className={`p-1 rounded hover:bg-gray-100 transition-colors ${voted === 1 ? "text-green-600" : "text-gray-300 hover:text-green-500"}`}
        title="Helpful"
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => vote(-1)}
        className={`p-1 rounded hover:bg-gray-100 transition-colors ${voted === -1 ? "text-red-500" : "text-gray-300 hover:text-red-400"}`}
        title="Not helpful"
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ── Pin to dashboard button ───────────────────────────────────────────────────

function PinButton({
  turnId,
  chartHint,
}: {
  conversationId: string;
  turnId: string;
  chartHint: string | null;
}) {
  const [pinned, setPinned] = useState(false);
  const { data: dashboards } = useDashboards();
  const createDash = useCreateDashboard();

  async function handlePin() {
    if (pinned) return;
    let dashId: string;

    // Use first dashboard if it exists, else create "My Dashboard"
    if (dashboards && dashboards.length > 0) {
      dashId = dashboards[0].id;
    } else {
      const dash = await createDash.mutateAsync({ name: "My Dashboard" });
      dashId = dash.id;
    }

    // Can't call hook conditionally; we need the add widget call here
    // Use apiClient directly to avoid hook-in-callback restriction
    const { apiClient } = await import("@/lib/api");
    await apiClient.post(`/dashboards/${dashId}/widgets`, {
      conversation_turn_id: turnId,
      widget_type:
        chartHint === "line" || chartHint === "area"
          ? chartHint
          : chartHint === "bar" || chartHint === "donut"
          ? chartHint
          : "table",
    });
    setPinned(true);
  }

  return (
    <button
      onClick={handlePin}
      disabled={pinned || createDash.isPending}
      className={`flex items-center gap-1 text-xs transition-colors ${
        pinned
          ? "text-blue-600 cursor-default"
          : "text-gray-400 hover:text-blue-600"
      }`}
      title="Pin to dashboard"
    >
      <LayoutDashboard className="w-3.5 h-3.5" />
      {pinned ? "Pinned" : "Pin"}
    </button>
  );
}

// ── Answer card ───────────────────────────────────────────────────────────────

function AnswerCard({
  turn,
  conversationId,
  onFollowUp,
}: {
  turn: ConversationTurn | AskResponse;
  conversationId: string;
  onFollowUp: (q: string) => void;
}) {
  const [showSQL, setShowSQL] = useState(false);

  const data = turn.answer_data as Record<string, unknown> | null;
  const rows = data?.rows as Record<string, unknown>[] | undefined;
  const columns = data?.columns as string[] | undefined;
  const anomalies = data?.anomalies as Array<{ row: Record<string, unknown>; column: string; anomaly: { severity: string; description: string; z_score: number } }> | undefined;
  const trendData = data?.type === "trend" ? data : null;

  const isError = "has_error" in turn ? turn.has_error : false;
  const answerType = data?.type as string | undefined;
  const isClarification = answerType === "clarification";

  const turnId = "id" in turn ? turn.id : ("turn_id" in turn ? turn.turn_id : "");
  const lineage = turn.lineage as Record<string, unknown> | null;

  // Build anomaly index for row highlights
  const anomalyIndex = new Set<number>(
    (anomalies ?? []).map((a) => {
      if (!rows) return -1;
      return rows.findIndex((r) =>
        Object.entries(a.row).every(([k, v]) => r[k] === v)
      );
    }).filter((i) => i !== -1)
  );

  if (isClarification) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-gray-600">{turn.answer_text}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Answer text */}
      <p className={`text-sm leading-relaxed ${isError ? "text-red-600" : "text-gray-800"}`}>
        {turn.answer_text || (isError ? (turn as AskResponse).error_message : "No answer available.")}
      </p>

      {/* Trend chart — shown instead of table for Trend intent */}
      {trendData && (
        <TrendChart
          data={trendData as unknown as Parameters<typeof TrendChart>[0]["data"]}
          chartHint={(turn.chart_hint === "area" ? "area" : "line") as "line" | "area"}
        />
      )}

      {/* Data table — shown for non-trend answers */}
      {!trendData && rows && rows.length > 0 && columns && columns.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.slice(0, 10).map((row, i) => (
                <tr key={i} className={`hover:bg-gray-50 ${anomalyIndex.has(i) ? "bg-red-50" : ""}`}>
                  {columns.map((col) => {
                    const cellAnomaly = (anomalies ?? []).find(
                      (a) => a.column === col && Object.entries(a.row).every(([k, v]) => row[k] === v)
                    );
                    return (
                      <td key={col} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                        <span className="mr-1">{String(row[col] ?? "")}</span>
                        {cellAnomaly && (
                          <AnomalyBadge
                            anomaly={{
                              severity: cellAnomaly.anomaly.severity as "low" | "medium" | "high" | "none",
                              description: cellAnomaly.anomaly.description,
                              z_score: cellAnomaly.anomaly.z_score,
                            }}
                          />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 10 && (
            <p className="px-3 py-2 text-xs text-gray-400 bg-gray-50 border-t">
              Showing 10 of {rows.length} rows
            </p>
          )}
        </div>
      )}

      {/* SQL toggle */}
      {turn.sql_query && (
        <div>
          <button
            onClick={() => setShowSQL((v) => !v)}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            {showSQL ? "Hide SQL" : "View SQL"}
          </button>
          {showSQL && (
            <pre className="mt-2 p-3 bg-gray-900 text-green-400 text-xs rounded-lg overflow-x-auto">
              {turn.sql_query}
            </pre>
          )}
        </div>
      )}

      {/* Lineage panel */}
      {lineage && Object.keys(lineage).length > 0 && (
        <LineagePanel lineage={lineage as Parameters<typeof LineagePanel>[0]["lineage"]} />
      )}

      {/* Meta row + actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <ChartIcon hint={turn.chart_hint} />
            {turn.chart_hint ?? "table"}
          </span>
          {turn.confidence_score != null && (
            <span>Confidence: {Math.round(turn.confidence_score * 100)}%</span>
          )}
          {turn.execution_time_ms != null && <span>{turn.execution_time_ms}ms</span>}
          {turn.intent && (
            <span className="bg-gray-100 px-2 py-0.5 rounded">{turn.intent}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {turnId && rows && rows.length > 0 && (
            <ExportButton conversationId={conversationId} turnId={turnId} />
          )}
          {turnId && (
            <PinButton
              conversationId={conversationId}
              turnId={turnId}
              chartHint={turn.chart_hint}
            />
          )}
          {turnId && <FeedbackButtons turnId={turnId} />}
        </div>
      </div>

      {/* Follow-up questions — clickable */}
      {(turn.follow_up_questions ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {(turn.follow_up_questions as string[]).map((q, i) => (
            <button
              key={i}
              onClick={() => onFollowUp(q)}
              className="px-2 py-1 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-100 hover:bg-blue-100 hover:border-blue-300 transition-colors text-left"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  turn,
  conversationId,
  onClarify,
  onFollowUp,
}: {
  turn: ConversationTurn;
  conversationId: string;
  onClarify: (q: string) => void;
  onFollowUp: (q: string) => void;
}) {
  const isClarification =
    (turn.answer_data as Record<string, unknown> | null)?.type === "clarification";

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <div className="max-w-xl bg-blue-600 text-white text-sm px-4 py-2.5 rounded-2xl rounded-tr-sm">
          {turn.question}
        </div>
      </div>
      <div className="flex justify-start">
        <div className="max-w-2xl w-full bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
          {isClarification ? (
            <ClarificationCard
              question={turn.answer_text ?? "Could you provide more details?"}
              onAnswer={onClarify}
            />
          ) : (
            <AnswerCard turn={turn} conversationId={conversationId} onFollowUp={onFollowUp} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Connection selector ───────────────────────────────────────────────────────

function ConnectionSelector({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const { data: connections } = useConnections();
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || null)}
      className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-gray-700"
    >
      <option value="">No connection</option>
      {(connections ?? []).map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

// ── Main chat page ────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: conversations } = useConversations();
  const { data: turns } = useConversationTurns(activeId);
  const createConv = useCreateConversation();
  const deleteConv = useDeleteConversation();
  const ask = useAsk(activeId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, ask.data]);

  async function handleNewConversation() {
    const conv = await createConv.mutateAsync({ connection_id: connectionId ?? undefined });
    setActiveId(conv.id);
  }

  async function handleSend(question?: string) {
    const q = (question ?? input).trim();
    if (!q || !activeId || ask.isPending) return;
    if (!question) setInput("");
    await ask.mutateAsync({ question: q });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-gray-200 bg-gray-50 flex flex-col">
        <div className="p-3 border-b border-gray-200 space-y-2">
          <ConnectionSelector value={connectionId} onChange={setConnectionId} />
          <button
            onClick={handleNewConversation}
            disabled={createConv.isPending}
            className="w-full flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Plus className="w-4 h-4" />
            New conversation
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {(conversations ?? []).map((conv) => (
            <div
              key={conv.id}
              className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm ${
                activeId === conv.id
                  ? "bg-blue-100 text-blue-700"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
              onClick={() => setActiveId(conv.id)}
            >
              <MessageSquare className="w-4 h-4 shrink-0" />
              <span className="flex-1 truncate">{conv.title || "New conversation"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConv.mutate(conv.id);
                  if (activeId === conv.id) setActiveId(null);
                }}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          {!conversations?.length && (
            <p className="text-xs text-gray-400 px-3 py-4 text-center">
              No conversations yet.
            </p>
          )}
        </nav>
      </aside>

      {/* Chat area */}
      <div className="flex-1 flex flex-col">
        {activeId ? (
          <>
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {(turns ?? []).map((turn) => (
                <MessageBubble
                  key={turn.id}
                  turn={turn}
                  conversationId={activeId}
                  onClarify={(answer) => handleSend(answer)}
                  onFollowUp={(q) => handleSend(q)}
                />
              ))}

              {/* Optimistic pending state */}
              {ask.isPending && (
                <div className="space-y-2">
                  <div className="flex justify-end">
                    <div className="max-w-xl bg-blue-600 text-white text-sm px-4 py-2.5 rounded-2xl rounded-tr-sm opacity-70">
                      {input || "…"}
                    </div>
                  </div>
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                      <span className="text-gray-400 text-sm animate-pulse">Thinking…</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Input bar */}
            <div className="border-t border-gray-200 bg-white p-4">
              <div className="flex items-end gap-3 max-w-4xl mx-auto">
                <textarea
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a business question… (Enter to send, Shift+Enter for new line)"
                  className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  disabled={ask.isPending}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || ask.isPending}
                  className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <MessageSquare className="w-16 h-16 text-gray-200 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700">Ask your SAP data anything</h2>
            <p className="text-gray-400 mt-2 max-w-sm">
              Select a connection, then start a conversation to ask about your finances,
              sales, purchasing, inventory, or operations.
            </p>
            <button
              onClick={handleNewConversation}
              className="mt-6 px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-medium"
            >
              Start conversation
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
