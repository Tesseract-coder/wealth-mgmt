import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fundamentalApi, type Direction, type FundamentalReport, type Metric, type Observation } from "../api/client";
import { formatINR } from "../lib/format";
import { FreshnessBadge } from "./MarketData";
import { Alert, Card, ErrorState, SkeletonCard } from "./ui";

const DIR: Record<Direction, { label: string; icon: string; cls: string }> = {
  bullish: { label: "Positive", icon: "▲", cls: "text-good" },
  bearish: { label: "Negative", icon: "▼", cls: "text-bad" },
  neutral: { label: "Neutral", icon: "●", cls: "text-fg-subtle" },
};

const GROUPS: { title: string; keys: string[] }[] = [
  { title: "Valuation", keys: ["market_cap", "pe", "pb", "ev_ebitda", "peg", "dividend_yield"] },
  { title: "Profitability", keys: ["roe", "roce", "op_margin", "op_margin_change", "net_margin", "net_margin_change"] },
  {
    title: "Growth",
    keys: ["revenue_cagr_3y", "profit_cagr_3y", "revenue_cagr_5y", "profit_cagr_5y", "revenue_qoq_yoy", "profit_qoq_yoy", "forward_growth"],
  },
  {
    title: "Financial health",
    keys: ["debt_equity", "interest_coverage", "current_ratio", "fcf", "fcf_positive_years", "consecutive_loss_years", "debt_change"],
  },
  {
    title: "Ownership (Screener.in)",
    keys: ["promoter_pct", "promoter_change", "pledge_pct", "fii_pct", "fii_change", "dii_pct", "dii_change"],
  },
];

export function formatMetric(m: Pick<Metric, "value" | "unit">): string {
  if (m.value === null) return "—";
  switch (m.unit) {
    case "₹ Cr":
      return `${formatINR(m.value, 0)} Cr`;
    case "%":
      return `${m.value.toFixed(1)}%`;
    case "pp":
      return `${m.value > 0 ? "+" : m.value < 0 ? "−" : ""}${Math.abs(m.value).toFixed(1)} pp`;
    case "x":
      return `${m.value.toFixed(2)}×`;
    default:
      return Number.isInteger(m.value) ? String(m.value) : m.value.toFixed(2);
  }
}

export function FundamentalReportView({ ticker, metricsOnly = false, enabled = true }: { ticker: string; metricsOnly?: boolean; enabled?: boolean }) {
  const q = useQuery({ queryKey: ["fundamental", ticker], queryFn: () => fundamentalApi.report(ticker), enabled });
  if (q.isError) return <ErrorState title="Couldn't load the fundamentals" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label={`fundamentals for ${ticker} (the first look downloads them from Yahoo Finance)`} lines={6} />;
  return <FundamentalBody r={q.data} metricsOnly={metricsOnly} />;
}

