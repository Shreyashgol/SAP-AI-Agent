import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

/** Button that flips the global light/dark theme. */
export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      onClick={toggle}
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="flex items-center gap-3 w-full px-2 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white transition-colors"
    >
      {dark ? <Sun className="h-5 w-5 shrink-0" /> : <Moon className="h-5 w-5 shrink-0" />}
      <span className="hidden lg:block">{dark ? "Light mode" : "Dark mode"}</span>
    </button>
  );
}
