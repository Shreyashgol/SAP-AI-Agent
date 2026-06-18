import { useState } from "react";
import { Bell, Plus, Trash2, Play, CheckCircle, Clock, ArrowUpCircle, AlertTriangle, Info, X } from "lucide-react";
import {
  useAlertRules,
  useAlerts,
  useCreateAlertRule,
  useDeleteAlertRule,
  usePatchAlertRule,
  useAlertAction,
  useReportSchedules,
  useCreateReportSchedule,
  useDeleteReportSchedule,
  useTriggerReport,
  type AlertRuleCreate,
} from "@/hooks/useAlerts";

// ── Severity badge ────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    critical: "bg-red-100 text-red-700 dark:text-red-300 border-red-300",
    warning: "bg-amber-100 text-amber-700 dark:text-amber-300 border-amber-300",
    info: "bg-blue-100 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-900",
  };
  const icons: Record<string, React.ReactNode> = {
    critical: <AlertTriangle className="w-3 h-3" />,
    warning: <AlertTriangle className="w-3 h-3" />,
    info: <Info className="w-3 h-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-medium ${styles[severity] ?? "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"}`}>
      {icons[severity]}
      {severity}
    </span>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400",
    acknowledged: "bg-green-50 dark:bg-green-950/40 text-green-600 dark:text-green-400",
    snoozed: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400",
    escalated: "bg-purple-50 text-purple-700",
  };
  const icons: Record<string, React.ReactNode> = {
    active: <Bell className="w-3 h-3" />,
    acknowledged: <CheckCircle className="w-3 h-3" />,
    snoozed: <Clock className="w-3 h-3" />,
    escalated: <ArrowUpCircle className="w-3 h-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-medium ${styles[status] ?? "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"}`}>
      {icons[status]}
      {status}
    </span>
  );
}

// ── Create rule form ──────────────────────────────────────────────────────────

function CreateRuleForm({ onClose }: { onClose: () => void }) {
  const createRule = useCreateAlertRule();
  const [form, setForm] = useState<AlertRuleCreate>({
    name: "",
    rule_type: "threshold",
    severity: "warning",
    monitoring_schedule: "hourly",
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    await createRule.mutateAsync(form);
    onClose();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 border border-gray-200 dark:border-gray-700 rounded-xl bg-gray-50 dark:bg-gray-800/60">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">New Alert Rule</h3>
        <button type="button" onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
          <input
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="e.g. Revenue drops below 50k"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Rule type</label>
          <select
            value={form.rule_type}
            onChange={(e) => setForm((f) => ({ ...f, rule_type: e.target.value as AlertRuleCreate["rule_type"] }))}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="threshold">Threshold</option>
            <option value="anomaly">Anomaly detection</option>
            <option value="business_event">Business event</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Severity</label>
          <select
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value as AlertRuleCreate["severity"] }))}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
        </div>

        {form.rule_type === "threshold" && (
          <>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Operator</label>
              <select
                value={form.operator ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, operator: e.target.value || undefined }))}
                className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select…</option>
                {["<", "<=", ">", ">=", "="].map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Threshold value</label>
              <input
                type="number"
                value={form.threshold_value ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, threshold_value: e.target.value ? Number(e.target.value) : undefined }))}
                className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. 50000"
              />
            </div>
          </>
        )}

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Check frequency</label>
          <select
            value={form.monitoring_schedule}
            onChange={(e) => setForm((f) => ({ ...f, monitoring_schedule: e.target.value as AlertRuleCreate["monitoring_schedule"] }))}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="hourly">Hourly</option>
            <option value="4hourly">Every 4 hours</option>
            <option value="daily">Daily</option>
          </select>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white">
          Cancel
        </button>
        <button
          type="submit"
          disabled={createRule.isPending}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-40"
        >
          {createRule.isPending ? "Creating…" : "Create rule"}
        </button>
      </div>
    </form>
  );
}

