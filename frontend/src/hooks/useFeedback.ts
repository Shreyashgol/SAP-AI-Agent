import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface FeedbackPayload {
  conversation_turn_id: string;
  tool_id?: string;
  rating: 1 | -1;
}

export interface CorrectionPayload {
  conversation_turn_id: string;
  correction_text: string;
}

export function useSubmitFeedback() {
  return useMutation<void, Error, FeedbackPayload>({
    mutationFn: (body) => apiClient.post("/feedback", body).then(() => undefined),
  });
}

export function useSubmitCorrection() {
  return useMutation<void, Error, CorrectionPayload>({
    mutationFn: (body) =>
      apiClient.post("/feedback/corrections", body).then(() => undefined),
  });
}
