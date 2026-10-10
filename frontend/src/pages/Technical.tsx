import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  analysisApi,
  api,
  portfolioApi,
  type Direction,
  type FrameAnalysis,
  type Observation,
  type StyleKey,
  type TimeframeReport,
} from "../api/client";
import { FreshnessBadge } from "../components/MarketData";
import { Alert, Card, inputClass } from "../components/ui";
import { useDebounced } from "../hooks/useDebounced";
import { formatDate, formatINR } from "../lib/format";

const DIR: Record<Direction, { label: string; icon: string; cls: string }> = {
  bullish: { label: "Bullish", icon: "▲", cls: "text-emerald-700 dark:text-emerald-400" },
  bearish: { label: "Bearish", icon: "▼", cls: "text-red-700 dark:text-red-400" },
  neutral: { label: "Neutral", icon: "●", cls: "text-slate-500" },
};

const INTERVAL_LABEL: Record<string, string> = {
  "15m": "15-minute",
  "1h": "Hourly",
  "1d": "Daily",
  "1wk": "Weekly",
  "1mo": "Monthly",
};

export function DirectionTag({ d }: { d: Direction }) {
  const s = DIR[d];
  return (
    <span className={`whitespace-nowrap text-xs font-medium ${s.cls}`}>
      {s.icon} {s.label}
    </span>
  );
}

/** Technical readings for a holding or any NSE stock (full stock detail with charts: Phase 8). */
export function Technical() {
  const { ticker } = useParams();
  const [params, setParams] = useSearchParams();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = (params.get("style") as StyleKey | null) ?? profile.data?.style ?? null;
  const styleKnown = params.has("style") || profile.isSuccess || profile.isError;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Technicals</h1>
          <p className="text-sm text-slate-500">
            Chart readings with the numbers behind each one. Scores and Buy/Hold/Sell signals come in a later phase.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-slate-500">Style</span>
            <select
              className={inputClass}
              value={style ?? ""}
              onChange={(e) => setParams(e.target.value ? { style: e.target.value } : {})}
            >
              <option value="">Daily only (no style chosen)</option>
              {config.data &&
                Object.entries(config.data.styles).map(([k, s]) => (
                  <option key={k} value={k}>
                    {s.label} ({s.timeframes.join(", ")})
                  </option>
                ))}
            </select>
          </label>
          <TickerSearch style={style} />
        </div>
      </div>
      {/* Wait for the saved profile so we don't analyse twice (once without, once with the style). */}
      {!styleKnown ? (
        <Card>Loading…</Card>
      ) : ticker ? (
        <Report ticker={ticker} style={style} />
      ) : (
        <HoldingsSummary style={style} />
      )}
    </div>
  );
}

