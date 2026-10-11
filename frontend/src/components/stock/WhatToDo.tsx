import { CircleAlert, OctagonAlert, Receipt, Scale, Target } from "lucide-react";
import type { StockSignal } from "../../api/client";
import { formatINR } from "../../lib/format";
import { SignalPill } from "../analysis";
import { ReasonList, ScoreBreakdown, SignalHistory } from "../SignalView";
import { Disclosure, Stat } from "../ui";

const TF: Record<string, string> = { "15m": "15-min", "1h": "hourly", "1d": "daily", "1wk": "weekly", "1mo": "monthly" };

/**
 * The signal and what it suggests: the rule that fired, red flags, the main reasons, stop-loss and
 * targets, a trim/add quantity, and the tax note. The score breakdown and signal history sit in
 * expanders underneath.
 */
export function WhatToDo({ s }: { s: StockSignal }) {
  const lv = s.levels;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <SignalPill signal={s.signal} label={s.signal_label} size="md" />
        <span className="text-sm text-fg-muted">
          Composite score <span className="font-semibold text-fg">{s.scores.composite === null ? "—" : Math.round(s.scores.composite)}</span>/100
        </span>
      </div>
      <p className="text-sm text-fg">
        <span className="font-semibold">Why: </span>
        {s.rule}.
      </p>
      <p className="text-xs text-fg-subtle">
        The signal weighs technical and fundamental scores for your {s.style_label.toLowerCase()} style, then your stop-loss and position size. The Score
        Shape above counts checks, so the two can differ.
      </p>

      {s.flags.length > 0 && (
        <ul className="space-y-1.5">
          {s.flags.map((f) => (
            <li key={f.key} className={`flex items-start gap-2 rounded-control border px-3 py-2 text-sm ${f.severe ? "border-bad-border bg-bad-soft text-bad" : "border-caution-border bg-caution-soft text-caution"}`}>
              {f.severe ? <OctagonAlert aria-hidden className="mt-0.5 size-4 shrink-0" /> : <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />}
              <span>
                <span className="font-semibold">{f.severe ? "Severe red flag: " : "Red flag: "}</span>
                {f.text}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1.5 text-sm font-semibold text-good">For buying or holding</h3>
          <ReasonList items={s.bullish} empty="None" />
        </div>
        <div>
          <h3 className="mb-1.5 text-sm font-semibold text-bad">Against</h3>
          <ReasonList items={s.bearish} empty="None" />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-control border border-border p-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-fg">
            <Target aria-hidden className="size-4 text-fg-subtle" /> Stop-loss and targets
          </h3>
          {lv ? (
            <>
              <dl className="grid grid-cols-2 gap-3">
                <Stat label={`Last close (${TF[lv.interval] ?? lv.interval})`} value={formatINR(lv.close)} />
                <Stat
                  label="Trailing stop"
                  value={<span className={lv.stop_breached ? "text-bad" : undefined}>{formatINR(lv.trailing_stop)}</span>}
                  hint={lv.stop_breached ? "Closed below it" : `${(((lv.close - lv.trailing_stop) / lv.close) * 100).toFixed(1)}% below the close`}
                  help="An ATR stop that rises with the price: a close below it is an exit signal."
                />
                <Stat label="Stop for a new purchase" value={formatINR(lv.entry_stop)} />
                <Stat label="Risk per share" value={formatINR(lv.risk_per_share)} help="Close minus the stop for a new purchase: one 'R'." />
              </dl>
              <ul className="mt-3 divide-y divide-border text-sm">
                {lv.targets.map((t) => (
                  <li key={t.label} className="flex justify-between gap-2 py-1.5">
                    <span className="text-fg-muted">Target: {t.label}</span>
                    <span className="font-semibold text-fg">
                      {formatINR(t.price)} <span className="font-normal text-good">+{t.pct.toFixed(1)}%</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-fg-subtle">{lv.basis}</p>
            </>
          ) : (
            <p className="text-sm text-fg-muted">Not enough price history for an ATR stop.</p>
          )}
          <p className="mt-2 text-xs text-fg-subtle">
            Beta {s.beta === null ? "—" : s.beta.toFixed(2)} ({s.beta_basis})
          </p>
        </div>

        <div className="space-y-3">
          <div className="rounded-control border border-border p-3">
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-fg">
              <Scale aria-hidden className="size-4 text-fg-subtle" /> Suggested trade
            </h3>
            <p className="text-sm text-fg">{s.rebalance.text}</p>
            {s.sector && s.sector_weight !== null && (
              <p className="mt-1 text-xs text-fg-subtle">
                {s.sector}: {(s.sector_weight * 100).toFixed(1)}% of your portfolio (limit {Math.round(s.max_sector_weight * 100)}%).
              </p>
            )}
            <p className="mt-1 text-xs text-fg-subtle">Suggestions only: this app never places orders.</p>
          </div>
          {s.tax && (
            <div className="rounded-control border border-border p-3">
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-fg">
                <Receipt aria-hidden className="size-4 text-fg-subtle" /> Tax note
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-fg">
                {s.tax.text.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-caution">{s.tax.verify_note}</p>
            </div>
          )}
        </div>
      </div>

      {s.notes.map((n) => (
        <p key={n} className="text-xs text-fg-subtle">
          {n}
        </p>
      ))}

      <div className="space-y-2">
        <Disclosure summary="Score breakdown and every reading" hint={`${s.readings.length} readings`}>
          <ScoreBreakdown s={s} />
        </Disclosure>
        <Disclosure summary="Signal history" lazy>
          <SignalHistory ticker={s.ticker} />
        </Disclosure>
      </div>
    </div>
  );
}
