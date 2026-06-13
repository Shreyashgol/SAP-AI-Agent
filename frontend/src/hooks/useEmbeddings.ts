import { useMutation, useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = "/api/v1/embeddings";

export interface ToolSearchResult {
  tool_id: string;
  tool_name: string;
  description: string | null;
  domain: string;
  category: string;
  similarity: number;
}

export interface EntitySearchResult {
  entity_id: string;
  entity_name: string;
  domain: string;
  similarity: number;
}

export interface RankedToolResult {
  tool_id: string;
  tool_name: string;
  description: string | null;
  domain: string;
  category: string;
  final_score: number;
  semantic_similarity: number;
  success_rate: number;
  feedback_weight: number;
}

export function useSemanticToolSearch(query: string, domain?: string, enabled = false) {
  return useQuery({
    queryKey: ["semantic-tool-search", query, domain],
    queryFn: async () => {
      const { data } = await axios.get<ToolSearchResult[]>(`${API}/search/tools`, {
        params: { q: query, domain, top_k: 10 },
      });
      return data;
    },
    enabled: enabled && query.length >= 2,
    staleTime: 30_000,
  });
}

export function useSemanticEntitySearch(query: string, enabled = false) {
  return useQuery({
    queryKey: ["semantic-entity-search", query],
    queryFn: async () => {
      const { data } = await axios.get<EntitySearchResult[]>(`${API}/search/entities`, {
        params: { q: query, top_k: 10 },
      });
      return data;
    },
    enabled: enabled && query.length >= 2,
    staleTime: 30_000,
  });
}

export function useRankedTools(query: string, domain?: string, enabled = false) {
  return useQuery({
    queryKey: ["ranked-tools", query, domain],
    queryFn: async () => {
      const { data } = await axios.get<RankedToolResult[]>("/api/v1/tools/rank", {
        params: { q: query, domain, top_k: 5 },
      });
      return data;
    },
    enabled: enabled && query.length >= 2,
    staleTime: 30_000,
  });
}

export function useTriggerEmbedTools() {
  return useMutation({
    mutationFn: (force: boolean) =>
      axios.post(`${API}/tools`, null, { params: { force } }),
  });
}

export function useTriggerEmbedEntities() {
  return useMutation({
    mutationFn: (force: boolean) =>
      axios.post(`${API}/entities`, null, { params: { force } }),
  });
}

export function useCustomBuildTool() {
  return useMutation({
    mutationFn: (body: { description: string; context_tables?: string[] }) =>
      axios.post("/api/v1/tools/custom-build", body),
  });
}
