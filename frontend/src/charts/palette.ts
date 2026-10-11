/** Chart colours for light and dark mode, mirroring styles/tokens.css (tokens.test.ts checks they match;
 * charts need literal colours, not CSS variables). Every series also has a text label in its legend,
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
  text: "#46516b",
  grid: "#e2e7f1",
  up: "#0b7a52",
  down: "#b8282e",
  neutral: "#4f5a72",
  stop: "#b8282e",
  target: "#0b7a52",
  support: "#3f7fd9",
  resistance: "#b87500",
  series: ["#5546d6", "#b87500", "#0e8f8a", "#c2417a", "#3f7fd9", "#6b8e23", "#d4553a", "#5b6680", "#0b8fb8", "#9a4fc4"],
};

const dark: Palette = {
  bg: "#111a2e",
  text: "#aeb9cf",
  grid: "#1e2b48",
  up: "#45d29a",
  down: "#ff8a8a",
  neutral: "#aeb9cf",
  stop: "#ff8a8a",
  target: "#45d29a",
  support: "#6aa7ff",
  resistance: "#f3be55",
  series: ["#8f82ff", "#f3be55", "#3fd0c9", "#f27fb0", "#6aa7ff", "#a5cf5a", "#ff8f6b", "#aeb9cf", "#45c4f0", "#c792ff"],
};

export const palette = (isDark: boolean): Palette => (isDark ? dark : light);

export const seriesColor = (p: Palette, i: number): string => p.series[i % p.series.length] ?? p.neutral;
