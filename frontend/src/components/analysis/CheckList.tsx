import type { CheckResult } from "../../api/client";
import { InfoTip, StatusIcon } from "../ui";

/**
 * A section's pass / fail / no-data checks: icon, the check, one plain-English line, and the
 * actual value against its threshold. Kept in the order the config lists them, so each section
 * reads as a story. `compact` drops the explanation and the figures (for cards).
 */
export function CheckList({ checks, compact = false, label }: { checks: CheckResult[]; compact?: boolean; label?: string }) {
  if (!checks.length) return <p className="text-sm text-fg-muted">No checks for this section.</p>;
  return (
    <ul aria-label={label} className={compact ? "space-y-1" : "divide-y divide-border"}>
      {checks.map((c) => (
        <li key={c.check_id} className={`${compact ? "flex items-start gap-2 text-sm" : "grid grid-cols-[auto_1fr] gap-x-3 py-2.5 sm:grid-cols-[auto_1fr_auto]"}`}>
          <StatusIcon status={c.status} className={compact ? "size-4 mt-0.5" : "size-5"} />
          <div className="min-w-0">
            <p className={`flex items-center gap-1 ${compact ? "" : "text-sm font-medium"} text-fg`}>
              <span>{c.label}</span>
              {c.help && !compact && <InfoTip label={c.label}>{c.help}</InfoTip>}
            </p>
            {!compact && <p className="mt-0.5 text-sm text-fg-muted">{c.explanation}</p>}
          </div>
          {!compact && <Figures c={c} />}
        </li>
      ))}
    </ul>
  );
}

function Figures({ c }: { c: CheckResult }) {
  if (c.status === "no_data" || c.display_value === "—") return <span className="col-start-2 text-xs text-fg-subtle sm:col-start-3 sm:text-right">No data</span>;
  return (
    <dl className="col-start-2 mt-1 flex gap-3 text-xs sm:col-start-3 sm:mt-0 sm:block sm:text-right">
      <div className="flex gap-1 sm:justify-end">
        <dt className="text-fg-subtle">Value</dt>
        <dd className="font-semibold text-fg">{c.display_value}</dd>
      </div>
      {c.display_threshold !== "—" && (
        <div className="flex gap-1 sm:justify-end">
          <dt className="text-fg-subtle">vs</dt>
          <dd className="text-fg-muted">{c.display_threshold}</dd>
        </div>
      )}
    </dl>
  );
}
