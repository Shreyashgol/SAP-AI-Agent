import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";

const API = "/knowledge-graph";

export interface KGNode {
  id: string;
  entity_id: string;
  node_label: string;
  domain: string | null;
  node_properties: Record<string, unknown> | null;
}

export interface KGEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  relation_name: string;
  edge_type: string;
  confidence: number;
  is_admin_confirmed: boolean;
  join_condition: string | null;
}

export interface TraversalStep {
  from_entity: string;
  to_entity: string;
  join_condition: string;
  confidence: number;
  edge_type: string;
}

export interface TraversalResult {
  found: boolean;
  hop_count: number;
  entity_chain: string[];
  join_sql: string | null;
  steps: TraversalStep[];
}

export function useKGNodes(connectionId?: string, domain?: string) {
  return useQuery({
    queryKey: ["kg-nodes", connectionId, domain],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (connectionId) params.connection_id = connectionId;
      if (domain) params.domain = domain;
      const { data } = await api.get<KGNode[]>(`${API}/nodes`, { params });
      return data;
    },
    staleTime: 60_000,
  });
}

export function useKGEdges(unconfirmedOnly = false) {
  return useQuery({
    queryKey: ["kg-edges", unconfirmedOnly],
    queryFn: async () => {
      const { data } = await api.get<KGEdge[]>(`${API}/edges`, {
        params: { unconfirmed_only: unconfirmedOnly },
      });
      return data;
    },
    staleTime: 60_000,
  });
}

export function useConfirmEdge(edgeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (confirmed: boolean) =>
      api.patch(`${API}/edges/${edgeId}/confirm`, { confirmed }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kg-edges"] });
    },
  });
}

export function useTriggerKGBuild(connectionId: string) {
  return useMutation({
    mutationFn: () => api.post(`${API}/connections/${connectionId}/build`),
  });
}

export function useTraverse(fromEntityId: string, toEntityId: string, enabled = false) {
  return useQuery({
    queryKey: ["kg-traverse", fromEntityId, toEntityId],
    queryFn: async () => {
      const { data } = await api.get<TraversalResult>(`${API}/traverse`, {
        params: { from_entity_id: fromEntityId, to_entity_id: toEntityId },
      });
      return data;
    },
    enabled: enabled && !!fromEntityId && !!toEntityId,
    staleTime: 30_000,
  });
}
