import { useState, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Send, Plus, Trash2, MessageSquare, BarChart2,
  Table2, TrendingUp, ThumbsUp, ThumbsDown, HelpCircle,
  LayoutDashboard, Copy, Check, RotateCcw, Sparkles, User,
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
import { useTypewriter } from "@/hooks/useTypewriter";
import { askStream, type ReasoningStep } from "@/hooks/useAskStream";
import Markdown from "@/components/chat/Markdown";
import LiveReasoning from "@/components/chat/LiveReasoning";
import TrendChart from "@/components/chat/TrendChart";
import AnomalyBadge from "@/components/chat/AnomalyBadge";
import LineagePanel from "@/components/chat/LineagePanel";
import ReasoningPanel from "@/components/chat/ReasoningPanel";
import ExportButton from "@/components/chat/ExportButton";

// ChatGPT-style example prompts shown on an empty conversation.
const EXAMPLE_PROMPTS = [
  "Total sales this quarter",
  "Top 5 customers by revenue",
  "Monthly revenue trend for the last 6 months",
  "How many open sales orders are there?",
];

// ── Chart hint icon ──────────────────────────────────────────────────────────

function ChartIcon({ hint }: { hint: string | null }) {
  if (hint === "line" || hint === "area") return <TrendingUp className="w-4 h-4 text-blue-500" />;
  if (hint === "bar" || hint === "donut") return <BarChart2 className="w-4 h-4 text-violet-500" />;
  return <Table2 className="w-4 h-4 text-gray-400" />;
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string | null | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch { /* clipboard unavailable */ }
      }}
      className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
      title="Copy answer"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
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

// ── Assistant answer text (Markdown + streaming-style typewriter) ─────────────

function AnswerText({
  text,
  isError,
  animate,
}: {
  text: string;
  isError: boolean;
  animate: boolean;
}) {
  const shown = useTypewriter(text, animate);
  if (isError) {
    return <p className="text-sm leading-relaxed text-red-600 dark:text-red-400">{text}</p>;
  }
  return <Markdown>{shown || "​"}</Markdown>;
}

// ── Answer card ───────────────────────────────────────────────────────────────

