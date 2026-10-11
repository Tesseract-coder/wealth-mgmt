import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  signalApi,
  type ConfidenceLevel,
  type HoldingSignals,
  type Reading,
  type RiskKey,
  type SideScore,
  type SignalKey,
  type StockSignal,
  type StyleKey,
} from "../api/client";
import { formatDate, formatINR } from "../lib/format";
import { FreshnessBadge } from "./MarketData";
import { Alert, Card } from "./ui";
import { SignalPill } from "./analysis/SignalPill";

/** Kept here for existing imports; the pill now lives in components/analysis. */
export { SignalPill };

const CONF: Record<ConfidenceLevel, string> = { high: "High", medium: "Medium", low: "Low" };

export function ConfidenceTag({ c, title }: { c: ConfidenceLevel | null; title?: string }) {
  return (
    <span title={title} className="text-xs text-slate-600 dark:text-slate-400">
      {c ? `${CONF[c]} confidence` : "No confidence"}
    </span>
  );
}

const CATEGORY: Record<string, string> = {
  trend: "Trend",
  momentum: "Momentum",
  volume: "Volume",
  structure: "Structure",
  relative_strength: "Relative strength",
  volatility: "Volatility",
  pattern: "Patterns",
  valuation: "Valuation",
  profitability: "Profitability",
  growth: "Growth",
  health: "Financial health",
  quality: "Quality (F-score)",
  ownership: "Ownership",
};

const TF: Record<string, string> = { "15m": "15-min", "1h": "Hourly", "1d": "Daily", "1wk": "Weekly", "1mo": "Monthly" };

function fmtScore(v: number | null): string {
  return v === null ? "—" : v.toFixed(0);
}

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

export function ScoreBar({ value, label }: { value: number | null; label: string }) {
  const w = value === null ? 0 : Math.max(0, Math.min(100, value));
  const tone = value === null ? "bg-slate-300" : value >= 60 ? "bg-emerald-600" : value < 40 ? "bg-red-600" : "bg-slate-500";
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums font-medium">{value === null ? "no data" : `${value.toFixed(0)}/100`}</span>
      </div>
      <div
        className="h-2 w-full rounded bg-slate-200 dark:bg-slate-800"
        role="meter"
        aria-label={label}
        aria-valuenow={value ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`h-2 rounded ${tone}`} style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}

export function StockSignalView({ ticker, style, risk }: { ticker: string; style: StyleKey | null; risk?: RiskKey | null }) {
  const q = useQuery({ queryKey: ["signal", ticker, style, risk], queryFn: () => signalApi.stock(ticker, style, risk) });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Scoring {ticker}… (the first look downloads prices and fundamentals)</Card>;
  return <StockSignalBody s={q.data} />;
}

