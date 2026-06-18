import { Brain } from "lucide-react";
import type { ReasoningStep } from "@/hooks/useAskStream";

/**
 * Live reasoning trace shown WHILE the agent is thinking — each step appears as
 * the corresponding graph node finishes (streamed from the backend). The most
 * recent step pulses to signal work in progress.
 */
export default function LiveReasoning({ steps }: { steps: ReasoningStep[] }) {
  return (
    <div className="border border-violet-100 dark:border-violet-900/50 rounded-lg overflow-hidden bg-violet-50/40 dark:bg-violet-950/20">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-violet-600 dark:text-violet-300">
        <Brain className="w-3.5 h-3.5 animate-pulse" />
        Thinking…
      </div>
      <ol className="px-3 pb-3 space-y-1.5">
        {steps.map((s, i) => {
          const isLast = i === steps.length - 1;
          return (
            <li key={i} className="flex gap-2 text-xs text-gray-700 dark:text-gray-300">
              <span
                className={`shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-medium mt-0.5 ${
                  isLast
                    ? "bg-violet-500 text-white animate-pulse"
                    : "bg-violet-100 dark:bg-violet-900/50 text-violet-600 dark:text-violet-300"
                }`}
              >
                {i + 1}
              </span>
              <span className="min-w-0">{s.label}</span>
            </li>
          );
        })}
        {steps.length === 0 && (
          <li className="text-xs text-gray-400 dark:text-gray-500 pl-6">Getting started…</li>
        )}
      </ol>
    </div>
  );
}
