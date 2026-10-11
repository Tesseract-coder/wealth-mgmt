import { CircleCheck, CircleX, Inbox, Info, RefreshCw, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export type Tone = "error" | "warning" | "success" | "info";

const ALERT: Record<Tone, { cls: string; icon: LucideIcon }> = {
  error: { cls: "border-bad-border bg-bad-soft", icon: CircleX },
  warning: { cls: "border-caution-border bg-caution-soft", icon: TriangleAlert },
  success: { cls: "border-good-border bg-good-soft", icon: CircleCheck },
  info: { cls: "border-neutral-border bg-neutral-soft", icon: Info },
};
const ICON_COLOR: Record<Tone, string> = { error: "text-bad", warning: "text-caution", success: "text-good", info: "text-neutral" };

/** An inline message. Errors are announced immediately (role=alert); the rest politely. */
export function Alert({ tone, title, children }: { tone: Tone; title?: ReactNode; children?: ReactNode }) {
  const { cls, icon: Icon } = ALERT[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex gap-2.5 rounded-control border p-3 text-sm text-fg ${cls}`}>
      <Icon aria-hidden className={`mt-0.5 size-4 shrink-0 ${ICON_COLOR[tone]}`} />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children}
      </div>
    </div>
  );
}

/** Nothing to show yet: say why, and what to do next. */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-card border border-dashed border-border-strong px-6 py-10 text-center">
      <span className="grid size-10 place-items-center rounded-full bg-accent-soft text-accent-text">
        <Icon aria-hidden className="size-5" />
      </span>
      <p className="font-medium text-fg">{title}</p>
      {children && <div className="max-w-md text-sm text-fg-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Something failed: what failed, what to do about it, and a retry when one makes sense. */
export function ErrorState({
  title,
  detail,
  hint,
  onRetry,
  retrying = false,
}: {
  title: ReactNode;
  detail?: ReactNode;
  hint?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  return (
    <div role="alert" className="flex flex-wrap items-start gap-3 rounded-card border border-bad-border bg-bad-soft p-4 text-sm text-fg">
      <CircleX aria-hidden className="mt-0.5 size-5 shrink-0 text-bad" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{title}</p>
        {detail && <p className="text-fg-muted">{detail}</p>}
        {hint && <p>{hint}</p>}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      )}
    </div>
  );
}
