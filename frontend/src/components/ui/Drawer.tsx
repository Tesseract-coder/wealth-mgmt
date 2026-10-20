import { X } from "lucide-react";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/** A panel over the right of the page (full width on a phone). Focus moves in and stays in until
 *  it closes (Escape, the close button or a click outside), then returns where it was. */
export function Drawer({ title, onClose, children, footer }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const before = document.activeElement;
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => {
      if (before instanceof HTMLElement) before.focus();
    };
  }, []);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "Tab" && panel.current) {
      const els = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const first = els[0], last = els.at(-1);
      if (!first || !last) return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKey}
        className="flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-pop"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <h2 id={titleId} className="min-w-0 text-base font-semibold text-fg">
            {title}
          </h2>
          <button type="button" aria-label="Close" onClick={onClose} className="inline-grid size-8 shrink-0 place-items-center rounded-control text-fg-muted hover:bg-surface-2 hover:text-fg">
            <X aria-hidden className="size-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>
        {footer && <footer className="border-t border-border px-4 py-3">{footer}</footer>}
      </div>
    </div>
  );
}
