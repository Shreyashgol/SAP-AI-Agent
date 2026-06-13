import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Document {
  id: string;
  tenant_id: string;
  uploaded_by: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: "pending" | "processing" | "ready" | "error";
  chunk_count: number;
  page_count: number | null;
  document_type: string | null;
  department: string | null;
  linked_entity_ids: string[] | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export function useDocuments(statusFilter?: string) {
  const params = statusFilter ? `?status_filter=${statusFilter}` : "";
  return useQuery<Document[]>({
    queryKey: ["documents", statusFilter],
    queryFn: () => apiClient.get(`/documents${params}`).then((r) => r.data),
  });
}

export function useDocument(id: string | null) {
  return useQuery<Document>({
    queryKey: ["documents", id],
    queryFn: () => apiClient.get(`/documents/${id}`).then((r) => r.data),
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation<
    Document,
    Error,
    { file: File; document_type?: string; department?: string }
  >({
    mutationFn: ({ file, document_type, department }) => {
      const form = new FormData();
      form.append("file", file);
      if (document_type) form.append("document_type", document_type);
      if (department) form.append("department", department);
      return apiClient
        .post("/documents/upload", form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/documents/${id}`).then(() => undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useReprocessDocument() {
  const qc = useQueryClient();
  return useMutation<Document, Error, string>({
    mutationFn: (id) =>
      apiClient.post(`/documents/${id}/reprocess`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function usePatchDocument() {
  const qc = useQueryClient();
  return useMutation<
    Document,
    Error,
    { id: string; document_type?: string; department?: string }
  >({
    mutationFn: ({ id, ...body }) =>
      apiClient.patch(`/documents/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}
