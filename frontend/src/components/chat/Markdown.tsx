import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders assistant message text as Markdown (GitHub-flavoured: bold, lists,
 * tables, links, code). Styled with Tailwind Typography (`prose`) tuned down to
 * chat size. Links open in a new tab. Used for conversational replies (which use
 * bold/bullets) and any Markdown the model returns.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:mt-3 prose-headings:mb-1.5 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-code:text-violet-600 dark:prose-code:text-violet-300 prose-code:before:content-[''] prose-code:after:content-[''] prose-a:text-blue-600 dark:prose-a:text-blue-400 text-gray-800 dark:text-gray-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
