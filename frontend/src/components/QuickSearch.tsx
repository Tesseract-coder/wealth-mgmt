import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { portfolioApi, suggestionTicker, watchlistApi, type Holdings, type Suggestion } from "../api/client";
import { useDebounced } from "../hooks/useDebounced";
import { NAV } from "../lib/nav";

export interface SearchItem {
  key: string;
  group: string;
  label: string;
  detail?: string;
  href: string;
}

const PER_GROUP = 6;
/** A fund comes in many plans and payout options; a few are enough to pick from. */
const FUNDS_SHOWN = 4;
/** Fuzzy matches below this are noise ("ab" matches half the market). */
const MIN_SCORE = 60;

export const stockHref = (ticker: string) => `/analysis/${encodeURIComponent(ticker)}`;

/** "tcs" → TCS.NS; anything with an exchange suffix or an index (^NSEI) is kept as typed. */
export function tickerFromInput(q: string): string | null {
  const t = q.trim().toUpperCase();
  if (!/^\^?[A-Z0-9&.-]{2,20}$/.test(t)) return null;
  return t.includes(".") || t.startsWith("^") ? t : `${t}.NS`;
}

const matches = (needle: string, ...hay: (string | null | undefined)[]) => hay.some((h) => h?.toLowerCase().includes(needle));

/** Everything the search box can offer for `q`: pages, your holdings and watchlist first, then
 *  any NSE or BSE stock or mutual fund. Grouped, a few per group, duplicates dropped. */
export function searchItems(
  q: string,
  holdings: Holdings | undefined,
  watch: string[] | undefined,
  stocks: Suggestion[] | undefined,
  funds: Suggestion[] | undefined,
): SearchItem[] {
  const needle = q.trim().toLowerCase();
  const out: SearchItem[] = [];
  const seen = new Set<string>();
  const add = (group: string, items: SearchItem[]) => {
    let n = 0;
    for (const it of items) {
      if (n >= PER_GROUP || seen.has(it.href)) continue;
      seen.add(it.href);
      out.push({ ...it, group });
      n++;
    }
  };
  const held = (holdings?.stocks ?? []).filter((s) => s.symbol);
  add(
    "Your stocks",
    held
      .filter((s) => !needle || matches(needle, s.symbol, s.name))
      .sort((a, b) => (b.current_value ?? 0) - (a.current_value ?? 0))
      .map((s) => {
        const t = `${s.symbol}${s.exchange === "BSE" ? ".BO" : ".NS"}`;
        return { key: `h:${t}`, group: "", label: s.name, detail: t, href: stockHref(t) };
      }),
  );
  add(
    "Your funds",
    (holdings?.mf ?? [])
      .filter((f) => f.amfi_code && (!needle || matches(needle, f.scheme_name, f.amfi_code)))
      .map((f) => ({ key: `f:${f.amfi_code}`, group: "", label: f.scheme_name, detail: `AMFI ${f.amfi_code}`, href: `/mutual-funds/${f.amfi_code}` })),
  );
  if (needle) {
    add(
      "Watchlist",
      (watch ?? []).filter((t) => matches(needle, t)).map((t) => ({ key: `w:${t}`, group: "", label: t.replace(/\.(NS|BO)$/, ""), detail: t, href: stockHref(t) })),
    );
  }
  add(
    "Pages",
    NAV.filter((n) => !needle || matches(needle, n.label)).map((n) => ({ key: `p:${n.to}`, group: "", label: n.label, href: n.to })),
  );
  if (needle) {
    add(
      "All stocks",
      (stocks ?? [])
        .filter((s) => s.symbol && s.score >= MIN_SCORE)
        .map((s) => ({ key: `s:${suggestionTicker(s)}`, group: "", label: s.name, detail: suggestionTicker(s), href: stockHref(suggestionTicker(s)) })),
    );
    add(
      "All mutual funds",
      (funds ?? [])
        .filter((f) => f.amfi_code && f.score >= MIN_SCORE)
        .slice(0, FUNDS_SHOWN)
        .map((f) => ({ key: `m:${f.amfi_code}`, group: "", label: f.name, detail: `AMFI ${f.amfi_code}`, href: `/mutual-funds/${f.amfi_code}` })),
    );
    const typed = tickerFromInput(q);
    if (typed && !out.some((i) => i.href === stockHref(typed)))
      out.push({ key: `t:${typed}`, group: "Open", label: `Open ${typed}`, detail: "as typed", href: stockHref(typed) });
  }
  return out;
}

