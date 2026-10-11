import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Candidate, Job, ScreenerConfig, ScreenField, ScreenResult, Watchlist } from "../api/client";
import { parseSel } from "../pages/Screener";
import { WatchlistTable } from "../pages/Watchlist";
import { FilterBuilder, fromDrafts, toDraft, type Draft } from "./FilterBuilder";
import { ScanProgress, scanMinutes } from "./ScanPanel";
import { funnel, keyFacts, ScreenResults, shapeFromFacts } from "./ScreenResults";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const fields: ScreenField[] = [
  { key: "rsi", label: "RSI (14)", group: "Technical", unit: "", help: "0–100", financial_exempt: false },
  { key: "roe", label: "ROE", group: "Fundamental", unit: "%", help: "Return on equity", financial_exempt: false },
];
const ops = { gt: ">", gte: "≥", lt: "<", lte: "≤", between: "between" } as const;

describe("Filter builder", () => {
  it("turns rows into filters and reports the first problem", () => {
    expect(fromDrafts([{ field: "rsi", op: "between", a: "35", b: "45" }], fields)).toEqual({
      filters: [{ field: "rsi", op: "between", value: [35, 45] }],
      error: null,
    });
    expect(fromDrafts([{ field: "roe", op: "gte", a: "abc", b: "" }], fields).error).toBe("ROE: enter a number");
    expect(fromDrafts([{ field: "rsi", op: "between", a: "50", b: "" }], fields).error).toMatch(/both ends/);
    expect(fromDrafts([{ field: "rsi", op: "between", a: "50", b: "40" }], fields).error).toMatch(/low end is above/);
    expect(fromDrafts([], fields).error).toBe("Add at least one condition");
    expect(toDraft({ field: "rsi", op: "between", value: [35, 45] })).toEqual({ field: "rsi", op: "between", a: "35", b: "45" });
  });

  it("adds, edits and removes rows", () => {
    let latest: Draft[] = [];
    function Host() {
      const [d, setD] = useState<Draft[]>([]);
      latest = d;
      return <FilterBuilder fields={fields} ops={ops} drafts={d} onChange={setD} />;
    }
    render(<Host />);
    fireEvent.click(screen.getByRole("button", { name: "+ Add condition" }));
    const row = screen.getByRole("group", { name: "Condition 1" });
    fireEvent.change(within(row).getByLabelText("Field"), { target: { value: "roe" } });
    fireEvent.change(within(row).getByLabelText("Value"), { target: { value: "15" } });
    expect(within(row).getByText("%")).toBeInTheDocument();
    expect(fromDrafts(latest, fields).filters).toEqual([{ field: "roe", op: "gte", value: 15 }]);
    fireEvent.change(within(row).getByLabelText("Condition"), { target: { value: "between" } });
    expect(within(row).getByLabelText("To")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove condition 1" }));
    expect(latest).toEqual([]);
  });
});

const cand: Candidate = {
  rank: 1, ticker: "TITAN.NS", symbol: "TITAN", label: "Titan", sector: "Consumer Durables", held: false, watched: false,
  signal: "buy", signal_label: "Buy / Add", rule: "Composite 74 ≥ buy threshold 70", confidence: "high", composite: 74,
  technical: 70, fundamental: 80, bullish: ["ROE 30%: high"], bearish: ["P/E rich"], flags: [], passed: ["ROE ≥ 15%"],
  levels: {
    interval: "1d", close: 3000, atr: 60, entry_low: 2970, entry_high: 3000, entry_basis: "Entry zone from close − 0.5 × ATR",
    stop: 2880, stop_pct: -4, targets: [{ label: "2R", price: 3240, pct: 8 }], basis: "b",
  },
  impact: { sector: "Consumer Durables", amount: 9000, quantity: 3, before: 0.05, after: 0.13, over_limit: false, text: "A starter position…" },
  facts: {}, price_as_of: "2026-10-09",
};  // prettier-ignore

const result: ScreenResult = {
  scan: {
    id: 1, job_id: 1, universe: "nifty500", universe_label: "Nifty 500", style: "swing", style_label: "Swing", risk: "medium",
    risk_label: "Medium", fetch: "missing", status: "complete", created_at: "2026-10-10T16:00:00+05:30",
    finished_at: "2026-10-10T16:40:00+05:30", total: 501, scored: 480, notes: [],
  },
  title: "Quality at fair price", filters: ["ROE ≥ 15%"], prefilters: ["Market cap ≥ ₹5,000 Cr"],
  counts: { universe: 501, not_scored: 21, held: 5, prefilter: 100, signal: 50, filters: 300, missing_data: 24, passed: 1 },
  candidates: [cand], near_misses: [{ ticker: "ITC.NS", label: "ITC", composite: 60, failed: ["ROE ≥ 15% (no data)"] }],
  stale_note: null, disclaimer: "x",
};  // prettier-ignore

describe("Screen results", () => {
  it("shows the funnel, signal as text, entry/stop/targets and the sector effect", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })));
    wrap(<ScreenResults r={result} includeHeld={false} />);
    expect(screen.getByText(/501 in the universe → 21 not scored .* → 1 passed/)).toBeInTheDocument();
    // Cards first: shape (if the scan has one), signal, entry zone, key facts, portfolio effect.
    const ideas = within(screen.getByRole("list", { name: "Ideas" }));
    expect(ideas.getByText("Buy / Add")).toBeInTheDocument();
    expect(ideas.getAllByText("₹2,970.00 – ₹3,000.00").length).toBeGreaterThan(0); // entry zone
    expect(ideas.getByText("Re-scan for a shape")).toBeInTheDocument();
    expect(ideas.getAllByText("ROE 30%: high")).toHaveLength(2); // key fact without a shape, and in Why
    expect(ideas.getByRole("figure", { name: /Consumer Durables share of your portfolio/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Buy / Add")).toBeInTheDocument();
    expect(table.getByText("₹2,970.00 – ₹3,000.00")).toBeInTheDocument();
    expect(table.getByText("₹2,880.00 (−4.0%)")).toBeInTheDocument();
    expect(table.getByText("Consumer Durables: 5.0% → 13.0%")).toBeInTheDocument();
    expect(table.getByRole("link", { name: "Titan" })).toHaveAttribute("href", "/analysis/TITAN.NS");
    expect(screen.getByText(/failed ROE ≥ 15% \(no data\)/)).toBeInTheDocument();
    const btn = await table.findByRole("button", { name: /Watch/ });
    await waitFor(() => expect(btn).toBeEnabled());
  });

  it("adds an idea to the watchlist with its screen as the source", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
      new Response(JSON.stringify(init?.method === "POST" ? {} : url.endsWith("/tickers") && fetchMock.mock.calls.length > 2 ? ["TITAN.NS"] : []), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    wrap(<ScreenResults r={result} includeHeld={false} />);
    const btn = await within(screen.getByRole("list", { name: "Ideas" })).findByRole("button", { name: /Watch/ });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getAllByText(/Watching/).length).toBeGreaterThan(0));
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(post[0]).toBe("/api/watchlist");
    expect(JSON.parse(String(post[1]?.body))).toEqual({ ticker: "TITAN.NS", source: "Screener: Quality at fair price" });
  });

  it("reads the Score Shape and key facts from the scan's facts", () => {
    const facts = { axis_valuation: 4, axis_growth: 2, axis_past: 6, axis_health: 5, axis_momentum: 3, axis_dividends: 1, axis_total: 21 };
    expect(shapeFromFacts(facts)?.total).toBe(21);
    expect(shapeFromFacts({})).toBeNull();
    expect(keyFacts({ ...cand, facts })).toEqual(["Strongest: Past Performance 6/6", "Weakest: Dividends 1/6"]);
  });

  it("says when held stocks are excluded", () => {
    expect(funnel(result.counts, false)).toContain("5 you already hold");
    expect(funnel(result.counts, true)).not.toContain("5 you already hold");
  });
});