function ReasonList({ items, empty }: { items: Reading[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  return (
    <ol className="space-y-1 text-sm">
      {items.map((r) => (
        <li key={`${r.source}-${r.key}-${r.text}`} className="flex gap-2">
          <span className="w-12 shrink-0 text-right tabular-nums text-xs text-slate-500" title="Points added to the composite score">
            {r.points > 0 ? "+" : "−"}
            {Math.abs(r.points).toFixed(1)}
          </span>
          <span>
            {r.text}
            <span className="ml-1 text-xs text-slate-500">
              ({r.source === "technical" ? "technical" : "fundamental"} · {CATEGORY[r.category] ?? r.category}
              {r.timeframes.length > 0 ? ` · ${r.timeframes.map((t) => TF[t] ?? t).join(", ")}` : ""})
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function SideBreakdown({ title, side, weight }: { title: string; side: SideScore; weight: number }) {
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold">
        {title} {fmtScore(side.score)}
        <span className="ml-1 font-normal text-slate-500">
          · {Math.round(weight * 100)}% of composite · {Math.round(side.coverage * 100)}% of inputs had data
        </span>
      </h3>
      {!side.applicable ? (
        <p className="text-sm text-slate-500">Not applicable to this security.</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {side.subscores.map((x) => (
              <tr key={x.category} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">{CATEGORY[x.category] ?? x.category}</td>
                <td className="pr-2 text-right text-xs text-slate-500">weight {Math.round(x.weight * 100)}%</td>
                <td className="pr-2 text-right tabular-nums font-medium">{x.score === null ? "no data" : x.score.toFixed(0)}</td>
                <td className="text-right text-xs text-slate-500 tabular-nums">
                  ▲{x.bullish} ▼{x.bearish} ●{x.neutral}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {side.timeframes.length > 1 && (
        <p className="mt-1 text-xs text-slate-500">
          By timeframe:{" "}
          {side.timeframes.map((t) => `${TF[t.interval] ?? t.interval} ${fmtScore(t.score)} (${Math.round(t.weight * 100)}%)`).join(" · ")}
        </p>
      )}
      {side.notes.map((n) => (
        <p key={n} className="mt-1 text-xs text-amber-800 dark:text-amber-300">
          {n}
        </p>
      ))}
    </div>
  );
}

export function StockSignalBody({ s }: { s: StockSignal }) {
  const sc = s.scores;
  const lv = s.levels;
  const pos = s.position;
  return (
    <div className="space-y-4">
      {s.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      <Card
        title={`Signal · ${s.style_label} style, ${s.risk_label} risk`}
        actions={
          <span className="flex items-center gap-2 text-xs text-slate-500">
            Prices <FreshnessBadge f={s.price_freshness} /> Fundamentals <FreshnessBadge f={s.fundamental_freshness} />
          </span>
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-lg">
            <SignalPill signal={s.signal} label={s.signal_label} />
          </span>
          <span className="text-xl font-semibold tabular-nums">{fmtScore(sc.composite)}</span>
          <span className="text-sm text-slate-500">composite score</span>
          <ConfidenceTag c={sc.confidence} title={sc.confidence_reason} />
        </div>
        <p className="mt-2 text-sm">
          <span className="font-medium">Why: </span>
          {s.rule}.
        </p>
        <p className="text-xs text-slate-500">Confidence: {sc.confidence_reason}.</p>
        {s.flags.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {s.flags.map((f) => (
              <li key={f.key} className={f.severe ? "text-red-700 dark:text-red-400" : "text-amber-800 dark:text-amber-300"}>
                {f.severe ? "⛔ Severe red flag: " : "⚠ Red flag: "}
                {f.text}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-1 text-sm font-semibold text-emerald-700 dark:text-emerald-400">▲ Top bullish reasons</h3>
            <ReasonList items={s.bullish} empty="None" />
          </div>
          <div>
            <h3 className="mb-1 text-sm font-semibold text-red-700 dark:text-red-400">▼ Top bearish reasons</h3>
            <ReasonList items={s.bearish} empty="None" />
          </div>
        </div>
      </Card>

      <Card title="Score breakdown">
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <ScoreBar value={sc.composite} label="Composite" />
          <ScoreBar value={sc.technical.score} label={`Technical (${Math.round(sc.technical_weight * 100)}%)`} />
          <ScoreBar value={sc.fundamental.score} label={`Fundamental (${Math.round(sc.fundamental_weight * 100)}%)`} />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <SideBreakdown title="Technical" side={sc.technical} weight={sc.technical_weight} />
          <SideBreakdown title="Fundamental" side={sc.fundamental} weight={sc.fundamental_weight} />
        </div>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-slate-600 dark:text-slate-400">All {s.readings.length} readings and their points</summary>
          <ReasonList items={s.readings.filter((r) => r.points !== 0)} empty="None scored" />
          {s.readings.some((r) => r.points === 0) && (
            <p className="mt-2 text-xs text-slate-500">
              Not scored (neutral or for information): {s.readings.filter((r) => r.points === 0).map((r) => r.text).join("; ")}
            </p>
          )}
        </details>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Stop-loss and targets">
          {lv ? (
            <div className="space-y-2 text-sm">
              <dl className="grid grid-cols-2 gap-2">
                <div>
                  <dt className="text-xs text-slate-500">Last close ({TF[lv.interval] ?? lv.interval})</dt>
                  <dd className="tabular-nums">{formatINR(lv.close)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">ATR trailing stop</dt>
                  <dd className={`tabular-nums ${lv.stop_breached ? "font-semibold text-red-700 dark:text-red-400" : ""}`}>
                    {formatINR(lv.trailing_stop)} {lv.stop_breached && "(closed below)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Stop for a new purchase</dt>
                  <dd className="tabular-nums">{formatINR(lv.entry_stop)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Risk per share (R)</dt>
                  <dd className="tabular-nums">{formatINR(lv.risk_per_share)}</dd>
                </div>
              </dl>
              <table className="w-full">
                <tbody>
                  {lv.targets.map((t) => (
                    <tr key={t.label} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1">Target: {t.label}</td>
                      <td className="text-right tabular-nums">{formatINR(t.price)}</td>
                      <td className="text-right tabular-nums text-xs text-slate-500">+{t.pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-slate-500">{lv.basis}</p>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Not enough price history for an ATR stop.</p>
          )}
          <p className="mt-2 text-xs text-slate-500">
            Beta {s.beta === null ? "—" : s.beta.toFixed(2)} ({s.beta_basis})
          </p>
        </Card>

        <Card title="Position and sizing">
          <div className="space-y-2 text-sm">
            {pos ? (
              <dl className="grid grid-cols-2 gap-2">
                <div>
                  <dt className="text-xs text-slate-500">Quantity · avg price</dt>
                  <dd className="tabular-nums">
                    {pos.quantity} · {formatINR(pos.avg_price)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Value ({pos.price_source})</dt>
                  <dd className="tabular-nums">{formatINR(pos.value, 0)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Unrealised P&amp;L</dt>
                  <dd className={`tabular-nums ${(pos.pnl ?? 0) < 0 ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`}>
                    {formatINR(pos.pnl, 0)} {pos.pnl_pct !== null && `(${pos.pnl_pct > 0 ? "+" : ""}${pos.pnl_pct.toFixed(1)}%)`}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Weight vs your limit</dt>
                  <dd className={`tabular-nums ${s.weight !== null && s.weight > s.max_weight ? "font-semibold text-amber-800 dark:text-amber-300" : ""}`}>
                    {pct(s.weight)} of {pct(s.max_weight, 0)} max
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="text-slate-500">You don't hold this stock.</p>
            )}
            {s.sector && (
              <p className="text-xs text-slate-500">
                Sector {s.sector}: {pct(s.sector_weight)} of your portfolio (limit {pct(s.max_sector_weight, 0)})
              </p>
            )}
            <p className="rounded bg-slate-100 p-2 dark:bg-slate-800">
              <span className="font-medium">Suggested: </span>
              {s.rebalance.text}
            </p>
            <p className="text-xs text-slate-500">Suggestions only: this app never places orders.</p>
          </div>
        </Card>
      </div>

      {s.tax && (
        <Card title="Tax note">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {s.tax.text.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">{s.tax.verify_note}</p>
        </Card>
      )}
      <SignalHistory ticker={s.ticker} />
    </div>
  );
}

export function SignalHistory({ ticker }: { ticker: string }) {
  const q = useQuery({ queryKey: ["signal-history", ticker], queryFn: () => signalApi.history(ticker) });
  if (!q.data || q.data.length === 0) return null;
  return (
    <Card title="Signal history">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-2">Day</th>
              <th className="pr-2">Style · risk</th>
              <th className="pr-2">Signal</th>
              <th className="pr-2 text-right">Composite</th>
              <th className="pr-2 text-right">Tech</th>
              <th className="text-right">Fund</th>
            </tr>
          </thead>
          <tbody>
            {q.data.slice(0, 30).map((h) => (
              <tr key={`${h.day}-${h.style}-${h.risk}`} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2 whitespace-nowrap">{formatDate(h.day)}</td>
                <td className="pr-2 text-xs">
                  {h.style} · {h.risk}
                </td>
                <td className="pr-2">
                  <SignalPill signal={h.signal} label={h.signal_label} />
                </td>
                <td className="pr-2 text-right tabular-nums">{fmtScore(h.composite)}</td>
                <td className="pr-2 text-right tabular-nums">{fmtScore(h.technical)}</td>
                <td className="text-right tabular-nums">{fmtScore(h.fundamental)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

const SEVERITY: Record<SignalKey, number> = { sell: 0, reduce: 1, strong_buy: 2, buy: 3, hold: 4, no_signal: 5 };

export function HoldingSignalsView({ style, risk, linkQuery = "" }: { style: StyleKey | null; risk?: RiskKey | null; linkQuery?: string }) {
  const q = useQuery({ queryKey: ["signal-holdings", style, risk], queryFn: () => signalApi.holdings(style, risk) });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Scoring your holdings…</Card>;
  return <HoldingSignalsTable d={q.data} linkQuery={linkQuery} />;
}

export function HoldingSignalsTable({ d, linkQuery = "" }: { d: HoldingSignals; linkQuery?: string }) {
  if (d.holdings.length === 0)
    return (
      <Alert tone="info">
        No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>.
      </Alert>
    );
  const rows = [...d.holdings].sort((a, b) => SEVERITY[a.signal] - SEVERITY[b.signal] || (b.weight ?? 0) - (a.weight ?? 0));
  return (
    <div className="space-y-4">
      {d.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      <Card title={`Signals · ${d.style_label} style (technical ${Math.round(d.technical_weight * 100)}%), ${d.risk_label} risk`}>
        <p className="mb-3 text-sm text-slate-500">
          Portfolio {formatINR(d.total_value, 0)} ({d.weight_base === "portfolio" ? `stocks ${formatINR(d.stock_value, 0)} + funds ${formatINR(d.fund_value, 0)}` : "stocks only"}). Uses cached data
          only: run <b>Refresh now</b> in Settings → Data refresh first. Sorted by what needs attention.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-2">Stock</th>
                <th className="pr-2">Signal</th>
                <th className="pr-2 text-right">Score</th>
                <th className="pr-2 text-right">Tech</th>
                <th className="pr-2 text-right">Fund</th>
                <th className="pr-2">Confidence</th>
                <th className="pr-2 text-right">Weight</th>
                <th className="pr-2">Why</th>
                <th className="pr-2">Suggested</th>
                <th>Prices</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.ticker} className="border-t border-slate-100 align-top dark:border-slate-800">
                  <td className="py-1 pr-2">
                    <Link className="underline" to={`/analysis/${encodeURIComponent(h.ticker)}${linkQuery}`}>
                      {h.label}
                    </Link>
                    <div className="font-mono text-xs text-slate-500">{h.ticker}</div>
                  </td>
                  <td className="pr-2">
                    <SignalPill signal={h.signal} label={h.signal_label} />
                  </td>
                  <td className="pr-2 text-right tabular-nums font-medium">{fmtScore(h.composite)}</td>
                  <td className="pr-2 text-right tabular-nums">{fmtScore(h.technical)}</td>
                  <td className="pr-2 text-right tabular-nums">{fmtScore(h.fundamental)}</td>
                  <td className="pr-2">
                    <ConfidenceTag c={h.confidence} />
                  </td>
                  <td className={`pr-2 text-right tabular-nums ${h.weight !== null && h.weight > h.max_weight ? "font-semibold text-amber-800 dark:text-amber-300" : ""}`}>
                    {pct(h.weight)}
                  </td>
                  <td className="pr-2 text-xs">
                    <div>{h.rule}</div>
                    {h.flags.map((f) => (
                      <div key={f.key} className={f.severe ? "text-red-700 dark:text-red-400" : "text-amber-800 dark:text-amber-300"}>
                        {f.severe ? "⛔" : "⚠"} {f.text}
                      </div>
                    ))}
                    {h.top_bullish.slice(0, 1).map((t) => (
                      <div key={t}>▲ {t}</div>
                    ))}
                    {h.top_bearish.slice(0, 1).map((t) => (
                      <div key={t}>▼ {t}</div>
                    ))}
                  </td>
                  <td className="pr-2 text-xs">{h.rebalance.action === "none" ? "—" : h.rebalance.text}</td>
                  <td>
                    <FreshnessBadge f={h.price_freshness} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d.sectors.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-semibold">Sector weights</h3>
            <ul className="grid gap-1 text-sm sm:grid-cols-2">
              {d.sectors.map((x) => (
                <li key={x.sector} className={x.over ? "text-amber-800 dark:text-amber-300" : ""}>
                  {x.over ? "⚠ " : ""}
                  {x.sector}: {pct(x.weight)} {x.over && `(above your ${pct(x.limit, 0)} limit)`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}
