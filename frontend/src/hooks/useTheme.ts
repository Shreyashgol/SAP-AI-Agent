import { create } from "zustand";

export type Theme = "light" | "dark";

function initialTheme(): Theme {
  if (typeof document !== "undefined" && document.documentElement.classList.contains("dark")) {
    return "dark";
  }
  return "light";
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem("theme", theme);
  } catch {
    /* localStorage unavailable */
  }
}

interface ThemeState {
  theme: Theme;
  toggle: () => void;
  setTheme: (t: Theme) => void;
}

/** Global light/dark theme. The initial value mirrors the class the inline
 * index.html script already set, so there is no flash on load. Toggling adds or
 * removes the `dark` class on <html> (Tailwind `darkMode: "class"`) and persists
 * the choice to localStorage. */
export const useTheme = create<ThemeState>((set, get) => ({
  theme: initialTheme(),
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    apply(next);
    set({ theme: next });
  },
  setTheme: (t) => {
    apply(t);
    set({ theme: t });
  },
}));
