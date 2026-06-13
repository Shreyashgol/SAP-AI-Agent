// ── API envelope types ────────────────────────────────────────────────────────
export interface APIResponse<T> {
  success: boolean;
  data: T | null;
  message?: string;
  request_id?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Conversation ──────────────────────────────────────────────────────────────
export type IntentType =
  | "Lookup"
  | "Aggregation"
  | "Trend"
  | "Comparative"
  | "RCA"
  | "Document"
  | "Hybrid"
  | "Web";

export type ChartHint =
  | "bar"
  | "line"
  | "area"
  | "donut"
  | "waterfall"
  | "kpi_card"
  | "table";

export type StreamEventType =
  | "agent_thinking"
  | "partial"
  | "complete"
  | "error";

export interface ConversationTurn {
  id: string;
  turn_number: number;
  question: string;
  answer_text: string | null;
  answer_data: AnswerData | null;
  intent: IntentType | null;
  confidence_score: number | null;
  lineage: Lineage | null;
  follow_up_questions: string[] | null;
  chart_hint: ChartHint | null;
  execution_time_ms: number | null;
  created_at: string;
}

export interface AnswerData {
  rows: Record<string, unknown>[];
  columns: string[];
  kpi_values?: Record<string, number | string>;
}

export interface Lineage {
  source_db: string;
  tables_used: string[];
  tool_id?: string;
  sql_query?: string;
  documents_cited?: DocumentCitation[];
  agents_invoked: string[];
}

export interface DocumentCitation {
  document_name: string;
  page_number: number;
  section: string;
  excerpt_preview: string;
}
