import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { analysisApi, type Backtest, type BacktestPerformance, type StyleKey } from "../api/client";
import { ComparisonLine } from "../charts/PortfolioCharts";
import { formatDate } from "../lib/format";
import { SignalPill } from "./SignalView";
import { Alert, Button, Card } from "./ui";

const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(digits)}%`;
const share = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** Replays the technical rules over past prices (on request: it takes a few seconds). */
export function BacktestView({ ticker, style }: { ticker: string; style: StyleKey | null }) {
  const [run, setRun] = useState(false);
  const q = useQuery({
    queryKey: ["backtest", ticker, style],
    queryFn: () => analysisApi.backtest(ticker, style),
    enabled: run,
    staleTime: 10 * 60_000,
  });
  return (
    <div className="space-y-4">
      <Alert tone="warning">
        <strong>Historical test only.</strong> This replays the app's <em>technical</em> rules over past prices to show how they
        would have behaved. Past results don't predict future returns. Fundamentals aren't replayed (their history isn't available
        free), and there are no costs, taxes or slippage.
      </Alert>
      {!q.data && (
        <Card>
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
            Every week of the last 3 years, the rules see only the prices up to that day and give a signal. The app then checks what
            the price did next. Settings are under <code>backtest:</code> in <code>profiles.yaml</code>.
          </p>
          <Button onClick={() => setRun(true)} disabled={q.isFetching}>
            {q.isFetching ? "Replaying… (a few seconds)" : `Run backtest for ${ticker}`}
          </Button>
          {q.isError && (
            <div className="mt-3">
              <Alert tone="error">{q.error.message}</Alert>
            </div>
          )}
        </Card>
      )}
      {q.data && <BacktestResult b={q.data} />}
    </div>
  );
}

function Perf({ title, p, trades }: { title: string; p: BacktestPerformance | null; trades?: number }) {
  return (
    <div className="rounded border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs uppercase tracking-wide text-slate-500">{title}</div>
      <div className={`text-xl font-semibold tabular-nums ${p && p.total_return < 0 ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`}>
        {pct(p?.total_return)}
      </div>
      <div className="text-xs text-slate-500">
        Max drawdown {pct(p?.max_drawdown)} · in the market {share(p?.exposure)}
        {trades !== undefined && ` · ${trades} entr${trades === 1 ? "y" : "ies"}`}
      </div>
    </div>
  );
}

export function BacktestResult({ b }: { b: Backtest }) {
  if (b.status !== "ok") {
    return (
      <Alert tone="info">
        Not enough price history to backtest {b.label}: {b.message}
      </Alert>
    );
  }
  const base = b.stats.find((s) => s.group === "all");
  const last = b.points[b.points.length - 1];
  return (
    <Card title={`${b.label}: ${b.style_label} style, ${b.risk_label} risk`}>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">
        {formatDate(b.start)} – {formatDate(b.end)}: {b.message} Evaluated every {b.step_sessions} sessions on{" "}
        {b.timeframes.join(" + ")} bars; a signal is judged {b.horizon_sessions} sessions later.
      </p>
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Perf title="Following the rules" p={b.strategy} trades={b.trades} />
        <Perf title="Buy and hold" p={b.buy_hold} />
      </div>
      <p className="mb-2 text-xs text-slate-500">
        "Following the rules" = in after a Buy, out after a Reduce/Sell, unchanged on Hold; trades at the next session's open.
      </p>
      <ComparisonLine
        dates={b.points.map((p) => p.date)}
        series={[
          { name: "Following the rules", values: b.points.map((p) => (p.strategy - 1) * 100) },
          { name: "Buy and hold", values: b.points.map((p) => (p.buy_hold - 1) * 100), dashed: true },
        ]}
        unit="%"
        zeroLine
      />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="mb-1 text-left text-sm font-semibold">How the signals did</caption>
          <thead className="text-left text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-2">Signal</th>
              <th className="pr-2 text-right">Times</th>
              <th className="pr-2 text-right">Right</th>
              <th className="pr-2 text-right">Price higher after</th>
              <th className="pr-2 text-right">Avg move after</th>
            </tr>
          </thead>
          <tbody>
            {b.stats.map((s) => (
              <tr key={s.group} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">{s.label}</td>
                <td className="pr-2 text-right tabular-nums">{s.count}</td>
                <td className="pr-2 text-right tabular-nums" title={s.measured < s.count ? `${s.count - s.measured} too recent to judge` : undefined}>
                  {share(s.hit_rate)}
                </td>
                <td className="pr-2 text-right tabular-nums">{share(s.rise_rate)}</td>
                <td className="pr-2 text-right tabular-nums">{pct(s.avg_forward_return)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-slate-500">
          A Buy is "right" if the price was higher {b.horizon_sessions} sessions later; a Reduce/Sell if it was lower. Compare with the
          base rate{base ? ` (${share(base.rise_rate)} of all weeks were followed by a rise)` : ""}: a rule only helps if it beats it.
        </p>
      </div>
      {last && (
        <p className="mt-3 text-sm">
          Replayed signal on {formatDate(last.date)}: <SignalPill signal={last.signal} label={SIGNAL_TEXT[last.signal]} /> (technical
          score {last.score ?? "—"}; the live signal also uses fundamentals and your position).
        </p>
      )}
      {[...b.notes, b.caveat].map((n) => (
        <p key={n} className="mt-2 text-xs text-slate-500">
          {n}
        </p>
      ))}
    </Card>
  );
}

const SIGNAL_TEXT: Record<Backtest["points"][number]["signal"], string> = {
  strong_buy: "Strong Buy / Add",
  buy: "Buy / Add",
  hold: "Hold",
  reduce: "Reduce / Trim",
  sell: "Sell / Exit",
  no_signal: "Insufficient data",
};
