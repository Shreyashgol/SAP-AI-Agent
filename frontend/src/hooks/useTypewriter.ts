import { useEffect, useState } from "react";

/**
 * Streaming-style "typewriter" reveal. When `enabled`, reveals `text` a few
 * characters per tick so a freshly-arrived assistant answer types itself out
 * (the backend returns the full response at once — there is no token stream yet,
 * so this is a client-side animation only). When disabled, the full text shows
 * immediately.
 *
 * The effect re-runs only when `text` or `enabled` change, so each fresh answer
 * animates once. It deliberately keeps no "already started" ref: under React
 * StrictMode the effect is mounted twice, and a guard that skipped the second
 * run would clear the interval without recreating it, freezing the reveal at
 * zero characters (a blank answer until the page is refreshed).
 */
export function useTypewriter(text: string, enabled: boolean): string {
  const [count, setCount] = useState(enabled ? 0 : text.length);

  useEffect(() => {
    if (!enabled) {
      setCount(text.length);
      return;
    }
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
