/** Chart colours for light and dark mode. Every series also has a text label in its legend,
 * so nothing is told by colour alone. */
export interface Palette {
  bg: string;
  text: string;
  grid: string;
  up: string;
  down: string;
  neutral: string;
  stop: string;
  target: string;
  support: string;
  resistance: string;
  series: string[];
}

const light: Palette = {
  bg: "#ffffff",
  text: "#334155",
  grid: "#e2e8f0",
  up: "#059669",
  down: "#dc2626",
  neutral: "#64748b",
  stop: "#dc2626",
  target: "#059669",
  support: "#0284c7",
  resistance: "#d97706",
  series: ["#2563eb", "#d97706", "#7c3aed", "#0d9488", "#db2777", "#65a30d", "#ea580c", "#475569", "#0891b2", "#9333ea"],
};

const dark: Palette = {
  bg: "#0f172a",
  text: "#cbd5e1",
  grid: "#1e293b",
  up: "#34d399",
  down: "#f87171",
  neutral: "#94a3b8",
  stop: "#f87171",
  target: "#34d399",
  support: "#38bdf8",
  resistance: "#fbbf24",
  series: ["#60a5fa", "#fbbf24", "#a78bfa", "#2dd4bf", "#f472b6", "#a3e635", "#fb923c", "#94a3b8", "#22d3ee", "#c084fc"],
};

export const palette = (isDark: boolean): Palette => (isDark ? dark : light);

export const seriesColor = (p: Palette, i: number): string => p.series[i % p.series.length] ?? p.neutral;