function AnswerCard({
  turn,
  conversationId,
  animate,
  onFollowUp,
  onRegenerate,
}: {
  turn: ConversationTurn | AskResponse;
  conversationId: string;
  animate: boolean;
  onFollowUp: (q: string) => void;
  onRegenerate: () => void;
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
  const answerText =
    turn.answer_text || (isError ? (turn as AskResponse).error_message : "No answer available.") || "";

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
        <p className="text-sm text-gray-600 dark:text-gray-300">{turn.answer_text}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Answer text — Markdown, with streaming-style reveal on fresh answers */}
      <AnswerText text={answerText} isError={isError} animate={animate} />

      {/* Trend chart — shown instead of table for Trend intent */}
      {trendData && (
        <TrendChart
          data={trendData as unknown as Parameters<typeof TrendChart>[0]["data"]}
          chartHint={(turn.chart_hint === "area" ? "area" : "line") as "line" | "area"}
        />
      )}

      {/* Data table — shown for non-trend answers */}
      {!trendData && rows && rows.length > 0 && columns && columns.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="px-3 py-2 text-left font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {rows.slice(0, 10).map((row, i) => (
                <tr key={i} className={`hover:bg-gray-50 dark:hover:bg-gray-800/60 ${anomalyIndex.has(i) ? "bg-red-50 dark:bg-red-950/40" : ""}`}>
                  {columns.map((col) => {
                    const cellAnomaly = (anomalies ?? []).find(
                      (a) => a.column === col && Object.entries(a.row).every(([k, v]) => row[k] === v)
                    );
                    return (
                      <td key={col} className="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">
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
            <p className="px-3 py-2 text-xs text-gray-400 bg-gray-50 dark:bg-gray-800 border-t dark:border-gray-700">
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

      {/* Reasoning panel — how the agent reached the answer */}
      <ReasoningPanel
        lineage={lineage}
        intent={turn.intent}
        confidence={turn.confidence_score}
      />

      {/* Lineage panel */}
      {lineage && Object.keys(lineage).length > 0 && (
        <LineagePanel lineage={lineage as Parameters<typeof LineagePanel>[0]["lineage"]} />
      )}

      {/* Meta row + actions */}
      <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
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
          <CopyButton text={answerText} />
          <button
            onClick={onRegenerate}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            title="Regenerate answer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Regenerate
          </button>
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
              className="px-2 py-1 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 text-xs rounded-full border border-blue-100 dark:border-blue-900 hover:bg-blue-100 dark:hover:bg-blue-900/50 hover:border-blue-300 transition-colors text-left"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Avatar ────────────────────────────────────────────────────────────────────

function Avatar({ role }: { role: "user" | "assistant" }) {
  if (role === "user") {
    return (
      <div className="w-8 h-8 shrink-0 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-gray-600 dark:text-gray-300">
        <User className="w-4 h-4" />
      </div>
    );
  }
  return (
    <div className="w-8 h-8 shrink-0 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center text-white shadow-sm">
      <Sparkles className="w-4 h-4" />
    </div>
  );
}

// ── Chat message row (full-width, ChatGPT-style) ──────────────────────────────

function MessageRow({
  turn,
  conversationId,
  animate,
  onClarify,
  onFollowUp,
  onRegenerate,
}: {
  turn: ConversationTurn;
  conversationId: string;
  animate: boolean;
  onClarify: (q: string) => void;
  onFollowUp: (q: string) => void;
  onRegenerate: (q: string) => void;
}) {
  const isClarification =
    (turn.answer_data as Record<string, unknown> | null)?.type === "clarification";

  return (
    <div>
      {/* User message row */}
      <div className="w-full">
        <div className="mx-auto max-w-3xl px-4 py-5 flex gap-4">
          <Avatar role="user" />
          <div className="min-w-0 flex-1 pt-1">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-0.5">You</p>
            <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{turn.question}</p>
          </div>
        </div>
      </div>

      {/* Assistant message row */}
      <div className="w-full bg-gray-50/70 dark:bg-gray-800/40">
        <div className="mx-auto max-w-3xl px-4 py-5 flex gap-4">
          <Avatar role="assistant" />
          <div className="min-w-0 flex-1 pt-1">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">SAP B1 Assistant</p>
            {isClarification ? (
              <ClarificationCard
                question={turn.answer_text ?? "Could you provide more details?"}
                onAnswer={onClarify}
              />
            ) : (
              <AnswerCard
                turn={turn}
                conversationId={conversationId}
                animate={animate}
                onFollowUp={onFollowUp}
                onRegenerate={() => onRegenerate(turn.question)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Example prompt cards ──────────────────────────────────────────────────────

function ExamplePrompts({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
      {EXAMPLE_PROMPTS.map((p) => (
        <button
          key={p}
          onClick={() => onPick(p)}
          className="text-left border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-700 dark:text-gray-300 hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50/50 dark:hover:bg-gray-800 transition-colors"
        >
          {p}
        </button>
      ))}
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
      className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
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
  const [animateTurnId, setAnimateTurnId] = useState<string | null>(null);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [liveSteps, setLiveSteps] = useState<ReasoningStep[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const qc = useQueryClient();
  const { data: conversations } = useConversations();
  const { data: turns } = useConversationTurns(activeId);
  const createConv = useCreateConversation();
  const deleteConv = useDeleteConversation();
  const ask = useAsk(activeId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy, liveSteps]);

  async function handleNewConversation() {
    const conv = await createConv.mutateAsync({ connection_id: connectionId ?? undefined });
    setActiveId(conv.id);
  }

  async function handleSend(question?: string) {
    const q = (question ?? input).trim();
    if (!q || !activeId || busy) return;
    if (!question) setInput("");

    setBusy(true);
    setPendingQuestion(q);
    setLiveSteps([]);
    try {
      // Stream the agent's reasoning live, then refetch so the saved turn renders.
      await askStream(activeId, q, connectionId, {
        onStep: (s) => setLiveSteps((prev) => [...prev, s]),
        onFinal: (data) => {
          if (data?.turn_id) setAnimateTurnId(data.turn_id);
        },
      });
      qc.invalidateQueries({ queryKey: ["conversations", activeId, "turns"] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      // Streaming unavailable — fall back to the non-streaming mutation.
      try {
        const res = await ask.mutateAsync({ question: q });
        if (res?.turn_id) setAnimateTurnId(res.turn_id);
      } catch {
        /* surfaced as an error turn on refetch */
      }
    } finally {
      setBusy(false);
      setPendingQuestion("");
      setLiveSteps([]);
    }
  }

  // Pick an example prompt: create a conversation first if none is active, then
  // send (the effect below fires once the new conversation id exists).
  async function sendPrompt(q: string) {
    if (activeId) {
      handleSend(q);
      return;
    }
    const conv = await createConv.mutateAsync({ connection_id: connectionId ?? undefined });
    setActiveId(conv.id);
    setPendingPrompt(q);
  }

  useEffect(() => {
    if (pendingPrompt && activeId && !busy) {
      const q = pendingPrompt;
      setPendingPrompt(null);
      handleSend(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, activeId]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const hasTurns = (turns ?? []).length > 0;

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 flex flex-col">
        <div className="p-3 border-b border-gray-200 dark:border-gray-800 space-y-2">
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
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
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
            <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-4 text-center">
              No conversations yet.
            </p>
          )}
        </nav>
      </aside>

      {/* Chat area */}
      <div className="flex-1 flex flex-col bg-white dark:bg-gray-900">
        {activeId && hasTurns ? (
          <>
            <div className="flex-1 overflow-y-auto">
              {(turns ?? []).map((turn) => (
                <MessageRow
                  key={turn.id}
                  turn={turn}
                  conversationId={activeId}
                  animate={turn.id === animateTurnId}
                  onClarify={(answer) => handleSend(answer)}
                  onFollowUp={(q) => handleSend(q)}
                  onRegenerate={(q) => handleSend(q)}
                />
              ))}

              {/* Pending state — live reasoning as the agent thinks */}
              {busy && (
                <>
                  <div className="w-full">
                    <div className="mx-auto max-w-3xl px-4 py-5 flex gap-4">
                      <Avatar role="user" />
                      <div className="min-w-0 flex-1 pt-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-0.5">You</p>
                        <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                          {pendingQuestion || "…"}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="w-full bg-gray-50/70 dark:bg-gray-800/40">
                    <div className="mx-auto max-w-3xl px-4 py-5 flex gap-4">
                      <Avatar role="assistant" />
                      <div className="min-w-0 flex-1 pt-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">SAP B1 Assistant</p>
                        <LiveReasoning steps={liveSteps} />
                      </div>
                    </div>
                  </div>
                </>
              )}

              <div ref={bottomRef} />
            </div>

            <Composer
              input={input}
              setInput={setInput}
              onSend={() => handleSend()}
              onKeyDown={handleKeyDown}
              disabled={busy}
            />
          </>
        ) : activeId ? (
          // Active but empty conversation — greeting + example prompts + composer
          <>
            <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center text-center p-8 gap-6">
              <Avatar role="assistant" />
              <div>
                <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">How can I help with your SAP B1 data?</h2>
                <p className="text-gray-400 dark:text-gray-500 mt-1 text-sm">Ask a question, or pick an example to start.</p>
              </div>
              <ExamplePrompts onPick={sendPrompt} />
            </div>
            <Composer
              input={input}
              setInput={setInput}
              onSend={() => handleSend()}
              onKeyDown={handleKeyDown}
              disabled={busy}
            />
          </>
        ) : (
          // No conversation selected
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 gap-6">
            <Avatar role="assistant" />
            <div>
              <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-100">Ask your SAP data anything</h2>
              <p className="text-gray-400 dark:text-gray-500 mt-2 max-w-sm text-sm">
                Select a connection, then start a conversation to ask about your finances,
                sales, purchasing, inventory, or operations.
              </p>
            </div>
            <ExamplePrompts onPick={sendPrompt} />
            <button
              onClick={handleNewConversation}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm font-medium"
            >
              Start conversation
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Composer (sticky bottom input) ────────────────────────────────────────────

function Composer({
  input,
  setInput,
  onSend,
  onKeyDown,
  disabled,
}: {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  disabled: boolean;
}) {
  return (
    <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-3">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-2 border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 rounded-3xl px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message the SAP B1 Assistant…"
            className="flex-1 resize-none bg-transparent dark:bg-transparent px-2 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none max-h-40"
            disabled={disabled}
          />
          <button
            onClick={onSend}
            disabled={!input.trim() || disabled}
            className="p-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-center text-[11px] text-gray-400 dark:text-gray-500 mt-1.5">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
