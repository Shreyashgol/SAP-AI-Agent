import { useState } from "react";
import { ChevronDown, ChevronRight, Database, FileText } from "lucide-react";

interface LineageChunk {
  label: string;
  chunk_id?: string;
  document_id?: string;
  similarity?: number;
  page_number?: number;
  section_title?: string;
}

interface LineageData {
  tool_id?: string;
  tool_name?: string;
  query_id?: string;
  rag_chunks?: LineageChunk[];
  hybrid_docs?: LineageChunk[];
  [key: string]: unknown;
}

interface Props {
  lineage: LineageData;
}

export default function LineagePanel({ lineage }: Props) {
  const [open, setOpen] = useState(false);

  const hasRag = lineage.rag_chunks && lineage.rag_chunks.length > 0;
  const hasHybrid = lineage.hybrid_docs && lineage.hybrid_docs.length > 0;
  const hasTool = Boolean(lineage.tool_name || lineage.tool_id);

  if (!hasRag && !hasHybrid && !hasTool) return null;

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:bg-gray-50 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5" />
        )}
        <span className="font-medium">Sources</span>
        {hasTool && (
          <span className="flex items-center gap-1 text-gray-400">
            <Database className="w-3 h-3" />
            {lineage.tool_name ?? "SQL"}
          </span>
        )}
        {(hasRag || hasHybrid) && (
          <span className="flex items-center gap-1 text-gray-400">
            <FileText className="w-3 h-3" />
            {(lineage.rag_chunks?.length ?? 0) +
              (lineage.hybrid_docs?.length ?? 0)}{" "}
            doc chunk{((lineage.rag_chunks?.length ?? 0) + (lineage.hybrid_docs?.length ?? 0)) !== 1 ? "s" : ""}
          </span>
        )}
      </button>

      {open && (
        <div className="border-t border-gray-100 px-3 py-2 space-y-2 bg-gray-50">
          {hasTool && (
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <Database className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span>
                <span className="font-medium">Tool:</span>{" "}
                {lineage.tool_name ?? lineage.tool_id ?? "unknown"}
              </span>
            </div>
          )}

          {[...(lineage.rag_chunks ?? []), ...(lineage.hybrid_docs ?? [])].map(
            (chunk, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-600">
                <FileText className="w-3.5 h-3.5 text-violet-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium">{chunk.label}</span>
                  {chunk.section_title && (
                    <span className="text-gray-400"> — {chunk.section_title}</span>
                  )}
                  {chunk.page_number != null && (
                    <span className="text-gray-400"> p.{chunk.page_number}</span>
                  )}
                  {chunk.similarity != null && (
                    <span className="ml-2 text-gray-400">
                      {Math.round(chunk.similarity * 100)}% match
                    </span>
                  )}
                </div>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