/** Consecutive items of one group, with the index of the first (for keyboard navigation). */
function groupsOf(items: SearchItem[]): { group: string; start: number; rows: SearchItem[] }[] {
  const out: { group: string; start: number; rows: SearchItem[] }[] = [];
  items.forEach((it, i) => {
    const last = out.at(-1);
    if (last && last.group === it.group) last.rows.push(it);
    else out.push({ group: it.group, start: i, rows: [it] });
  });
  return out;
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** A search box over the whole app, opened from the header or with Ctrl+K (⌘K on a Mac) or "/". */
export function QuickSearch() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName));
      if ((e.key === "k" || e.key === "K") && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Search stocks, funds and pages"
        aria-keyshortcuts="Control+K Meta+K /"
        className="inline-flex h-9 shrink-0 items-center gap-2 rounded-control border border-border-strong px-2.5 text-sm text-fg-muted hover:bg-surface-2 hover:text-fg"
      >
        <Search aria-hidden className="size-4" />
        <span className="hidden 2xl:inline">Search</span>
        <kbd className="hidden rounded border border-border px-1 font-sans text-[11px] text-fg-subtle lg:inline">{isMac ? "⌘K" : "Ctrl K"}</kbd>
      </button>
      {open && <SearchDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function SearchDialog({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const restore = useRef<Element | null>(null);
  const listId = useId();
  const dq = useDebounced(q.trim(), 200);
  const holdings = useQuery({ queryKey: ["holdings"], queryFn: portfolioApi.holdings });
  const watch = useQuery({ queryKey: ["watch-tickers"], queryFn: watchlistApi.tickers });
  const stocks = useQuery({ queryKey: ["ref", "stock", dq], queryFn: () => portfolioApi.searchSecurities(dq), enabled: dq.length >= 2 });
  const funds = useQuery({ queryKey: ["ref", "scheme", dq], queryFn: () => portfolioApi.searchSchemes(dq), enabled: dq.length >= 3 });
  const items = useMemo(
    () => searchItems(q, holdings.data, watch.data, dq === q.trim() ? stocks.data : undefined, dq === q.trim() ? funds.data : undefined),
    [q, dq, holdings.data, watch.data, stocks.data, funds.data],
  );
  const searching = q.trim().length >= 2 && (dq !== q.trim() || stocks.isFetching || funds.isFetching);

  useEffect(() => {
    restore.current = document.activeElement;
    input.current?.focus();
    return () => {
      if (restore.current instanceof HTMLElement) restore.current.focus();
    };
  }, []);
  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, listId]);

  const go = (it: SearchItem | undefined) => {
    if (!it) return;
    onClose();
    navigate(it.href);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, items.length - 1));
    else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
    else if (e.key === "Enter") go(items[active]);
    else if (e.key === "Escape") onClose();
    else if (e.key === "Tab") {
      /* the dialog has one control: keep focus in it */
    } else return;
    e.preventDefault();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[12vh]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label="Search" className="w-full max-w-xl overflow-hidden rounded-card border border-border bg-surface shadow-pop">
        <div className="flex items-center gap-2 border-b-2 border-border px-3 focus-within:border-accent">
          <Search aria-hidden className="size-4 shrink-0 text-fg-subtle" />
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={items.length ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
            aria-label="Search stocks, funds and pages"
            placeholder="Stock, fund or page…"
            className="h-12 w-full bg-transparent text-sm text-fg placeholder:text-fg-subtle"
            // The row's accent border shows focus instead of an outline inside the box.
            style={{ outline: "none" }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
          />
          <kbd className="rounded border border-border px-1 text-[11px] text-fg-subtle">Esc</kbd>
        </div>
        <div id={listId} role="listbox" aria-label="Results" className="max-h-[60vh] overflow-y-auto py-1 text-sm">
          {groupsOf(items).map(({ group, start, rows }) => (
            <div key={group} role="group" aria-labelledby={`${listId}-g-${start}`}>
              <div id={`${listId}-g-${start}`} className="px-3 pb-1 pt-2 text-xs font-medium text-fg-subtle">
                {group}
              </div>
              {rows.map((it, j) => {
                const i = start + j;
                return (
                  <div
                    key={it.key}
                    id={`${listId}-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => setActive(i)}
                    onClick={() => go(it)}
                    className={`mx-1 flex cursor-pointer items-baseline justify-between gap-3 rounded-control px-2 py-1.5 ${i === active ? "bg-accent-soft text-accent-text" : "text-fg"}`}
                  >
                    <span className="truncate">{it.label}</span>
                    {it.detail && <span className="shrink-0 font-mono text-xs text-fg-subtle">{it.detail}</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p className="border-t border-border px-3 py-1.5 text-xs text-fg-subtle" aria-live="polite">
          {searching ? "Searching every NSE and BSE stock and fund…" : items.length ? "↑ ↓ to move · Enter to open" : "Nothing matches. Type a symbol, a company or a fund name."}
        </p>
      </div>
    </div>
  );
}
