import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleDot, CircleMinus } from "lucide-react";
import { useState } from "react";
import { patternApi, type Direction, type PatternInfo, type Suitability } from "../../api/client";
import { Badge, Chip, ChipGroup, Disclosure, ErrorState, SkeletonText } from "../ui";
import { ACTION, DIRECTION, HORIZONS, KIND, SUIT } from "./meta";
import { PatternShape } from "./PatternShape";

const SUIT_ICON = { good: CircleCheck, ok: CircleDot, poor: CircleMinus } as const;
const SUIT_CLS: Record<Suitability, string> = { good: "text-good", ok: "text-caution", poor: "text-fg-subtle" };

/** Intraday / Swing / Positional, each with how well the pattern suits it (icon + words). */
export function HorizonFit({ info, compact = false }: { info: PatternInfo; compact?: boolean }) {
  return (
    <ul className={`flex flex-wrap gap-x-3 gap-y-1 text-xs ${compact ? "" : "mt-1"}`} aria-label="Suits these trading styles">
      {HORIZONS.map((h) => {
        const s = info[h.key];
        const Icon = SUIT_ICON[s];
        return (
          <li key={h.key} className={`inline-flex items-center gap-1 ${SUIT_CLS[s]}`} title={`${h.label}: ${SUIT[s]}`}>
            <Icon aria-hidden className="size-3.5" />
            <span className={s === "poor" ? "line-through decoration-1" : ""}>{h.label}</span>
            <span className="sr-only">: {SUIT[s]}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** The long form: meaning, how to trade it, what confirms it, what cancels it, the target. */
export function PatternDetails({ info }: { info: PatternInfo }) {
  const rows: [string, string][] = [
    ["What it means", info.meaning],
    ["How to trade it", info.trade],
    ["What confirms it", info.confirm],
    ["What cancels it", info.fails],
    ["Textbook target", info.target_rule],
    ["Typical length", `${info.duration} on a daily chart`],
    ["Reliability", `${info.reliability[0]!.toUpperCase()}${info.reliability.slice(1)}: patterns are probabilities, not promises.`],
  ];
  return (
    <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[9rem_1fr]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-medium text-fg">{k}</dt>
          <dd className="text-fg-muted">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

type BiasFilter = "all" | Direction;
type HorizonFilter = "any" | (typeof HORIZONS)[number]["key"];

/**
 * Every pattern the scanner looks for, as cards with their textbook shape and verdict. `found`
 * marks the ones on the current chart.
 */
export function PatternGuide({ found = new Set<string>() }: { found?: Set<string> }) {
  const lib = useQuery({ queryKey: ["pattern-library"], queryFn: patternApi.library, staleTime: Infinity });
  const [bias, setBias] = useState<BiasFilter>("all");
  const [horizon, setHorizon] = useState<HorizonFilter>("any");
  if (lib.isError) return <ErrorState title="Couldn't load the pattern guide" detail={lib.error.message} onRetry={() => void lib.refetch()} />;
  if (!lib.data) return <SkeletonText lines={5} />;
  const shown = lib.data.filter((p) => (bias === "all" || p.bias === bias) && (horizon === "any" || p[horizon] === "good"));
  const count = (d: Direction) => lib.data.filter((p) => p.bias === d).length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <ChipGroup label="Signal">
          <Chip pressed={bias === "all"} onClick={() => setBias("all")}>
            All
          </Chip>
          {(["bullish", "bearish", "neutral"] as const).map((d) => (
            <Chip key={d} pressed={bias === d} onClick={() => setBias(d)} count={count(d)}>
              {DIRECTION[d].label}
            </Chip>
          ))}
        </ChipGroup>
        <ChipGroup label="Best for">
          <Chip pressed={horizon === "any"} onClick={() => setHorizon("any")}>
            Any style
          </Chip>
          {HORIZONS.map((h) => (
            <Chip key={h.key} pressed={horizon === h.key} onClick={() => setHorizon(h.key)}>
              {h.label}
            </Chip>
          ))}
        </ChipGroup>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((p) => (
          <GuideCard key={p.key} info={p} found={found.has(p.key)} />
        ))}
      </ul>
      {shown.length === 0 && <p className="text-sm text-fg-muted">No pattern matches both filters.</p>}
    </div>
  );
}

function GuideCard({ info, found }: { info: PatternInfo; found: boolean }) {
  const dir = DIRECTION[info.bias];
  return (
    <li className={`flex flex-col gap-2 rounded-card border bg-surface p-3 ${found ? "border-accent ring-1 ring-accent" : "border-border"}`}>
      <div className="flex items-start gap-3">
        <PatternShape patternKey={info.key} direction={info.bias} className="h-12 w-24 rounded-control bg-surface-2 p-1" />
        <div className="min-w-0">
          {info.family_label !== info.name && <p className="text-xs text-fg-subtle">{info.family_label}</p>}
          <h3 className="font-semibold text-fg">{info.name}</h3>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={dir.tone} icon={dir.icon}>
              {dir.label}
            </Badge>
            <Badge tone="neutral">{KIND[info.kind]}</Badge>
            {found && <Badge tone="accent">On this chart</Badge>}
          </div>
        </div>
      </div>
      <p className="text-sm text-fg">{info.verdict}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge tone={ACTION[info.action].tone}>{ACTION[info.action].label}</Badge>
        <HorizonFit info={info} compact />
      </div>
      <Disclosure summary="Details">
        <PatternDetails info={info} />
      </Disclosure>
    </li>
  );
}
