/* One plain-English sentence for each chart on the stock page, worked out from the same figures the
 * chart shows. Pure functions, so they're tested on their own (captions.test.ts). */
import type { FairValue, FinancialYear } from "../../api/client";
import { formatINR, formatNumber } from "../../lib/format";

type Year = Pick<FinancialYear, "fy" | "year_end"> & Partial<FinancialYear>;

/** ₹ crore amounts with Indian grouping ("₹3,98,000 Cr"), or the statement currency ("12,400 USD Cr"). */
export function crore(v: number, unit = "₹ Cr"): string {
  if (unit === "₹ Cr") return `${formatINR(v, 0)} Cr`;
  return `${formatNumber(v, 0)} ${unit}`;
}

const pct = (v: number, d = 1) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;
const times = (v: number) => `${v.toFixed(2)}×`;

/** Years in date order that have a value for `key`. */
export function series<K extends keyof FinancialYear>(years: Year[], key: K): { fy: string; value: number }[] {
  return [...years]
    .sort((a, b) => a.year_end.localeCompare(b.year_end))
    .flatMap((y) => (typeof y[key] === "number" ? [{ fy: y.fy, value: y[key] as number }] : []));
}

const span = (n: number) => `${n} year${n === 1 ? "" : "s"}`;

/** Compound yearly growth between two positive values over `n` years. */
export function cagr(first: number, last: number, n: number): number | null {
  if (first <= 0 || last <= 0 || n <= 0) return null;
  return ((last / first) ** (1 / n) - 1) * 100;
}

export function fairValueCaption(fv: FairValue | null, price: number | null): string {
  if (!fv) return "No fair-value estimate: it needs sector medians and a profit or book value for this company.";
  const p = formatINR(price ?? fv.price);
  // Nothing left at the sector's multiples once debt is paid: the gap is infinite (sent as null).
  if (fv.value <= 0 || fv.gap_pct === null)
    return `Price ${p} is far above the estimated fair value of ${formatINR(fv.value)}: at its sector's multiples the business is worth less than its debt.`;
  const gap = Math.abs(fv.gap_pct).toFixed(1);
  if (Math.abs(fv.gap_pct) < 1) return `Price ${p} is in line with the estimated fair value of ${formatINR(fv.value)}.`;
  return fv.gap_pct < 0
    ? `Price ${p} is ${gap}% below the estimated fair value of ${formatINR(fv.value)}: cheaper than its sector's multiples suggest.`
    : `Price ${p} is ${gap}% above the estimated fair value of ${formatINR(fv.value)}: dearer than its sector's multiples suggest.`;
}

export function peCaption(pe: number | null, sector: number | null, own: number | null): string {
  const times = (v: number) => `${v.toFixed(1)}×`;
  if (pe === null) return "No P/E: the company made a loss or its earnings aren't available.";
  const parts: string[] = [];
  if (sector !== null) parts.push(`${pe < sector ? "below" : "above"} the sector median of ${times(sector)}`);
  if (own !== null) parts.push(`${pe < own ? "below" : "above"} its own recent median of ${times(own)}`);
  return parts.length ? `P/E of ${times(pe)} is ${parts.join(" and ")}.` : `P/E is ${times(pe)}; there's no sector or own-history median to compare it with.`;
}

/** "Revenue grew from ₹X to ₹Y over 3 years (6.4% a year); profit grew 6.6% a year." */
export function growthCaption(years: Year[], unit = "₹ Cr"): string {
  const rev = series(years, "revenue");
  const ni = series(years, "net_income");
  if (rev.length < 2) return "Not enough yearly results to show growth.";
  const n = rev.length - 1;
  const r0 = rev[0]!.value;
  const r1 = rev[n]!.value;
  const g = cagr(r0, r1, n);
  let s = `Revenue ${r1 >= r0 ? "grew" : "fell"} from ${crore(r0, unit)} to ${crore(r1, unit)} over ${span(n)}${g !== null ? ` (${pct(g)} a year)` : ""}`;
  if (ni.length >= 2) {
    const m = ni.length - 1;
    const p = cagr(ni[0]!.value, ni[m]!.value, m);
    s += p !== null ? `; profit ${p >= 0 ? "grew" : "fell"} ${pct(Math.abs(p))} a year` : `; profit went from ${crore(ni[0]!.value, unit)} to ${crore(ni[m]!.value, unit)}`;
  }
  return `${s}.`;
}

