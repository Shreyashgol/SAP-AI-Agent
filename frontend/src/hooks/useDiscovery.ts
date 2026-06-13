import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";

export interface DiscoveryJobStatus {
  job_id: string;
  stage: string;
  pct: number;
  detail: string;
  updated_at: string;
}

export interface CatalogTable {
  id: string;
  connection_id: string;
  schema_name: string;
  table_name: string;
  object_type: "table" | "view";
  row_count_estimate: number | null;
  is_pii_flagged: boolean;
  ai_description: string | null;
  discovery_version: number;
}

export interface CatalogTableDetail extends CatalogTable {
  metadata_hash: string | null;
  columns: Array<{
    id: string;
    column_name: string;
    data_type: string;
    is_nullable: boolean;
    is_primary_key: boolean;
    is_foreign_key: boolean;
    is_pii_flagged: boolean;
    is_masked: boolean;
    ai_description: string | null;
    ordinal_position: number;
    sample_values: { values: string[] } | null;
    column_stats: Record<string, unknown> | null;
  }>;
}

export interface CatalogListParams {
  search?: string;
  connection_id?: string;
  schema_name?: string;
  pii_only?: boolean;
  page?: number;
  page_size?: number;
}

export function useTriggerDiscovery(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: "full" | "incremental" = "full") =>
      api
        .post<{ data: { job_id: string; mode: string; status: string } }>(
          `/connections/${connectionId}/discover`,
          { mode }
        )
        .then((r) => r.data.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog-tables"] });
    },
  });
}

export function useDiscoveryStatus(
  connectionId: string,
  jobId: string | null,
  enabled: boolean
) {
  return useQuery<DiscoveryJobStatus>({
    queryKey: ["discovery-status", jobId],
    queryFn: () =>
      api
        .get<{ data: DiscoveryJobStatus }>(
          `/connections/${connectionId}/discover/status`,
          { params: { job_id: jobId } }
        )
        .then((r) => r.data.data),
    enabled: enabled && !!jobId,
    refetchInterval: (query) => {
      const stage = query.state.data?.stage;
      return stage === "done" || stage === "error" ? false : 2000;
    },
  });
}

export function useCatalogTables(params: CatalogListParams = {}) {
  return useQuery<{ data: CatalogTable[]; total: number; page: number; page_size: number }>({
    queryKey: ["catalog-tables", params],
    queryFn: () =>
      api
        .get("/catalog/tables", { params })
        .then((r) => r.data),
  });
}

export function useCatalogTable(tableId: string | null) {
  return useQuery<CatalogTableDetail>({
    queryKey: ["catalog-table", tableId],
    queryFn: () =>
      api
        .get<{ data: CatalogTableDetail }>(`/catalog/tables/${tableId}`)
        .then((r) => r.data.data),
    enabled: !!tableId,
  });
}

export function usePatchCatalogTable(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { ai_description?: string; is_pii_flagged?: boolean }) =>
      api
        .patch<{ data: CatalogTable }>(`/catalog/tables/${tableId}`, patch)
        .then((r) => r.data.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog-tables"] });
      qc.invalidateQueries({ queryKey: ["catalog-table", tableId] });
    },
  });
}