export function FundamentalBody({ r, metricsOnly = false }: { r: FundamentalReport; metricsOnly?: boolean }) {
  const byKey = new Map(r.metrics.map((m) => [m.key, m]));
  return (
    <div className="space-y-4">
      {r.fetch_errors.map((e) => (
        <Alert key={e} tone="warning">
          Could not refresh: {e}. Showing cached data where available.
        </Alert>
      ))}
      <Card
        title={`Fundamentals${r.sector ? ` · ${r.sector}` : ""}`}
        actions={
          <span className="flex items-center gap-2 text-sm text-fg-subtle">
            {r.source === "screener" ? "Screener.in upload" : r.source === "yahoo" ? "Yahoo Finance" : "No statements"}
            {r.latest_year && ` · latest year ${r.latest_year.slice(0, 4)}`}
            <FreshnessBadge f={r.freshness} />
          </span>
        }
      >
        {r.notes.map((n) => (
          <p key={n} className={`mb-2 text-xs ${n.startsWith("Data check") ? "text-caution" : "text-fg-subtle"}`}>
            {n}
          </p>
        ))}
        <div className="grid gap-4 lg:grid-cols-2">
          {GROUPS.map((g) => {
            const rows = g.keys.map((k) => byKey.get(k)).filter((m): m is Metric => !!m);
            if (rows.length === 0) return null;
            return (
              <div key={g.title}>
                <h3 className="mb-1 text-sm font-semibold">{g.title}</h3>
                <table className="w-full text-sm">
                  <tbody>
                    {rows.map((m) => (
                      <tr key={m.key} className="border-t border-border align-top">
                        <td className="py-1 pr-2">{m.label}</td>
                        <td className="pr-2 text-right tabular-nums font-medium">{formatMetric(m)}</td>
                        <td className="pr-2 text-right text-xs text-fg-subtle tabular-nums">
                          {m.sector_median !== null ? `sector ${formatMetric({ value: m.sector_median, unit: m.unit })}` : ""}
                        </td>
                        <td className="text-xs text-fg-subtle">{m.basis}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      </Card>

      {!metricsOnly && r.fscore && (
        <Card title={`Piotroski F-score: ${r.fscore.score === null ? `not scored (${r.fscore.computable}/9 tests have data)` : `${r.fscore.score}/9`}`}>
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {r.fscore.tests.map((t) => (
              <li key={t.name}>
                <span className={t.passed === null ? "text-fg-subtle" : t.passed ? "text-good" : "text-bad"}>
                  {t.passed === null ? "– n/a" : t.passed ? "✓ pass" : "✗ fail"}
                </span>{" "}
                {t.name} <span className="text-xs text-fg-subtle">({t.detail})</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!metricsOnly && (
      <Card title="Readings">
        <Readings observations={r.observations} />
        {r.unavailable.length > 0 && (
          <div className="mt-3 text-xs text-fg-subtle">
            <span className="font-medium">Not available:</span> {r.unavailable.join("; ")}
          </div>
        )}
      </Card>
      )}
    </div>
  );
}

function Readings({ observations }: { observations: Observation[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {(["bullish", "bearish", "neutral"] as const).map((d) => {
        const items = observations.filter((o) => o.direction === d);
        const s = DIR[d];
        return (
          <div key={d}>
            <h3 className={`mb-1 text-sm font-semibold ${s.cls}`}>
              {s.icon} {s.label} ({items.length})
            </h3>
            <ul className="space-y-1 text-sm">
              {items.map((o) => (
                <li key={o.key}>
                  <span className="text-xs uppercase text-fg-subtle">{o.category}</span> {o.text}
                  {o.minor && <span className="ml-1 text-xs text-fg-subtle">(minor)</span>}
                </li>
              ))}
              {items.length === 0 && <li className="text-fg-subtle">None</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

export function FundamentalHoldings() {
  const q = useQuery({ queryKey: ["fund-holdings"], queryFn: fundamentalApi.holdings });
  if (q.isError) return <ErrorState title="Couldn't load your holdings' fundamentals" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label="your holdings' fundamentals" lines={6} />;
  if (q.data.length === 0)
    return (
      <Alert tone="info">
        No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>.
      </Alert>
    );
  return (
    <Card title="Your holdings: fundamentals">
      <p className="mb-3 text-sm text-fg-subtle">
        Cached data only. Run <b>Refresh fundamentals + peers</b> in Settings → Data refresh to fill gaps and sector medians.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-fg-subtle">
            <tr>
              <th className="py-1 pr-2">Stock</th>
              <th className="pr-2">Sector</th>
              <th className="pr-2 text-right">P/E</th>
              <th className="pr-2 text-right">ROE</th>
              <th className="pr-2 text-right">D/E</th>
              <th className="pr-2 text-right">F-score</th>
              <th className="pr-2 text-right">▲</th>
              <th className="pr-2 text-right">▼</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.ticker} className="border-t border-border align-top">
                <td className="py-1 pr-2">
                  <Link className="underline" to={`/analysis/${encodeURIComponent(r.ticker)}?view=fundamental`}>
                    {r.label}
                  </Link>
                  <div className="font-mono text-xs text-fg-subtle">{r.ticker}</div>
                </td>
                <td className="pr-2 text-xs">{r.sector ?? "—"}</td>
                <td className="pr-2 text-right tabular-nums">{r.pe?.toFixed(1) ?? "—"}</td>
                <td className="pr-2 text-right tabular-nums">{r.roe != null ? `${r.roe.toFixed(1)}%` : "—"}</td>
                <td className="pr-2 text-right tabular-nums">{r.debt_equity?.toFixed(2) ?? "—"}</td>
                <td className="pr-2 text-right tabular-nums">{r.fscore != null ? `${r.fscore}/9` : "—"}</td>
                <td className="pr-2 text-right tabular-nums">{r.bullish}</td>
                <td className="pr-2 text-right tabular-nums">{r.bearish}</td>
                <td>
                  <FreshnessBadge f={r.freshness} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
