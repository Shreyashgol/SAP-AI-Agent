import { ensureAuth, getToken, getTenant } from "@/lib/api";
import type { AskResponse } from "@/hooks/useConversations";

export interface ReasoningStep {
  node: string;
  label: string;
  intent?: string | null;
}

export interface StreamCallbacks {
  onStep: (step: ReasoningStep) => void;
  onFinal: (data: AskResponse) => void;
}

/**
 * POST a question to the streaming ask endpoint and surface the agent's live
 * reasoning. The response body is newline-delimited JSON: `{"type":"step",...}`
 * objects as the agent thinks, then a final `{"type":"final","data":...}`.
 *
 * Uses fetch (not axios) because we need to read the streamed body; auth/tenant
 * headers mirror the axios client. Throws on a non-OK response so callers can
 * fall back to the non-streaming mutation.
 */
export async function askStream(
  conversationId: string,
  question: string,
  connectionId: string | null,
  cb: StreamCallbacks,
): Promise<void> {
  await ensureAuth();
  const res = await fetch(`/api/v1/conversations/${conversationId}/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-ID": getTenant(),
      Authorization: `Bearer ${getToken() ?? ""}`,
    },
    body: JSON.stringify({ question, connection_id: connectionId ?? undefined }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`stream request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      let msg: { type: string; data?: AskResponse } & ReasoningStep;
      try {
        msg = JSON.parse(line);
      } catch {
        continue;
      }
      if (msg.type === "step") {
        cb.onStep({ node: msg.node, label: msg.label, intent: msg.intent });
      } else if (msg.type === "final" && msg.data) {
        cb.onFinal(msg.data);
      }
    }
  }
}
