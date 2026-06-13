import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Conversation {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  is_active: boolean;
  turn_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationTurn {
  id: string;
  conversation_id: string;
  turn_number: number;
  question: string;
  answer_text: string | null;
  answer_data: Record<string, unknown> | null;
  sql_query: string | null;
  chart_hint: string | null;
  follow_up_questions: string[] | null;
  lineage: Record<string, unknown> | null;
  confidence_score: number | null;
  execution_time_ms: number | null;
  agents_invoked: string[] | null;
  intent: string | null;
  created_at: string;
}

export interface AskResponse {
  turn_id: string;
  conversation_id: string;
  question: string;
  answer_text: string | null;
  answer_data: Record<string, unknown> | null;
  sql_query: string | null;
  chart_hint: string | null;
  follow_up_questions: string[];
  lineage: Record<string, unknown> | null;
  confidence_score: number | null;
  execution_time_ms: number | null;
  agents_invoked: string[];
  intent: string | null;
  has_error: boolean;
  error_message: string | null;
}

// ── List conversations ──────────────────────────────────────────────────────

export function useConversations(limit = 20, offset = 0) {
  return useQuery<Conversation[]>({
    queryKey: ["conversations", limit, offset],
    queryFn: () =>
      apiClient.get(`/conversations?limit=${limit}&offset=${offset}`).then((r) => r.data),
  });
}

// ── Single conversation ─────────────────────────────────────────────────────

export function useConversation(id: string | null) {
  return useQuery<Conversation>({
    queryKey: ["conversations", id],
    queryFn: () => apiClient.get(`/conversations/${id}`).then((r) => r.data),
    enabled: !!id,
  });
}

// ── Turns ───────────────────────────────────────────────────────────────────

export function useConversationTurns(conversationId: string | null) {
  return useQuery<ConversationTurn[]>({
    queryKey: ["conversations", conversationId, "turns"],
    queryFn: () =>
      apiClient.get(`/conversations/${conversationId}/turns`).then((r) => r.data),
    enabled: !!conversationId,
  });
}

// ── Create conversation ─────────────────────────────────────────────────────

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation<Conversation, Error, { title?: string; connection_id?: string }>({
    mutationFn: (body) => apiClient.post("/conversations", body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

// ── Delete conversation ─────────────────────────────────────────────────────

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/conversations/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

// ── Ask question ─────────────────────────────────────────────────────────────

export function useAsk(conversationId: string | null) {
  const qc = useQueryClient();
  return useMutation<AskResponse, Error, { question: string; connection_id?: string }>({
    mutationFn: (body) =>
      apiClient.post(`/conversations/${conversationId}/ask`, body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations", conversationId, "turns"] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
