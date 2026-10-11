import type { ReactNode } from "react";

/** The one plain-English sentence under a chart that says what it means, plus where the data came from. */
export function ChartCaption({ children, source, className = "" }: { children: ReactNode; source?: ReactNode; className?: string }) {
  return (
    <figcaption className={`mt-2 text-sm text-fg-muted ${className}`}>
      {children}
      {source && <span className="mt-0.5 block text-xs text-fg-subtle">Source: {source}</span>}
    </figcaption>
  );
}

/**
 * A chart with a title and its caption. `label` describes the chart for screen readers; the
 * caption is read too, so it should carry the takeaway.
 */
export function ChartFigure({
  title,
  label,
  caption,
  source,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  label: string;
  caption: ReactNode;
  source?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <figure aria-label={label} className={`min-w-0 ${className}`}>
      {(title || actions) && (
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          {title && <h3 className="text-sm font-semibold text-fg">{title}</h3>}
          {actions}
        </div>
      )}
      {children}
      <ChartCaption source={source}>{caption}</ChartCaption>
    </figure>
  );
}
