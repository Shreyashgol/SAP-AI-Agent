import { useEffect, useRef, useState } from "react";

/**
 * Streaming-style "typewriter" reveal. When `enabled`, reveals `text` a few
 * characters per tick so a freshly-arrived assistant answer types itself out
 * (the backend returns the full response at once — there is no token stream yet,
 * so this is a client-side animation only). When disabled, the full text shows
 * immediately. Runs once per text value.
 */
export function useTypewriter(text: string, enabled: boolean): string {
  const [count, setCount] = useState(enabled ? 0 : text.length);
  const startedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setCount(text.length);
      return;
    }
    // Only (re)start the animation when the target text actually changes.
    if (startedFor.current === text) return;
    startedFor.current = text;
    setCount(0);

    // Reveal faster for long answers so it never feels sluggish.
    const step = Math.max(1, Math.round(text.length / 160));
    const id = setInterval(() => {
      setCount((c) => {
        const next = c + step;
        if (next >= text.length) {
          clearInterval(id);
          return text.length;
        }
        return next;
      });
    }, 16);
    return () => clearInterval(id);
  }, [text, enabled]);

  return text.slice(0, count);
}
