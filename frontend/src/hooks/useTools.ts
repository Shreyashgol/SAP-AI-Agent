import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";

const API = "/tools";

export interface Tool {
  id: string;
  name: string;
  description: string | null;
  category: string;
  domain: string;
  status: string;
  version: number;
  is_system: boolean;
  is_human_override: boolean;
  pack_source: string | null;
  sql_template: string;
  input_schema: ToolParam[];
  output_schema: { columns: { name: string; type: string }[] };
  permissions: Record<string, unknown> | null;
  last_validated_at: string | null;
  created_at: string;
}

export interface ToolParam {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
  description?: string;
}

export interface ToolsFilter {
  domain?: string;
  category?: string;
  search?: string;
  status?: string;
}

export function useTools(filters: ToolsFilter = {}) {
  return useQuery({
    queryKey: ["tools", filters],
    queryFn: async () => {
      // limit=200 (endpoint max) so freshly generated tools aren't hidden past the default page of 50
      const { data } = await api.get<Tool[]>(API, { params: { limit: 200, ...filters } });
      return data;
    },
    staleTime: 60_000,
  });
}

export function useTool(toolId: string) {
  return useQuery({
    queryKey: ["tool", toolId],
    queryFn: async () => {
      const { data } = await api.get<Tool>(`${API}/${toolId}`);
      return data;
    },
    enabled: !!toolId,
  });
}

export function useCreateTool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Tool>) => api.post<Tool>(API, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tools"] }),
  });
}

export function usePatchTool(toolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Tool>) => api.patch<Tool>(`${API}/${toolId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      qc.invalidateQueries({ queryKey: ["tool", toolId] });
    },
  });
}

export function useDeleteTool(toolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete(`${API}/${toolId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tools"] }),
  });
}

export function useApplyToolPack() {
  return useMutation({
    mutationFn: (packSource?: string) =>
      api.post(`${API}/actions/apply-pack`, null, { params: { pack_source: packSource ?? "sap_b1" } }),
  });
}

export function useGenerateToolsForConnection() {
  return useMutation({
    mutationFn: (connectionId: string) =>
      api.post(`${API}/actions/generate-for-connection`, null, {
        params: { connection_id: connectionId },
      }),
  });
}

export function useGenerateKPITools() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`${API}/actions/generate-kpi-tools`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tools"] }),
  });
}
