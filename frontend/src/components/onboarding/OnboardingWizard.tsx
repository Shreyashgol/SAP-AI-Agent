/**
 * OnboardingWizard — 4-step guided setup shown to first-time tenants.
 *
 * Step 1: Connect — create a DB connection
 * Step 2: Discover — trigger the schema discovery crawl, poll for completion
 * Step 3: Review — quick-preview of detected entities
 * Step 4: Ask — fire a first question and redirect to Chat
 *
 * The wizard is dismissed by writing "onboarding_complete" to localStorage.
 * It is shown when:  no connections exist  AND  localStorage key is absent.
 */

import { useState } from "react";
import { CheckCircle, Database, Search, Layers, MessageSquare, ChevronRight, X } from "lucide-react";
import { useConnections } from "@/hooks/useConnections";
import { useCreateConnection } from "@/hooks/useConnections";
import { useNavigate } from "react-router-dom";

const STORAGE_KEY = "onboarding_complete";

// ── Step indicators ───────────────────────────────────────────────────────────

const STEPS = [
  { icon: Database, label: "Connect" },
  { icon: Search, label: "Discover" },
  { icon: Layers, label: "Review" },
  { icon: MessageSquare, label: "Ask" },
];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const done = i < current;
        const active = i === current;
        return (
          <div key={i} className="flex items-center">
            <div
              className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors ${
                done
                  ? "bg-blue-600 border-blue-600 text-white"
                  : active
                  ? "border-blue-600 text-blue-600 bg-white"
                  : "border-gray-200 text-gray-300 bg-white"
              }`}
            >
              {done ? <CheckCircle className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
            </div>
            <span
              className={`ml-1.5 text-xs font-medium hidden sm:inline ${
                active ? "text-blue-600" : done ? "text-gray-500" : "text-gray-300"
              }`}
            >
              {step.label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`w-8 h-0.5 mx-2 ${i < current ? "bg-blue-600" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Step 1: Connect ───────────────────────────────────────────────────────────

function StepConnect({ onNext }: { onNext: (connectionId: string) => void }) {
  const createConn = useCreateConnection();
  const [form, setForm] = useState({
    name: "",
    db_type: "mssql" as "mssql" | "hana",
    host: "",
    port: "1433",
    database_name: "",
    username: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const conn = await createConn.mutateAsync({
        name: form.name,
        db_type: form.db_type,
        host: form.host,
        port: Number(form.port),
        database_name: form.database_name,
        username: form.username,
        password: form.password,
        is_tls: true,
      });
      onNext(conn.id);
    } catch (err: unknown) {
      setError((err as Error).message ?? "Connection failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Connect your database</h2>
        <p className="text-sm text-gray-500 mt-1">
          Connect SAP Business One or any MSSQL database to begin.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="block text-xs font-medium text-gray-700 mb-1">Connection name</label>
          <input
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="SAP B1 Production"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Database type</label>
          <select
            value={form.db_type}
            onChange={(e) => setForm((f) => ({ ...f, db_type: e.target.value as "mssql" | "hana", port: e.target.value === "hana" ? "30015" : "1433" }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="mssql">SAP B1 on MSSQL</option>
            <option value="hana">SAP B1 on HANA</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Port</label>
          <input
            required
            type="number"
            value={form.port}
            onChange={(e) => setForm((f) => ({ ...f, port: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Host / server</label>
          <input
            required
            value={form.host}
            onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="192.168.1.10"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Database name</label>
          <input
            required
            value={form.database_name}
            onChange={(e) => setForm((f) => ({ ...f, database_name: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="SBODemoUS"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Username</label>
          <input
            required
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Password</label>
          <input
            required
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={createConn.isPending}
        className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-40 flex items-center justify-center gap-2"
      >
        {createConn.isPending ? "Connecting…" : <>Connect & continue <ChevronRight className="w-4 h-4" /></>}
      </button>
    </form>
  );
}

// ── Step 2: Discover ──────────────────────────────────────────────────────────

function StepDiscover({
  connectionId,
  onNext,
}: {
  connectionId: string;
  onNext: () => void;
}) {
  const [launched, setLaunched] = useState(false);
  const [polling, setPolling] = useState(false);

  async function handleLaunch() {
    setLaunched(true);
    setPolling(true);
    try {
      const { apiClient } = await import("@/lib/api");
      await apiClient.post(`/discovery/${connectionId}/start`);
    } catch {
      // ignore — task may already be running
    }
    // Poll every 3 seconds for up to 2 minutes, then auto-advance
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const { apiClient } = await import("@/lib/api");
        const res = await apiClient.get(`/discovery/${connectionId}/status`);
        const st = res.data?.status;
        if (st === "completed" || st === "success" || attempts > 40) {
          clearInterval(interval);
          setPolling(false);
          onNext();
        }
      } catch {
        if (attempts > 40) { clearInterval(interval); setPolling(false); onNext(); }
      }
    }, 3000);
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Discover your schema</h2>
        <p className="text-sm text-gray-500 mt-1">
          We'll scan your database to map tables, columns, relationships, and entities.
          This takes 1–3 minutes.
        </p>
      </div>

      {!launched ? (
        <button
          onClick={handleLaunch}
          className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 flex items-center justify-center gap-2"
        >
          <Search className="w-4 h-4" /> Start discovery
        </button>
      ) : (
        <div className="flex flex-col items-center gap-4 py-8">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500 animate-pulse">
            {polling ? "Scanning your database…" : "Done!"}
          </p>
          {!polling && (
            <button
              onClick={onNext}
              className="px-6 py-2 bg-blue-600 text-white text-sm rounded-xl hover:bg-blue-700 flex items-center gap-2"
            >
              Continue <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Step 3: Review ────────────────────────────────────────────────────────────

function StepReview({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Review detected entities</h2>
        <p className="text-sm text-gray-500 mt-1">
          The AI has mapped your database to business entities. You can fine-tune
          these in the Semantic Layer at any time.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {["Customers", "Sales Orders", "Invoices", "Inventory Items", "Vendors", "Payments"].map((e) => (
          <div key={e} className="flex items-center gap-2 p-3 border border-gray-200 rounded-lg bg-white">
            <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
            <span className="text-sm text-gray-700">{e}</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400">
        Visit <strong>Semantic Layer</strong> to review all entities and KPIs in detail.
      </p>
      <button
        onClick={onNext}
        className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 flex items-center justify-center gap-2"
      >
        Looks good — continue <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}

// ── Step 4: Ask ───────────────────────────────────────────────────────────────

function StepAsk({ onFinish }: { onFinish: () => void }) {
  const navigate = useNavigate();
  const STARTER_QUESTIONS = [
    "What is our total revenue this month?",
    "Show me the top 10 customers by sales.",
    "What is our outstanding accounts receivable?",
    "Which products have low inventory?",
  ];

  function handleQuestion(q: string) {
    // Store the starter question in sessionStorage for ChatPage to pick up
    sessionStorage.setItem("starter_question", q);
    onFinish();
    navigate("/");
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Ask your first question</h2>
        <p className="text-sm text-gray-500 mt-1">
          Try one of these starter questions or go to Chat to ask your own.
        </p>
      </div>
      <div className="space-y-2">
        {STARTER_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => handleQuestion(q)}
            className="w-full text-left px-4 py-3 border border-gray-200 rounded-xl text-sm text-gray-700 hover:border-blue-400 hover:bg-blue-50 transition-colors flex items-center justify-between group"
          >
            {q}
            <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-blue-500" />
          </button>
        ))}
      </div>
      <button
        onClick={onFinish}
        className="w-full py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
      >
        Skip — I'll explore on my own
      </button>
    </div>
  );
}

// ── Wizard shell ──────────────────────────────────────────────────────────────

export function useShowOnboarding(): boolean {
  const { data: connections, isLoading } = useConnections();
  if (isLoading) return false;
  if (localStorage.getItem(STORAGE_KEY)) return false;
  return !connections || connections.length === 0;
}

export default function OnboardingWizard() {
  const [step, setStep] = useState(0);
  const [connectionId, setConnectionId] = useState<string>("");
  const [dismissed, setDismissed] = useState(false);

  function finish() {
    localStorage.setItem(STORAGE_KEY, "1");
    setDismissed(true);
  }

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "1");
    setDismissed(true);
  }

  if (dismissed) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-500 px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-white font-semibold text-lg">Welcome to SAP AI Platform</h1>
            <p className="text-blue-100 text-sm mt-0.5">Let's get you set up in 4 steps</p>
          </div>
          <button onClick={dismiss} className="text-blue-200 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="px-6 py-4 border-b border-gray-100">
          <StepIndicator current={step} />
        </div>

        {/* Step content */}
        <div className="px-6 py-6">
          {step === 0 && (
            <StepConnect
              onNext={(id) => {
                setConnectionId(id);
                setStep(1);
              }}
            />
          )}
          {step === 1 && (
            <StepDiscover connectionId={connectionId} onNext={() => setStep(2)} />
          )}
          {step === 2 && <StepReview onNext={() => setStep(3)} />}
          {step === 3 && <StepAsk onFinish={finish} />}
        </div>
      </div>
    </div>
  );
}
