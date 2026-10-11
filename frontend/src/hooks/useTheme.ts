import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

/** `?theme=light|dark` previews a theme for this visit without saving it (screenshots, /dev/components). */
function urlTheme(): Theme | null {
  const t = new URLSearchParams(window.location.search).get("theme");
  return t === "light" || t === "dark" ? t : null;
}

/** The URL override, else the saved choice, else dark (the default). index.html applies the same
 * rule before React loads, so the page never flashes the wrong theme. */
export function initialTheme(): Theme {
  const fromUrl = urlTheme();
  if (fromUrl) return fromUrl;
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage unavailable; use the default
  }
  return "dark";
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [preview] = useState(() => urlTheme() !== null);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  const toggle = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      if (!preview) {
        try {
          localStorage.setItem("theme", next);
        } catch {
          // ignore
        }
      }
      return next;
    });
  return { theme, toggle };
}
