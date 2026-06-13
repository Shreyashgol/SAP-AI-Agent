import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import type { APIResponse } from "@/types";

export interface Connection {
  id: string;
  name: string;
  db_type: "hana" | "mssql";
  host: string;
  port: number;
  database_name: string;
  is_active: boolean;
  is_tls: boolean;
  last_health_status: string | null;
  last_health_check_at: string | null;
}

export interface ConnectionCreate {
  name: string;
  db_type: "hana" | "mssql";
  host: string;
  port: number;
  database_name: string;
  username: string;
  password: string;
  is_tls: boolean;
}

export interface TestResult {
  success: boolean;
  latency_ms?: number;
  db_version?: string;
  is_read_only?: boolean;
  error?: string;
}

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: async () => {
      const res = await api.get<APIResponse<Connection[]>>("/connections");
      return res.data.data ?? [];
    },
  });
}

export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ConnectionCreate) => {
      const res = await api.post<APIResponse<Connection>>("/connections", body);
      return res.data.data!;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<APIResponse<TestResult>>(`/connections/${id}/test`);
      return res.data.data!;
    },
  });
}

export function useDeleteConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/connections/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["connections"] }),
  });
}