// ── Create report form ────────────────────────────────────────────────────────

function CreateReportForm({ onClose }: { onClose: () => void }) {
  const createReport = useCreateReportSchedule();
  const [name, setName] = useState("");
  const [cron, setCron] = useState("0 8 * * 1");
  const [questions, setQuestions] = useState<string[]>(["What is our total revenue this week?"]);
  const [newQ, setNewQ] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || questions.length === 0) return;
    await createReport.mutateAsync({ name, questions, cron_expression: cron });
    onClose();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 border border-gray-200 dark:border-gray-700 rounded-xl bg-gray-50 dark:bg-gray-800/60">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-900 dark:text-gray-100">New Report Schedule</h3>
        <button type="button" onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Report name</label>
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Weekly Finance Summary"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          Cron expression
          <span className="ml-2 font-normal text-gray-400 dark:text-gray-500">(minute hour dom month dow)</span>
        </label>
        <input
          value={cron}
          onChange={(e) => setCron(e.target.value)}
          className="w-full text-sm font-mono border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="0 8 * * 1"
        />
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">e.g. "0 8 * * 1" = every Monday at 8am</p>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Questions</label>
        <div className="space-y-2">
          {questions.map((q, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1 truncate">{q}</span>
              <button
                type="button"
                onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}
                className="text-gray-300 dark:text-gray-600 hover:text-red-500"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-2">
          <input
            value={newQ}
            onChange={(e) => setNewQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (newQ.trim()) { setQuestions((qs) => [...qs, newQ.trim()]); setNewQ(""); }
              }
            }}
            className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Add a question… (Enter to add)"
          />
          <button
            type="button"
            onClick={() => { if (newQ.trim()) { setQuestions((qs) => [...qs, newQ.trim()]); setNewQ(""); } }}
            className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            Add
          </button>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white">Cancel</button>
        <button
          type="submit"
          disabled={createReport.isPending || questions.length === 0}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-40"
        >
          {createReport.isPending ? "Creating…" : "Create schedule"}
        </button>
      </div>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const [tab, setTab] = useState<"active" | "rules" | "reports">("active");
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [showReportForm, setShowReportForm] = useState(false);

  const { data: alerts } = useAlerts(tab === "active" ? "active" : undefined);
  const { data: rules } = useAlertRules();
  const { data: schedules } = useReportSchedules();
  const deleteRule = useDeleteAlertRule();
  const patchRule = usePatchAlertRule();
  const deleteSchedule = useDeleteReportSchedule();
  const triggerReport = useTriggerReport();
  const alertAction = useAlertAction();

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Alerts & Reports</h1>
        <div className="flex gap-2">
          <button
            onClick={() => { setShowRuleForm(true); setShowReportForm(false); setTab("rules"); }}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" /> Alert rule
          </button>
          <button
            onClick={() => { setShowReportForm(true); setShowRuleForm(false); setTab("reports"); }}
            className="flex items-center gap-2 px-3 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <Plus className="w-4 h-4" /> Report schedule
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-6">
          {([
            { key: "active", label: `Active alerts${alerts ? ` (${alerts.length})` : ""}` },
            { key: "rules", label: "Alert rules" },
            { key: "reports", label: "Report schedules" },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                tab === key
                  ? "border-blue-600 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Forms */}
      {tab === "rules" && showRuleForm && (
        <CreateRuleForm onClose={() => setShowRuleForm(false)} />
      )}
      {tab === "reports" && showReportForm && (
        <CreateReportForm onClose={() => setShowReportForm(false)} />
      )}

      {/* Active alerts */}
      {tab === "active" && (
        <div className="space-y-3">
          {(alerts ?? []).length === 0 ? (
            <div className="text-center py-16">
              <CheckCircle className="w-12 h-12 text-green-200 mx-auto mb-3" />
              <p className="text-gray-400 dark:text-gray-500">No active alerts — all clear.</p>
            </div>
          ) : (
            (alerts ?? []).map((alert) => (
              <div key={alert.id} className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-800 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={alert.severity} />
                      <StatusBadge status={alert.status} />
                    </div>
                    {alert.triggered_value != null && (
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        Triggered value: <span className="font-mono font-medium">{alert.triggered_value.toLocaleString()}</span>
                      </p>
                    )}
                    {alert.rca_summary && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">{alert.rca_summary}</p>
                    )}
                  </div>
                  {alert.status === "active" && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => alertAction.mutate({ id: alert.id, status: "acknowledged" })}
                        className="px-3 py-1.5 text-xs bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-900 rounded-lg hover:bg-green-100"
                      >
                        Acknowledge
                      </button>
                      <button
                        onClick={() => alertAction.mutate({ id: alert.id, status: "snoozed" })}
                        className="px-3 py-1.5 text-xs bg-gray-50 dark:bg-gray-800/60 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                      >
                        Snooze 1h
                      </button>
                    </div>
                  )}
                </div>
                {(alert.suggested_questions ?? []).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    <span className="text-xs text-gray-400 dark:text-gray-500">Investigate:</span>
                    {(alert.suggested_questions as string[]).map((q, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 rounded-full border border-blue-100">{q}</span>
                    ))}
                  </div>
                )}
                <p className="text-xs text-gray-400 dark:text-gray-500">{new Date(alert.created_at).toLocaleString()}</p>
              </div>
            ))
          )}
        </div>
      )}

      {/* Alert rules */}
      {tab === "rules" && (
        <div className="space-y-3">
          {(rules ?? []).length === 0 && !showRuleForm && (
            <div className="text-center py-16">
              <Bell className="w-12 h-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 dark:text-gray-500">No alert rules. Create one to start monitoring.</p>
            </div>
          )}
          {(rules ?? []).map((rule) => (
            <div key={rule.id} className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-800 flex items-center gap-4">
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-gray-900 dark:text-gray-100">{rule.name}</span>
                  <SeverityBadge severity={rule.severity} />
                  {!rule.is_active && (
                    <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 rounded">Paused</span>
                  )}
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {rule.rule_type}
                  {rule.operator && rule.threshold_value != null && ` — value ${rule.operator} ${rule.threshold_value.toLocaleString()}`}
                  {" · "}
                  {rule.monitoring_schedule}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => patchRule.mutate({ id: rule.id, body: { is_active: !rule.is_active } })}
                  className="text-xs px-2.5 py-1 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  {rule.is_active ? "Pause" : "Enable"}
                </button>
                <button
                  onClick={() => { if (confirm(`Delete rule "${rule.name}"?`)) deleteRule.mutate(rule.id); }}
                  className="text-gray-300 dark:text-gray-600 hover:text-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Report schedules */}
      {tab === "reports" && (
        <div className="space-y-3">
          {(schedules ?? []).length === 0 && !showReportForm && (
            <div className="text-center py-16">
              <Bell className="w-12 h-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-400 dark:text-gray-500">No report schedules. Create one to automate recurring reports.</p>
            </div>
          )}
          {(schedules ?? []).map((sched) => (
            <div key={sched.id} className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-800 space-y-2">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-gray-900 dark:text-gray-100">{sched.name}</span>
                    {!sched.is_active && (
                      <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 rounded">Paused</span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-gray-500 dark:text-gray-400">{sched.cron_expression}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => triggerReport.mutate(sched.id)}
                    disabled={triggerReport.isPending}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-40"
                    title="Run now"
                  >
                    <Play className="w-3.5 h-3.5" />
                    Run now
                  </button>
                  <button
                    onClick={() => { if (confirm(`Delete schedule "${sched.name}"?`)) deleteSchedule.mutate(sched.id); }}
                    className="text-gray-300 dark:text-gray-600 hover:text-red-500"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {sched.questions.map((q, i) => (
                  <span key={i} className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-full truncate max-w-xs">{q}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