/** Latest quarter against the same quarter a year earlier. */
export function quarterCaption(quarters: { label: string; period_end: string; revenue: number | null; net_income: number | null }[]): string {
  const sorted = [...quarters].sort((a, b) => a.period_end.localeCompare(b.period_end));
  const last = sorted.at(-1);
  if (!last) return "No quarterly results.";
  const yearAgo = sorted.find((q) => {
    const months = (Date.parse(last.period_end) - Date.parse(q.period_end)) / (30.44 * 86_400_000);
    return months > 10.5 && months < 13.5;
  });
  if (!yearAgo) return `Latest results: the ${last.label}. There's no quarter from a year earlier to compare with.`;
  const change = (a: number | null, b: number | null) => (a !== null && b !== null && b > 0 ? ((a - b) / b) * 100 : null);
  const r = change(last.revenue, yearAgo.revenue);
  const p = change(last.net_income, yearAgo.net_income);
  const bits = [r !== null && `revenue ${r >= 0 ? "up" : "down"} ${pct(Math.abs(r))}`, p !== null && `profit ${p >= 0 ? "up" : "down"} ${pct(Math.abs(p))}`].filter(Boolean);
  return bits.length ? `In the ${last.label}, ${bits.join(" and ")} on a year earlier.` : `Latest results: the ${last.label}.`;
}

export function marginCaption(years: Year[]): string {
  const m = series(years, "op_margin");
  const key = m.length >= 2 ? "Operating margin" : "Net margin";
  const s = m.length >= 2 ? m : series(years, "net_margin");
  if (s.length < 2) return "Not enough yearly results to show the margin trend.";
  const a = s[0]!.value;
  const b = s.at(-1)!.value;
  const d = b - a;
  const move = Math.abs(d) < 0.5 ? "held steady at about" : d > 0 ? `rose from ${pct(a)} to` : `fell from ${pct(a)} to`;
  return `${key} ${move} ${pct(b)} over ${span(s.length - 1)}.`;
}

export function roeCaption(years: Year[]): string {
  const s = series(years, "roe");
  if (s.length < 2) return "Not enough yearly results to show the ROE trend.";
  const a = s[0]!.value;
  const b = s.at(-1)!.value;
  const verdict = b >= 15 ? "a strong return" : b >= 10 ? "a moderate return" : "a weak return";
  return `ROE went from ${pct(a)} to ${pct(b)} over ${span(s.length - 1)}: ${verdict} on shareholders' money.`;
}

/** "Debt has fallen from 0.47× to 0.44× equity over 3 years." */
export function debtCaption(years: Year[], unit = "₹ Cr"): string {
  const de = series(years, "debt_equity");
  if (de.length >= 2) {
    const a = de[0]!.value;
    const b = de.at(-1)!.value;
    if (b < 0.05 && a < 0.05) return `Practically debt-free over ${span(de.length - 1)}.`;
    const move = Math.abs(b - a) < 0.02 ? `has held at about ${times(b)}` : b < a ? `has fallen from ${times(a)} to ${times(b)}` : `has risen from ${times(a)} to ${times(b)}`;
    return `Debt ${move} equity over ${span(de.length - 1)}.`;
  }
  const debt = series(years, "total_debt");
  if (debt.length >= 2) return `Debt went from ${crore(debt[0]!.value, unit)} to ${crore(debt.at(-1)!.value, unit)} over ${span(debt.length - 1)}.`;
  return "Not enough balance-sheet history to show the debt trend.";
}

export function dividendCaption(years: Year[], unit = "₹ Cr"): string {
  const d = series(years, "dividends_paid").filter((x) => x.value > 0);
  if (!d.length) return "No dividends paid in the years on record.";
  const payout = series(years, "payout_pct").at(-1);
  const growth = d.length >= 2 ? (d.at(-1)!.value >= d[0]!.value ? "rising" : "falling") : null;
  return `Paid ${crore(d.at(-1)!.value, unit)} in dividends in ${d.at(-1)!.fy}${growth ? `, ${growth} from ${crore(d[0]!.value, unit)} in ${d[0]!.fy}` : ""}${
    payout ? `; that's ${pct(payout.value, 0)} of profit` : ""
  }.`;
}

/** RSI zones as the app's thresholds define them. */
export function rsiZone(rsi: number, band: [number, number] = [45, 70], oversold = 30): string {
  if (rsi >= band[1]) return "overbought: the price may have run ahead";
  if (rsi >= band[0]) return "healthy: firm buying without overheating";
  if (rsi > oversold) return "weak: sellers have the upper hand";
  return "oversold: heavy selling, sometimes before a bounce";
}

export function ownershipCaption(promoter: number | null, change: number | null, pledge: number | null): string {
  if (promoter === null) return "No shareholding data. Upload Screener.in data in Import to see who owns the company.";
  let s = `Promoters own ${pct(promoter)}`;
  if (change !== null && Math.abs(change) >= 0.1) s += `, ${change > 0 ? "up" : "down"} ${Math.abs(change).toFixed(1)} pp`;
  if (pledge !== null) s += pledge > 0 ? `, with ${pct(pledge)} of their shares pledged` : `, with none of their shares pledged`;
  return `${s}.`;
}
