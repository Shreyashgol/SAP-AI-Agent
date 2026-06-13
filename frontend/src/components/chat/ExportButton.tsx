import { Download } from "lucide-react";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Props {
  conversationId: string;
  turnId: string;
}

type Format = "csv" | "xlsx";

export default function ExportButton({ conversationId, turnId }: Props) {
  const [loading, setLoading] = useState<Format | null>(null);

  async function download(format: Format) {
    setLoading(format);
    try {
      const response = await apiClient.get(
        `/conversations/${conversationId}/turns/${turnId}/export`,
        { params: { format }, responseType: "blob" }
      );
      const blob = new Blob([response.data as BlobPart]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `export_${turnId.slice(0, 8)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silently fail — no tabular data for this turn
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => download("csv")}
        disabled={loading !== null}
        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 disabled:opacity-40 transition-colors"
        title="Download CSV"
      >
        <Download className="w-3 h-3" />
        {loading === "csv" ? "…" : "CSV"}
      </button>
      <span className="text-gray-200">|</span>
      <button
        onClick={() => download("xlsx")}
        disabled={loading !== null}
        className="text-xs text-gray-400 hover:text-gray-600 disabled:opacity-40 transition-colors"
        title="Download Excel"
      >
        {loading === "xlsx" ? "…" : "XLSX"}
      </button>
    </div>
  );
}
