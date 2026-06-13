import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Dashboard {
  id: string;
  tenant_id: string;
  user_id: string;
  name: string;
  is_shared: boolean;
  share_token: string | null;
  layout: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardWidget {
  id: string;
  dashboard_id: string;
  conversation_turn_id: string;
  title: string | null;
  widget_type: string;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  created_at: string;
  updated_at: string;
}

export interface WidgetCreate {
  conversation_turn_id: string;
  title?: string;
  widget_type?: string;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
}

export interface WidgetPatch {
  title?: string;
  widget_type?: string;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
}

export interface LayoutUpdate {
  layout: Record<string, unknown>;
}

// ── Dashboards ────────────────────────────────────────────────────────────────

export function useDashboards() {
  return useQuery<Dashboard[]>({
    queryKey: ["dashboards"],
    queryFn: () => apiClient.get("/dashboards").then((r) => r.data),
  });
}

export function useCreateDashboard() {
  const qc = useQueryClient();
  return useMutation<Dashboard, Error, { name: string; is_shared?: boolean }>({
    mutationFn: (body) => apiClient.post("/dashboards", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboards"] }),
  });
}

export function useDeleteDashboard() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/dashboards/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboards"] }),
  });
}

export function usePatchDashboard() {
  const qc = useQueryClient();
  return useMutation<
    Dashboard,
    Error,
    { id: string; body: Partial<{ name: string; is_shared: boolean; layout: Record<string, unknown> }> }
  >({
    mutationFn: ({ id, body }) =>
      apiClient.patch(`/dashboards/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboards"] }),
  });
}

// ── Widgets ───────────────────────────────────────────────────────────────────

export function useWidgets(dashboardId: string | null) {
  return useQuery<DashboardWidget[]>({
    queryKey: ["widgets", dashboardId],
    queryFn: () =>
      apiClient.get(`/dashboards/${dashboardId}/widgets`).then((r) => r.data),
    enabled: Boolean(dashboardId),
  });
}

export function useAddWidget(dashboardId: string) {
  const qc = useQueryClient();
  return useMutation<DashboardWidget, Error, WidgetCreate>({
    mutationFn: (body) =>
      apiClient.post(`/dashboards/${dashboardId}/widgets`, body).then((r) => r.data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["widgets", dashboardId] }),
  });
}

export function usePatchWidget(dashboardId: string) {
  const qc = useQueryClient();
  return useMutation<DashboardWidget, Error, { widgetId: string; body: WidgetPatch }>({
    mutationFn: ({ widgetId, body }) =>
      apiClient
        .patch(`/dashboards/${dashboardId}/widgets/${widgetId}`, body)
        .then((r) => r.data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["widgets", dashboardId] }),
  });
}

export function useDeleteWidget(dashboardId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (widgetId) =>
      apiClient
        .delete(`/dashboards/${dashboardId}/widgets/${widgetId}`)
        .then(() => undefined),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["widgets", dashboardId] }),
  });
}
