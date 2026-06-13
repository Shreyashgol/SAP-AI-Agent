import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface AlertRule {
  id: string;
  tenant_id: string;
  created_by: string;
  kpi_id: string | null;
  name: string;
  rule_type: "threshold" | "anomaly" | "business_event";
  operator: string | null;
  threshold_value: number | null;
  severity: "critical" | "warning" | "info";
  assigned_role_ids: string[];
  monitoring_schedule: "hourly" | "4hourly" | "daily";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleCreate {
  name: string;
  rule_type: "threshold" | "anomaly" | "business_event";
  kpi_id?: string;
  operator?: string;
  threshold_value?: number;
  severity?: "critical" | "warning" | "info";
  monitoring_schedule?: "hourly" | "4hourly" | "daily";
}

export interface Alert {
  id: string;
  tenant_id: string;
  alert_rule_id: string;
  triggered_value: number | null;
  expected_range: Record<string, unknown> | null;
  severity: "critical" | "warning" | "info";
  status: "active" | "acknowledged" | "snoozed" | "escalated";
  acknowledged_by: string | null;
  snoozed_until: string | null;
  suggested_questions: string[] | null;
  rca_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportSchedule {
  id: string;
  tenant_id: string;
  created_by: string;
  name: string;
  questions: string[];
  cron_expression: string;
  delivery_channels: Record<string, unknown>;
  is_active: boolean;
  subscriber_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ReportExecution {
  id: string;
  schedule_id: string;
  status: "pending" | "running" | "completed" | "failed";
  storage_path: string | null;
  error_message: string | null;
  delivered_at: string | null;
  execution_time_ms: number | null;
  created_at: string;
}

// ── Alert rules ───────────────────────────────────────────────────────────────

export function useAlertRules(activeOnly = false) {
  return useQuery<AlertRule[]>({
    queryKey: ["alert-rules", activeOnly],
    queryFn: () =>
      apiClient
        .get(`/alert-rules${activeOnly ? "?active_only=true" : ""}`)
        .then((r) => r.data),
  });
}

export function useCreateAlertRule() {
  const qc = useQueryClient();
  return useMutation<AlertRule, Error, AlertRuleCreate>({
    mutationFn: (body) => apiClient.post("/alert-rules", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
}

export function usePatchAlertRule() {
  const qc = useQueryClient();
  return useMutation<AlertRule, Error, { id: string; body: Partial<AlertRule> }>({
    mutationFn: ({ id, body }) =>
      apiClient.patch(`/alert-rules/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
}

export function useDeleteAlertRule() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/alert-rules/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
}

// ── Triggered alerts ──────────────────────────────────────────────────────────

export function useAlerts(statusFilter?: string) {
  return useQuery<Alert[]>({
    queryKey: ["alerts", statusFilter],
    queryFn: () =>
      apiClient
        .get("/alerts", { params: statusFilter ? { status_filter: statusFilter } : {} })
        .then((r) => r.data),
    refetchInterval: 60_000, // poll every minute for new alerts
  });
}

export function useAlertAction() {
  const qc = useQueryClient();
  return useMutation<
    Alert,
    Error,
    { id: string; status: "acknowledged" | "snoozed" | "escalated"; snoozed_until?: string }
  >({
    mutationFn: ({ id, ...body }) =>
      apiClient.post(`/alerts/${id}/action`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

// ── Report schedules ──────────────────────────────────────────────────────────

export function useReportSchedules() {
  return useQuery<ReportSchedule[]>({
    queryKey: ["report-schedules"],
    queryFn: () => apiClient.get("/report-schedules").then((r) => r.data),
  });
}

export function useCreateReportSchedule() {
  const qc = useQueryClient();
  return useMutation<
    ReportSchedule,
    Error,
    { name: string; questions: string[]; cron_expression: string }
  >({
    mutationFn: (body) => apiClient.post("/report-schedules", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["report-schedules"] }),
  });
}

export function useDeleteReportSchedule() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) =>
      apiClient.delete(`/report-schedules/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["report-schedules"] }),
  });
}

export function useTriggerReport() {
  const qc = useQueryClient();
  return useMutation<ReportExecution, Error, string>({
    mutationFn: (id) =>
      apiClient.post(`/report-schedules/${id}/run`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["report-schedules"] }),
  });
}
