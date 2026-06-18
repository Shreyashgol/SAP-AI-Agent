import { useState, useRef } from "react";
import {
  Upload, FileText, Trash2, RefreshCw, CheckCircle,
  Clock, AlertCircle, Loader2, File,
} from "lucide-react";
import {
  useDocuments,
  useUploadDocument,
  useDeleteDocument,
  useReprocessDocument,
  type Document,
} from "@/hooks/useDocuments";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document["status"] }) {
  const cfg: Record<string, { icon: React.ReactNode; cls: string; label: string }> = {
    pending:    { icon: <Clock className="w-3 h-3" />,       cls: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300",   label: "Pending" },
    processing: { icon: <Loader2 className="w-3 h-3 animate-spin" />, cls: "bg-blue-100 text-blue-600 dark:text-blue-400", label: "Processing" },
    ready:      { icon: <CheckCircle className="w-3 h-3" />, cls: "bg-green-100 text-green-700 dark:text-green-300", label: "Ready" },
    error:      { icon: <AlertCircle className="w-3 h-3" />, cls: "bg-red-100 text-red-600 dark:text-red-400",     label: "Error" },
  };
  const { icon, cls, label } = cfg[status] ?? cfg.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {icon}{label}
    </span>
  );
}

// ── File type icon ────────────────────────────────────────────────────────────

function FileTypeIcon({ type }: { type: string }) {
  const colors: Record<string, string> = {
    pdf: "text-red-500", docx: "text-blue-600 dark:text-blue-400",
    txt: "text-gray-500 dark:text-gray-400", md: "text-purple-500", markdown: "text-purple-500",
  };
  return <File className={`w-5 h-5 ${colors[type] ?? "text-gray-400 dark:text-gray-500"}`} />;
}

// ── Format bytes ──────────────────────────────────────────────────────────────

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Upload zone ───────────────────────────────────────────────────────────────

function UploadZone() {
  const [dragging, setDragging] = useState(false);
  const [docType, setDocType] = useState("");
  const [dept, setDept] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();

  function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    Array.from(files).forEach((file) =>
      upload.mutate({
        file,
        document_type: docType || undefined,
        department: dept || undefined,
      })
    );
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-6 bg-white dark:bg-gray-800 space-y-4">
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Upload documents</h2>

      {/* Metadata row */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Document type (optional)"
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          className="flex-1 text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          type="text"
          placeholder="Department (optional)"
          value={dept}
          onChange={(e) => setDept(e.target.value)}
          className="flex-1 text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragging ? "border-blue-400 bg-blue-50 dark:bg-blue-950/40" : "border-gray-200 dark:border-gray-700 hover:border-blue-300 hover:bg-gray-50 dark:hover:bg-gray-800"
        }`}
      >
        <Upload className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Drag & drop files or <span className="text-blue-600 dark:text-blue-400 font-medium">browse</span>
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">PDF, DOCX, TXT, MD — max 50 MB</p>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {upload.isPending && (
        <p className="text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" /> Uploading…
        </p>
      )}
      {upload.isError && (
        <p className="text-xs text-red-600 dark:text-red-400">{upload.error?.message}</p>
      )}
    </div>
  );
}

// ── Document row ──────────────────────────────────────────────────────────────

function DocRow({ doc }: { doc: Document }) {
  const deleteDoc = useDeleteDocument();
  const reprocess = useReprocessDocument();

  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <FileTypeIcon type={doc.file_type} />
          <div>
            <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate max-w-xs">{doc.filename}</p>
            <p className="text-xs text-gray-400 dark:text-gray-500">{formatBytes(doc.file_size_bytes)}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={doc.status} />
        {doc.status === "error" && doc.error_message && (
          <p className="text-xs text-red-500 mt-1 max-w-xs truncate" title={doc.error_message}>
            {doc.error_message}
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
        {doc.chunk_count > 0 ? `${doc.chunk_count} chunks` : "—"}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        {doc.document_type || "—"}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        {doc.department || "—"}
      </td>
      <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">
        {new Date(doc.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          {(doc.status === "error" || doc.status === "pending") && (
            <button
              onClick={() => reprocess.mutate(doc.id)}
              disabled={reprocess.isPending}
              className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded"
              title="Reprocess"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => {
              if (confirm(`Delete "${doc.filename}"?`)) deleteDoc.mutate(doc.id);
            }}
            disabled={deleteDoc.isPending}
            className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 rounded"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const [filter, setFilter] = useState<string | undefined>();
  const { data: docs, isLoading } = useDocuments(filter);

  const statuses = [
    { label: "All", value: undefined },
    { label: "Ready", value: "ready" },
    { label: "Processing", value: "processing" },
    { label: "Error", value: "error" },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Documents</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Upload documents to enable document-based Q&amp;A via RAG.
          </p>
        </div>
      </div>

      <UploadZone />

      {/* Filter tabs */}
      <div className="flex gap-2">
        {statuses.map(({ label, value }) => (
          <button
            key={label}
            onClick={() => setFilter(value)}
            className={`px-3 py-1.5 text-sm rounded-lg ${
              filter === value
                ? "bg-blue-600 text-white"
                : "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Document table */}
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-gray-300 dark:text-gray-600 animate-spin" />
          </div>
        ) : !docs?.length ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <FileText className="w-12 h-12 text-gray-200 mb-3" />
            <p className="text-gray-500 dark:text-gray-400 text-sm">No documents yet.</p>
            <p className="text-gray-400 dark:text-gray-500 text-xs mt-1">Upload a file above to get started.</p>
          </div>
        ) : (
          <table className="min-w-full">
            <thead className="bg-gray-50 dark:bg-gray-800/60 border-b border-gray-200 dark:border-gray-700">
              <tr>
                {["File", "Status", "Chunks", "Type", "Department", "Uploaded", "Actions"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {docs.map((doc) => (
                <DocRow key={doc.id} doc={doc} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
