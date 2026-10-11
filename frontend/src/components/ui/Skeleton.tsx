import type { ReactNode } from "react";

/** A grey placeholder block shaped like the content that is loading. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div aria-hidden className={`skeleton rounded-control ${className}`} />;
}

/** Wraps placeholders so screen readers hear one "Loading …" instead of nothing. */
export function Loading({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div aria-busy="true" role="status">
      <span className="sr-only">Loading {label}…</span>
      {children}
    </div>
  );
}

/** Lines of text (the last one shorter). */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={`h-3.5 ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

/** A card-shaped placeholder: a title bar, then text lines. */
export function SkeletonCard({ label, lines = 3, chart = false }: { label: string; lines?: number; chart?: boolean }) {
  return (
    <Loading label={label}>
      <div className="space-y-4 rounded-card border border-border bg-surface p-4 sm:p-5">
        <Skeleton className="h-5 w-40" />
        {chart && <Skeleton className="h-48 w-full" />}
        <SkeletonText lines={lines} />
      </div>
    </Loading>
  );
}