describe("Scan progress", () => {
  it("estimates a first scan's duration", () => {
    expect(scanMinutes(500, 6.5)).toBe(54);
    expect(scanMinutes(3, 6.5)).toBe(1);
    expect(scanMinutes(0, 6.5)).toBe(0);
  });

  it("shows a progress bar and a Stop button", () => {
    const job: Job = {
      id: 3, kind: "screener", status: "running", trigger: "manual", params: {}, created_at: "", started_at: null, finished_at: null,
      done: 250, total: 1000, message: "Data 250/500: TCS", errors: ["INFY prices: timeout"],
    };  // prettier-ignore
    const stop = vi.fn();
    render(<ScanProgress job={job} onStop={stop} stopping={false} />);
    expect(screen.getByRole("progressbar", { name: "Scan progress" })).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText(/Data 250\/500: TCS · 25%/)).toBeInTheDocument();
    expect(screen.getByText(/1 stock\(s\) could not be downloaded/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(stop).toHaveBeenCalled();
  });
});

describe("Screen selection", () => {
  const config = {
    presets: [{ key: "top_scores" }, { key: "growth" }],
    screens: [{ id: 4 }],
  } as unknown as ScreenerConfig;
  it("reads the URL, falling back to the first preset", () => {
    expect(parseSel("preset:growth", config)).toEqual({ kind: "preset", key: "growth" });
    expect(parseSel("saved:4", config)).toEqual({ kind: "saved", id: 4 });
    expect(parseSel("saved:9", config)).toEqual({ kind: "preset", key: "top_scores" });
    expect(parseSel("custom", config)).toEqual({ kind: "custom" });
    expect(parseSel(null, config)).toEqual({ kind: "preset", key: "top_scores" });
  });
});

describe("Watchlist", () => {
  const d: Watchlist = {
    style_label: "Swing", risk_label: "Medium", fetching_job_id: null, disclaimer: "x",
    items: [
      {
        ticker: "TITAN.NS", label: "Titan", note: "results on 20th", source: "Screener: Growth", added_at: "2026-10-01T10:00:00+05:30",
        added_price: 2800, added_signal: "hold", added_signal_label: "Hold", added_score: 60, held: false, status: "ok",
        signal: "buy", signal_label: "Buy / Add", rule: "r", confidence: "medium", composite: 72, score_change: 12, price: 3000,
        price_as_of: "2026-10-09", price_change_pct: 7.14, signal_changed_since_added: true,
        last_change: { previous: "hold", previous_label: "Hold", current: "buy", current_label: "Buy / Add", day: "2026-10-08" },
        stop: 2880, stop_breached: false, bullish: [], bearish: [], flags: [], sector: "Consumer Durables",
        price_freshness: { status: "fresh", reason: "ok" },
      },
      {
        ticker: "NEW.NS", label: "Newco", note: null, source: "Manual", added_at: "2026-10-10T10:00:00+05:30", added_price: null,
        added_signal: null, added_signal_label: null, added_score: null, held: false, status: "no_data", signal: null,
        signal_label: null, rule: null, confidence: null, composite: null, score_change: null, price: null, price_as_of: null,
        price_change_pct: null, signal_changed_since_added: false, last_change: null, stop: null, stop_breached: false,
        bullish: [], bearish: [], flags: [], sector: null, price_freshness: null,
      },
    ],
  };  // prettier-ignore

  it("shows the live signal, what changed since it was added, and missing data", () => {
    wrap(<WatchlistTable d={d} />);
    expect(screen.getAllByText("Buy / Add")).toHaveLength(2); // the pill, and the last change
    expect(screen.getByText("Was Hold when added")).toBeInTheDocument();
    expect(screen.getByText("+12.0 since added")).toBeInTheDocument();
    expect(screen.getByText("+7.1% since added")).toBeInTheDocument();
    expect(screen.getByText("on 08 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText(/No prices downloaded yet/)).toBeInTheDocument();
    expect(screen.getByText("results on 20th")).toBeInTheDocument();
  });

  it("removes a stock", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<WatchlistTable d={d} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Titan" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/watchlist/TITAN.NS", { method: "DELETE" }));
  });

  it("has an empty state", () => {
    wrap(<WatchlistTable d={{ ...d, items: [] }} />);
    expect(screen.getByText(/Nothing on your watchlist yet/)).toBeInTheDocument();
  });
});
