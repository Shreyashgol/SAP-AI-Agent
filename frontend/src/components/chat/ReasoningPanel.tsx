import { useState } from "react";
import { ChevronDown, ChevronRight, Brain } from "lucide-react";
import Markdown from "./Markdown";

interface Candidate {
  name?: string;
  score?: number;
  domain?: string;
}

interface Props {
  lineage: Record<string, unknown> | null;
  intent?: string | null;
  confidence?: number | null;
}

/**
 * Collapsible "Reasoning" panel — shows how the agent reached its answer:
 * the step-by-step trace, detected intent + confidence, the tables queried, and
 * the tools it considered. Data comes from the turn's lineage (built by the
 * response formatter).
 */
export default function ReasoningPanel({ lineage, intent, confidence }: Props) {
  const [open, setOpen] = useState(false);

  const steps = (lineage?.reasoning as string[] | undefined) ?? [];
  const candidates = (lineage?.candidate_tools as Candidate[] | undefined) ?? [];
  const tables = (lineage?.tables_used as string[] | undefined) ?? [];
  const resolvedIntent = intent ?? (lineage?.intent as string | undefined) ?? null;

  if (steps.length === 0 && candidates.length === 0 && !resolvedIntent) return null;

  return (
    <div className="border border-gray-100 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Brain className="w-3.5 h-3.5 text-violet-500" />
        <span className="font-medium">Reasoning</span>
        {resolvedIntent && (
          <span className="text-gray-400 dark:text-gray-500">· {resolvedIntent}</span>
        )}
        {confidence != null && (
          <span className="text-gray-400 dark:text-gray-500">
            · {Math.round(confidence * 100)}% confident
          </span>
        )}
      </button>

      {open && (
        <div className="border-t border-gray-100 dark:border-gray-700 px-3 py-3 space-y-3 bg-gray-50 dark:bg-gray-800/50">
          {steps.length > 0 && (
            <ol className="space-y-1.5">
              {steps.map((s, i) => (
                <li key={i} className="flex gap-2 text-xs text-gray-700 dark:text-gray-300">
                  <span className="shrink-0 w-4 h-4 rounded-full bg-violet-100 dark:bg-violet-900/50 text-violet-600 dark:text-violet-300 flex items-center justify-center text-[10px] font-medium mt-0.5">
                    {i + 1}
                  </span>
                  <div className="min-w-0 [&_p]:!my-0 [&_*]:!text-xs">
                    <Markdown>{s}</Markdown>
                  </div>
                </li>
              ))}
            </ol>
          )}

          {tables.length > 0 && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              <span className="font-medium">Tables queried:</span> {tables.join(", ")}
            </div>
          )}

          {candidates.length > 0 && (
            <div className="text-xs">
              <p className="font-medium text-gray-500 dark:text-gray-400 mb-1">Tools considered</p>
              <div className="space-y-1">
                {candidates.slice(0, 5).map((c, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between text-gray-600 dark:text-gray-300"
                  >
                    <span className="truncate">{c.name}</span>
                    {c.score != null && (
                      <span className="ml-2 text-gray-400 dark:text-gray-500">
                        {Math.round((c.score as number) * 100) / 100}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
