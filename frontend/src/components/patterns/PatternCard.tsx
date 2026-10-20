import { CandlestickChart, Volume2, VolumeX } from "lucide-react";
import type { PatternInfo, PatternMatch, PatternReport } from "../../api/client";
import { formatPct } from "../../lib/format";
import { Badge, Button, Disclosure } from "../ui";
import { ACTION, DIRECTION, KIND, levelLabels, STRENGTH, statusLabel } from "./meta";
import { PatternMiniChart } from "./PatternMiniChart";
import { PatternShape } from "./PatternShape";
import { HorizonFit, PatternDetails } from "./PatternGuide";

const VERDICT_BORDER = { bullish: "border-good", bearish: "border-bad", neutral: "border-accent" } as const;

/** One pattern found on the chart: what it is, whether it's confirmed, and the prices that matter. */
export function PatternCard({
  match: m,
  info,
  report,
  px,
  onShow,
}: {
  match: PatternMatch;
  info?: PatternInfo;
  report: PatternReport;
  px: (v: number) => string;
  /** Draw it on the main price chart (only for the daily, weekly and monthly charts). */
  onShow?: () => void;
}) {
  const dir = DIRECTION[m.direction];
  const labels = levelLabels(m);
  const short = (v: number) => px(v).replace(/\.\d+$/, (d) => (v >= 1000 ? "" : d));
  return (
    <article aria-label={m.name} className="flex min-w-0 flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <header className="flex items-start gap-3">
        <PatternShape patternKey={m.key} direction={m.direction} className="h-10 w-20 rounded-control bg-surface-2 p-1" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-base font-semibold text-fg">{m.name}</h3>
            <Badge tone={dir.tone} icon={dir.icon}>
              {dir.label}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-fg-muted">
            {info ? `${KIND[info.kind]} · ` : ""}
            <span className={m.status === "confirmed" ? "font-semibold text-fg" : ""}>{statusLabel(m, report.unit)}</span>
          </p>
        </div>
        <Strength m={m} />
      </header>

      <div className="rounded-control border border-border bg-surface p-1">
        <PatternMiniChart window={report.window} match={m} px={short} />
      </div>

      {info && <p className={`border-l-4 pl-3 text-sm font-medium text-fg ${VERDICT_BORDER[m.direction]}`}>{info.verdict}</p>}

      <dl className="grid grid-cols-3 gap-2 text-sm">
        <Level label={labels.breakout} value={m.breakout} pct={null} px={px} />
        <Level label={labels.target} value={m.target} pct={m.target_pct} px={px} tone={m.direction === "bearish" ? "text-bad" : m.direction === "bullish" ? "text-good" : undefined} />
        <Level label={labels.cancel} value={m.invalidation} pct={m.invalidation_pct} px={px} />
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        {info && <Badge tone={ACTION[info.action].tone}>{ACTION[info.action].label}</Badge>}
        {m.status === "confirmed" && m.volume_confirmed !== null && (
          <Badge tone={m.volume_confirmed ? "good" : "caution"} icon={m.volume_confirmed ? Volume2 : VolumeX}>
            {m.volume_confirmed ? "Volume confirms" : "No volume surge"}
          </Badge>
        )}
        {info && <HorizonFit info={info} compact />}
      </div>

      <p className="text-sm text-fg-muted">{m.text}</p>

      {info && (
        <Disclosure summary="What it means and how to trade it">
          <PatternDetails info={info} />
        </Disclosure>
      )}
      {onShow && (
        <Button variant="secondary" size="sm" icon={CandlestickChart} onClick={onShow} className="self-start">
          Show on the price chart
        </Button>
      )}
    </article>
  );
}

function Level({ label, value, pct, px, tone }: { label: string; value: number | null; pct: number | null; px: (v: number) => string; tone?: string }) {
  return (
    <div className="min-w-0 rounded-control bg-surface-2 px-2 py-1.5">
      <dt className="text-xs leading-tight text-fg-subtle">{label}</dt>
      <dd className={`font-semibold tabular-nums ${tone ?? "text-fg"}`}>{value == null ? "—" : px(value)}</dd>
      {pct != null && <dd className="text-xs tabular-nums text-fg-subtle">{formatPct(pct)} from now</dd>}
    </div>
  );
}

/** How well the chart fits the textbook shape: a 4-step meter with its words. */
function Strength({ m }: { m: PatternMatch }) {
  const steps = m.confidence >= 80 ? 4 : m.confidence >= 70 ? 3 : m.confidence >= 55 ? 2 : 1;
  return (
    <div className="flex shrink-0 flex-col items-end gap-1" title={`Fit ${m.confidence}/100: how cleanly the chart matches the textbook shape, with extra weight for a confirmed break and volume.`}>
      <span className="flex gap-0.5" aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-2 w-3 rounded-sm ${i <= steps ? "bg-accent" : "bg-surface-3"}`} />
        ))}
      </span>
      <span className="text-xs text-fg-muted">{STRENGTH[m.strength]}</span>
    </div>
  );
}
