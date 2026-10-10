import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { dashboardApi, type Actions, type Severity } from "../api/client";
import { Alert, Card } from "./ui";

const SEV: Record<Severity, { label: string; icon: string; cls: string }> = {
  high: { label: "High", icon: "⛔", cls: "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200" },
  medium: { label: "Medium", icon: "⚠", cls: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200" },
  low: { label: "Low", icon: "ℹ", cls: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200" },
};

export function SeverityTag({ s }: { s: Severity }) {
  const v = SEV[s];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-xs font-medium ${v.cls}`}>
      <span aria-hidden="true">{v.icon}</span>
      {v.label}
    </span>
  );
}

export function ActionList() {
  const q = useQuery({ queryKey: ["actions"], queryFn: dashboardApi.actions });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card title="Action needed">Checking your holdings…</Card>;
  return <ActionListBody d={q.data} />;
}

export function ActionListBody({ d, limit = 12 }: { d: Actions; limit?: number }) {
  const counts = { high: 0, medium: 0, low: 0 } as Record<Severity, number>;
  d.actions.forEach((a) => counts[a.severity]++);
  const shown = d.actions.slice(0, limit);
  return (
    <Card
      title="Action needed"
      actions={<span className="text-xs text-slate-500">{d.style_label} style · {d.risk_label} risk · most severe first</span>}
    >
      {d.actions.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing needs attention under your current profile.</p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-600 dark:text-slate-400">
            {counts.high} high, {counts.medium} medium, {counts.low} low.
          </p>
          <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
            {shown.map((a, i) => (
              <li key={`${a.subject}-${a.title}-${i}`} className="flex flex-wrap items-start gap-2 py-2">
                <SeverityTag s={a.severity} />
                <div className="min-w-0 flex-1">
                  <div>
                    <span className="font-medium">{a.title}</span>
                    {" · "}
                    {a.link ? (
                      <Link className="underline" to={a.link}>
                        {a.subject}
                      </Link>
                    ) : (
                      a.subject
                    )}
                  </div>
                  <div className="text-xs text-slate-600 dark:text-slate-400">{a.detail}</div>
                </div>
              </li>
            ))}
          </ul>
          {d.actions.length > limit && (
            <p className="mt-2 text-xs text-slate-500">
              {d.actions.length - limit} more. See <Link className="underline" to="/holdings">Holdings</Link> and{" "}
              <Link className="underline" to="/mutual-funds">Mutual funds</Link>.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
