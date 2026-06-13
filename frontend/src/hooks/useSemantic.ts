import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface SemanticEntity {
  id: string;
  table_id: string;
  entity_name: string;
  domain: string;
  description: string | null;
  is_ai_generated: boolean;
  is_human_override: boolean;
  confidence: number;
  pack_source: string;
  semantic_version: number;
}

export interface SemanticAttribute {
  id: string;
  entity_id: string;
  column_id: string;
  attribute_name: string;
  display_name: string;
  semantic_type: string;
  description: string | null;
  is_human_override: boolean;
  is_ai_generated: boolean;
}

export interface KPI {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  formula: string | null;
  unit: string | null;
  aggregation_method: string;
  display_format: string | null;
  domain: string;
  is_active: boolean;
  is_system: boolean;
}

export interface GlossaryTerm {
  id: string;
  term: string;
  definition: string;
  domain: string | null;
  is_ai_generated: boolean;
  approved_by: string | null;
}

export interface BusinessRule {
  id: string;
  entity_id: string;
  rule_name: string;
  predicate_sql: string;
  description: string | null;
  is_default: boolean;
  is_system: boolean;
  pack_source: string;
}

// ── Entities ───────────────────────────────────────────────────────────────────

export function useEntities(params: {
  domain?: string;
  connection_id?: string;
  ai_only?: boolean;
  page?: number;
  page_size?: number;
} = {}) {
  return useQuery<{ data: SemanticEntity[]; total: number }>({
    queryKey: ["semantic-entities", params],
    queryFn: () => api.get("/semantic/entities", { params }).then((r) => r.data),
  });
}

export function usePatchEntity(entityId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { entity_name?: string; domain?: string; description?: string }) =>
      api.patch<{ data: SemanticEntity }>(`/semantic/entities/${entityId}`, patch).then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["semantic-entities"] }),
  });
}

export function usePatchAttribute(attrId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { display_name?: string; semantic_type?: string; description?: string }) =>
      api.patch(`/semantic/attributes/${attrId}`, patch).then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["semantic-entities"] }),
  });
}

// ── KPIs ───────────────────────────────────────────────────────────────────────

export function useKPIs(domain?: string) {
  return useQuery<{ data: KPI[]; total: number }>({
    queryKey: ["kpis", domain],
    queryFn: () =>
      api.get("/semantic/kpis", { params: { domain, active_only: true, page_size: 200 } })
         .then((r) => r.data),
  });
}

export function useSeedKPIs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/semantic/seed-kpis").then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kpis"] }),
  });
}

// ── Glossary ───────────────────────────────────────────────────────────────────

export function useGlossary(domain?: string) {
  return useQuery<{ data: GlossaryTerm[]; total: number }>({
    queryKey: ["glossary", domain],
    queryFn: () =>
      api.get("/semantic/glossary", { params: { domain, page_size: 200 } }).then((r) => r.data),
  });
}

export function useCreateGlossaryTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { term: string; definition: string; domain?: string }) =>
      api.post("/semantic/glossary", body).then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["glossary"] }),
  });
}

export function useDeleteGlossaryTerm(termId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete(`/semantic/glossary/${termId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["glossary"] }),
  });
}

// ── Pack / AI mapping ──────────────────────────────────────────────────────────

export function useApplyPack() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { connection_id: string; schema_name?: string }) =>
      api.post("/semantic/apply-pack", body).then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["semantic-entities"] }),
  });
}

export function useRunAIMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { connection_id: string; limit?: number }) =>
      api.post("/semantic/ai-map", body).then((r) => r.data.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["semantic-entities"] }),
  });
}
