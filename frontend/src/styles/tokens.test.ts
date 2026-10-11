import { describe, expect, it } from "vitest";
import { palette } from "../charts/palette";
import indexCss from "../index.css?raw";
import css from "./tokens.css?raw";

/** `--name: #hex;` declarations inside the first block that opens with `selector {`. */
function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1]!, m[2]!.toLowerCase()]));
}

const light = block(":root,\n.light");
const dark = { ...light, ...block(".dark") };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

/** Body text on every surface it can sit on: AA (4.5:1). */
const TEXT = ["fg", "fg-muted", "fg-subtle", "accent-text", "good", "caution", "bad", "neutral"];
const SURFACES = ["bg", "surface", "surface-2"];
/** Semantic text on its own soft badge background. */
const ON_SOFT: [string, string][] = [
  ["good", "good-soft"],
  ["caution", "caution-soft"],
  ["bad", "bad-soft"],
  ["neutral", "neutral-soft"],
  ["accent-text", "accent-soft"],
  // Solid signal pills (Strong Buy, Sell, Switch): surface-coloured text on the semantic colour.
  ["surface", "good"],
  ["surface", "bad"],
];
/** Graphics (shape fills, chart lines, focus ring): 3:1 against the surface (WCAG 1.4.11). */
const GRAPHICS = ["score-1", "score-2", "score-3", "score-4", "score-5", "chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-6", "chart-up", "chart-down", "focus", "border-strong"];

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme tokens", (_name, t) => {
  it.each(TEXT.flatMap((fg) => SURFACES.map((bg) => [fg, bg])))("%s on %s passes AA", (fg, bg) => {
    expect(contrast(t[fg]!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(ON_SOFT)("%s on %s passes AA", (fg, bg) => {
    expect(contrast(t[fg]!, t[bg]!)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(GRAPHICS)("%s is visible on the surface (3:1)", (g) => {
    expect(contrast(t[g]!, t.surface!)).toBeGreaterThanOrEqual(3);
  });

  it("accent buttons are readable", () => {
    expect(contrast(t["accent-fg"]!, t.accent!)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("legacy slate-500 text (used without a dark variant)", () => {
  const ramp = (re: RegExp) => indexCss.match(re)?.[1]?.toLowerCase() ?? "";
  it("passes AA on light surfaces and, via the .dark override, on dark ones", () => {
    const lightSlate = ramp(/--color-slate-500:\s*(#[0-9a-f]{6})/i);
    for (const bg of ["bg", "surface", "surface-2"]) expect(contrast(lightSlate, light[bg]!)).toBeGreaterThanOrEqual(4.5);
    const darkSlate = block(".dark")["color-slate-500"]!;
    for (const bg of ["bg", "surface", "surface-2"]) expect(contrast(darkSlate, dark[bg]!)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("chart palette mirrors the tokens", () => {
  it.each([
    ["light", false, light],
    ["dark", true, dark],
  ] as const)("%s", (_n, isDark, t) => {
    const p = palette(isDark);
    expect(p.bg).toBe(t.surface);
    expect(p.text).toBe(t["chart-axis"]);
    expect(p.grid).toBe(t["chart-grid"]);
    expect(p.up).toBe(t["chart-up"]);
    expect(p.down).toBe(t["chart-down"]);
    expect(p.series.slice(0, 6)).toEqual([1, 2, 3, 4, 5, 6].map((i) => t[`chart-${i}`]));
  });
});
