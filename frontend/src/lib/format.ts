/** Indian digit grouping: 123456.78 -> "₹1,23,456.78". Mirrors backend app/core/formatting.py. */
export function formatINR(amount: number | null | undefined, decimals = 2): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
}

/** "09 Oct 2026, 3:30 PM IST" */
export function formatFreshness(date: Date): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")} ${get("month")} ${get("year")}, ${get("hour")}:${get("minute")} ${get("dayPeriod").toUpperCase()} IST`;
}

/** "2026-10-09" -> "09 Oct 2026" (dates are calendar dates; no timezone shift). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "—";
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1];
  return `${String(d).padStart(2, "0")} ${month} ${y}`;
}

/** Index levels and other non-rupee numbers, with Indian grouping: 22520.45 -> "22,520.45". */
export function formatNumber(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** +1.2% / −0.7% (one decimal by default). Uses a true minus sign. */
export function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Number(Math.abs(value).toFixed(decimals));
  const sign = rounded === 0 ? "" : value > 0 ? "+" : "−";
  return `${sign}${rounded.toFixed(decimals)}%`;
}

const LAKH = 1e5;
const CRORE = 1e7;

/** Short rupee amounts for cards and hero figures: ₹45,230 · ₹12.4 L · ₹3.2 Cr · ₹15,83,705 Cr.
 * `signed` adds "+" to gains; losses always get "−". Use formatINR where the exact amount matters. */
export function formatINRCompact(amount: number | null | undefined, { signed = false } = {}): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  const abs = Math.abs(amount);
  const group = (v: number, d: number) =>
    new Intl.NumberFormat("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  let body: string;
  if (abs >= 100 * CRORE) body = `₹${group(abs / CRORE, 0)} Cr`;
  else if (abs >= CRORE) body = `₹${group(abs / CRORE, 1)} Cr`;
  else if (abs >= LAKH) body = `₹${group(abs / LAKH, 1)} L`;
  else body = `₹${group(Math.round(abs), 0)}`;
  // "₹100.0 L" reads oddly; it rounds up into crore.
  body = body.replace("₹100.0 L", "₹1.0 Cr");
  const sign = amount < 0 && body !== "₹0" ? "−" : signed && amount > 0 ? "+" : "";
  return `${sign}${body}`;
}
