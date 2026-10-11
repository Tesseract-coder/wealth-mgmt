import type { ReactNode } from "react";
import type { CheckStatus, SectionResult } from "../../api/client";
import { InfoTip } from "../ui";
import { formatScore, stepFor } from "./ScoreShape";

/**
 * One segment per check: filled for a pass (in the section's score colour), outlined for a fail,
 * dashed for no data. The text beside it says the same thing, so colour is never the only signal.
 */
export function CheckBar({ statuses, step }: { statuses: CheckStatus[]; step: number | null }) {
  const passed = statuses.filter((s) => s === "pass").length;
  const failed = statuses.filter((s) => s === "fail").length;
  const missing = statuses.length - passed - failed;
  const fill = step ? `var(--score-${step})` : "var(--neutral)";
  return (
    <span
      role="img"
      aria-label={`${passed} passed, ${failed} failed${missing ? `, ${missing} no data` : ""}`}
      className="inline-flex gap-0.5"
    >
      {/* Passes first so the bar fills from the left like a gauge. */}
      {[...statuses].sort((a, b) => ORDER[a] - ORDER[b]).map((s, i) => (
        <span
          key={i}
          data-status={s}
          className={`h-2 w-3 rounded-[2px] border ${s === "no_data" ? "border-dashed border-border-strong" : s === "fail" ? "border-border-strong" : "border-transparent"}`}
          style={s === "pass" ? { background: fill } : undefined}
        />
      ))}
    </span>
  );
}

const ORDER: Record<CheckStatus, number> = { pass: 0, fail: 1, no_data: 2 };

/**
 * The heading of one analysis section: name, the question it answers, "4/6 checks" with a small
 * bar, and the axis score that feeds the Score Shape.
 */
export function SectionHeader({
  section,
  id,
  max = 6,
  level = 2,
  actions,
}: {
  section: SectionResult;
  id?: string;
  max?: number;
  level?: 2 | 3;
  actions?: ReactNode;
}) {
  const H = level === 2 ? "h2" : "h3";
  const total = section.checks.length;
  const missing = total - section.with_data;
  const step = section.score === null ? null : stepFor(section.score, max);
  const exact = section.with_data ? (section.passed / section.with_data) * max : 0;
  const how =
    section.score === null
      ? `Too few checks had data to score this section (${section.with_data} of ${total}).`
      : missing
        ? `Scored on the ${section.with_data} checks with data: ${section.passed} ÷ ${section.with_data} × ${max} = ${formatScore(Math.round(exact * 10) / 10)}, rounded to ${section.score}.`
        : `${section.passed} of ${total} checks passed, so the axis scores ${section.score}/${max}.`;

  return (
    <header id={id} className="scroll-mt-24">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <H className="text-lg font-semibold text-fg">{section.label}</H>
          <p className="text-sm text-fg-muted">{section.question}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {actions}
          <div className="flex flex-col items-end gap-1">
            <span className="text-sm font-semibold text-fg">
              {section.passed}/{total} checks
              {missing > 0 && <span className="font-normal text-fg-subtle"> · {missing} no data</span>}
            </span>
            <CheckBar statuses={section.checks.map((c) => c.status)} step={step} />
          </div>
          <span className="inline-flex items-center gap-1 rounded-control border border-border bg-surface-2 px-2 py-1 text-xs font-medium text-fg-muted">
            {section.score === null ? "Not enough data" : (
              <>
                Score <span className="font-semibold text-fg">{section.score}/{max}</span>
              </>
            )}
            <InfoTip label={`${section.label} score`}>{how}</InfoTip>
          </span>
        </div>
      </div>
      {/* With no score the badge already says "Not enough data". */}
      {(section.caption || (section.note && section.score !== null)) && (
        <p className="mt-1 text-xs text-fg-subtle">{[section.caption, section.score !== null && section.note].filter(Boolean).join(" ")}</p>
      )}
    </header>
  );
}