function TickerSearch({ style }: { style: StyleKey | null }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const dq = useDebounced(q.trim());
  const results = useQuery({
    queryKey: ["ref", "stock", dq],
    queryFn: () => portfolioApi.searchSecurities(dq),
    enabled: dq.length >= 2,
  });
  const go = (t: string) => {
    setQ("");
    navigate(`/technical/${encodeURIComponent(t)}${style ? `?style=${style}` : ""}`);
  };
  return (
    <div className="relative w-72 text-sm">
      <label>
        <span className="mb-1 block text-slate-500">Stock</span>
        <input
          className={inputClass}
          placeholder="Search NSE symbol or company…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.trim()) {
              const t = q.trim().toUpperCase();
              go(t.includes(".") || t.startsWith("^") ? t : `${t}.NS`);
            }
          }}
        />
      </label>
      {dq.length >= 2 && results.data && results.data.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full rounded border border-slate-200 bg-white shadow dark:border-slate-700 dark:bg-slate-900">
          {results.data.map((s) => (
            <li key={s.symbol}>
              <button
                type="button"
                className="w-full px-2 py-1 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => go(`${s.symbol}.NS`)}
              >
                <span className="font-mono">{s.symbol}</span> · {s.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function HoldingsSummary({ style }: { style: StyleKey | null }) {
  const q = useQuery({ queryKey: ["tech-holdings", style], queryFn: () => analysisApi.holdings(style) });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Loading…</Card>;
  if (q.data.length === 0)
    return (
      <Alert tone="info">
        No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>, or search for any stock above.
      </Alert>
    );
  return (
    <Card title="Your holdings">
      <p className="mb-3 text-sm text-slate-500">
        Uses cached prices only. If a row says Unavailable, run <b>Refresh now</b> on the Overview page.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-2">Stock</th>
              <th className="pr-2">As of</th>
              <th className="pr-2 text-right">▲ Bullish</th>
              <th className="pr-2 text-right">▼ Bearish</th>
              <th className="pr-2">Main readings</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.ticker} className="border-t border-slate-100 align-top dark:border-slate-800">
                <td className="py-1 pr-2">
                  <Link className="underline" to={`/technical/${encodeURIComponent(r.ticker)}${style ? `?style=${style}` : ""}`}>
                    {r.label}
                  </Link>
                  <div className="font-mono text-xs text-slate-500">{r.ticker}</div>
                </td>
                <td className="pr-2 whitespace-nowrap">{formatDate(r.as_of)}</td>
                <td className="pr-2 text-right tabular-nums">{r.bullish}</td>
                <td className="pr-2 text-right tabular-nums">{r.bearish}</td>
                <td className="pr-2 text-xs">
                  {r.top_bullish.slice(0, 1).map((t) => (
                    <div key={t}>▲ {t}</div>
                  ))}
                  {r.top_bearish.slice(0, 1).map((t) => (
                    <div key={t}>▼ {t}</div>
                  ))}
                </td>
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

function Report({ ticker, style }: { ticker: string; style: StyleKey | null }) {
  const q = useQuery({ queryKey: ["technical", ticker, style], queryFn: () => analysisApi.technical(ticker, style) });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Analysing {ticker}… (the first look at a stock downloads its price history)</Card>;
  const r = q.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-xl font-semibold">{r.label}</h2>
        <Link to={style ? `/technical?style=${style}` : "/technical"} className="text-sm underline">
          ← all holdings
        </Link>
      </div>
      {r.fetch_errors.map((e) => (
        <Alert key={e} tone="warning">
          Could not refresh: {e}. Showing cached data where available.
        </Alert>
      ))}
      {r.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      {r.timeframes.map((tf) => (
        <TimeframeCard key={tf.interval} tf={tf} isIndex={ticker.startsWith("^")} />
      ))}
      <Card title="Context (daily)">
        <Readings a={r.context} />
      </Card>
    </div>
  );
}

function TimeframeCard({ tf, isIndex }: { tf: TimeframeReport; isIndex: boolean }) {
  const px = (v: number | null | undefined) =>
    v == null ? "—" : isIndex ? v.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : formatINR(v);
  const v = tf.analysis.values;
  const keyVals: [string, string][] = [
    ["Close", px(tf.last_close)],
    ["SMA 50", px(v.sma50)],
    ["SMA 200", px(v.sma200)],
    ["RSI 14", v.rsi14 == null ? "—" : v.rsi14.toFixed(1)],
    ["ADX", v.adx == null ? "—" : v.adx.toFixed(1)],
    ["ATR 14", px(v.atr14)],
    ["Support", px(v.support)],
    ["Resistance", px(v.resistance)],
  ];
  return (
    <Card
      title={`${INTERVAL_LABEL[tf.interval] ?? tf.interval} · ${tf.bars} bars`}
      actions={
        <span className="flex items-center gap-2 text-sm text-slate-500">
          as of {tf.as_of ? (tf.as_of.length > 10 ? new Date(tf.as_of).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : formatDate(tf.as_of)) : "—"}
          <FreshnessBadge f={tf.freshness} />
        </span>
      }
    >
      {tf.freshness.status !== "fresh" && <p className="mb-2 text-xs text-slate-500">{tf.freshness.reason}</p>}
      {tf.notes.map((n) => (
        <p key={n} className="mb-2 text-xs text-amber-800 dark:text-amber-300">
          {n}
        </p>
      ))}
      {tf.bars > 0 && (
        <dl className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:grid-cols-8">
          {keyVals.map(([k, val]) => (
            <div key={k}>
              <dt className="text-xs text-slate-500">{k}</dt>
              <dd className="tabular-nums">{val}</dd>
            </div>
          ))}
        </dl>
      )}
      <Readings a={tf.analysis} />
    </Card>
  );
}

const ORDER: Direction[] = ["bullish", "bearish", "neutral"];

function Readings({ a }: { a: FrameAnalysis }) {
  const by = (d: Direction): Observation[] => a.observations.filter((o) => o.direction === d);
  return (
    <div>
      <div className="grid gap-4 md:grid-cols-3">
        {ORDER.map((d) => (
          <div key={d}>
            <h3 className="mb-1 text-sm font-semibold">
              <DirectionTag d={d} /> ({by(d).length})
            </h3>
            <ul className="space-y-1 text-sm">
              {by(d).map((o) => (
                <li key={o.key}>
                  {o.text}
                  {o.minor && <span className="ml-1 text-xs text-slate-500">(minor)</span>}
                </li>
              ))}
              {by(d).length === 0 && <li className="text-slate-500">None</li>}
            </ul>
          </div>
        ))}
      </div>
      {a.unavailable.length > 0 && (
        <div className="mt-3 text-xs text-slate-500">
          <span className="font-medium">Not available:</span> {a.unavailable.join("; ")}
        </div>
      )}
    </div>
  );
}
