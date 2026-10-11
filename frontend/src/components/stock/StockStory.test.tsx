import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StockChecks } from "../../api/client";
import { stockRoute } from "../../test/stockRoutes";
import { SAMPLE_STOCK } from "../analysis/samples";
import { StockStory, type LegacyView } from "./StockStory";

// lightweight-charts needs a real canvas; the chart has its own tests.
vi.mock("../../charts/PriceChart", () => ({ PriceChart: () => <div>Price chart</div> }));

const prices = {
  ticker: "RELIANCE.NS",
  interval: "1d",
  source: "yahoo",
  delayed: true,
  last_complete: true,
  freshness: { status: "fresh", reason: "Up to date" },
  fetch_error: null,
  bars: [
    { t: "2026-10-08", open: 1180, high: 1190, low: 1170, close: 1178.5, volume: 1 },
    { t: "2026-10-09", open: 1178, high: 1180, low: 1165, close: 1170.3, volume: 1 },
  ],
};

function bodyFor(url: string): unknown {
  return (
    stockRoute(url) ??
    (url.includes("/market/prices/")
      ? prices
      : url.includes("/series")
        ? { ticker: "RELIANCE.NS", interval: "1d", t: [], columns: {} }
        : url.includes("/analysis/technical/")
          ? { ticker: "RELIANCE.NS", label: "", style: null, timeframes: [], context: { values: {}, observations: [], unavailable: [], levels: [] }, fetch_errors: [], notes: [], disclaimer: "" }
          : url.includes("/market/status")
            ? { generated_at: "", summary: { fresh: 0, stale: 0, unavailable: 0 }, references: [], quotes: [], schedule: {}, last_job: null, last_fundamentals_job: null, notes: [] }
            : { version: 1, styles: {}, risk_levels: {}, disclaimer: "", technical: { thresholds: { rsi_overbought: 70, rsi_oversold: 30 } } })
  );
}

/** `overrides`: URL fragment → body, or [status, body] for an error. */
function mockFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const hit = Object.entries(overrides).find(([k]) => url.includes(k));
      const [status, body] = hit ? (Array.isArray(hit[1]) ? hit[1] : [200, hit[1]]) : [200, bodyFor(url)];
      return new Response(JSON.stringify(body), { status });
    }),
  );
}

function renderStory(view: LegacyView = "signal", ticker = "RELIANCE.NS") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StockStory ticker={ticker} style="positional" view={view} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("StockStory (desktop)", () => {
  it("opens with the header, the Score Shape, the summary and Rewards and Risks", async () => {
    mockFetch();
    renderStory();
    expect(await screen.findByRole("heading", { level: 1, name: "Reliance Industries Ltd" })).toBeInTheDocument();
    const header = screen.getByRole("heading", { level: 1 }).closest("header")!;
    expect(await within(header).findByText("−0.7%")).toBeInTheDocument();
    expect(header).toHaveTextContent("Down −0.7%"); // a word and an arrow, not just red
    expect(screen.getAllByText("Sell / Exit").length).toBeGreaterThan(0);
    expect(screen.getByText("High confidence")).toBeInTheDocument();
    expect(screen.getByText("Your holding")).toBeInTheDocument();

    const shape = await screen.findByRole("img", { name: /^Score Shape for Reliance Industries Ltd/ });
    expect(shape.getAttribute("aria-label")).toContain("total 19 of 36");
    expect(screen.getByText(/passes 18 of the 35 checks/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Risks (5)" })).toBeInTheDocument();
  });

  it("lists every section in a sticky nav with its score", async () => {
    mockFetch();
    renderStory();
    const nav = screen.getByRole("navigation", { name: "Sections" });
    const links = within(nav).getAllByRole("link").map((a) => a.textContent);
    expect(links[0]).toBe("Summary");
    expect(await within(nav).findByText("2/6")).toBeInTheDocument();
    expect(within(nav).getAllByRole("link")).toHaveLength(11);
    expect(within(nav).getByRole("link", { name: "Summary" })).toHaveAttribute("aria-current", "location");
  });

  it("tells each section's story with a chart caption and its checks", async () => {
    mockFetch();
    renderStory();
    const valuation = await screen.findByRole("region", { name: "Valuation" });
    expect(await within(valuation).findByText("2/6 checks")).toBeInTheDocument();
    expect(within(valuation).getByText(/33\.0% above the estimated fair value of ₹879\.77: dearer/)).toBeInTheDocument();
    expect(within(valuation).getByText(/P\/E of 19\.6× is above the sector median of 13\.3× and below/)).toBeInTheDocument();
    expect(within(valuation).getByRole("list", { name: "Valuation checks" })).toBeInTheDocument();

    const health = screen.getByRole("region", { name: "Financial Health" });
    expect(await within(health).findByText("Debt has fallen from 0.47× to 0.44× equity over 3 years.")).toBeInTheDocument();
    expect(within(health).getAllByText("6.12×")).toHaveLength(2); // interest coverage stat and check

    const momentum = screen.getByRole("region", { name: "Momentum" });
    expect(within(momentum).getByRole("img", { name: /^RSI 35\.4: weak/ })).toBeInTheDocument();
  });

  it("keeps the old tabs' content: fundamentals, technical readings, signal details and backtest", async () => {
    mockFetch();
    renderStory("fundamental");
    const fundamentals = (await screen.findByText("F-score and every fundamental figure")).closest("details")!;
    expect(fundamentals).toHaveAttribute("open");
    expect(await within(fundamentals).findByText(/Piotroski F-score/)).toBeInTheDocument();
    expect(screen.getByText("Every technical reading, by timeframe").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Score breakdown and every reading")).toBeInTheDocument();
    expect(screen.getByText("Signal history")).toBeInTheDocument();
    expect(screen.getByText("Backtest the signal rules on RELIANCE.NS")).toBeInTheDocument();
    const action = screen.getByRole("region", { name: "What to do" });
    expect(within(action).getByText("Trailing stop")).toBeInTheDocument();
    expect(within(action).getByText("Suggested trade")).toBeInTheDocument();
  });

  it("explains how to get ownership data when there is none", async () => {
    mockFetch();
    renderStory();
    const own = screen.getByRole("region", { name: "Ownership" });
    expect(await within(own).findByText("No shareholding data")).toBeInTheDocument();
    expect(within(own).getByRole("link", { name: "Upload Screener.in data" })).toHaveAttribute("href", "/import");
  });

  it("drops the company sections for an index and says why", async () => {
    const empty = (s: StockChecks["sections"][number]) => (s.key === "momentum" ? s : { ...s, with_data: 0, score: null, passed: 0, checks: s.checks.map((c) => ({ ...c, status: "no_data" as const })) });
    mockFetch({ "/checks": { ...SAMPLE_STOCK, sections: SAMPLE_STOCK.sections.map(empty) } });
    renderStory("signal", "^NSEI");
    expect(await screen.findByText(/only the Momentum checks apply/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /^Score Shape/ })).not.toBeInTheDocument();
    expect(screen.getByText("0 of 6 checks passed")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(within(nav).queryByRole("link", { name: /Valuation/ })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Momentum/ })).toBeInTheDocument();
  });

  it("shows a retryable error when the checks fail, and keeps the rest of the page", async () => {
    mockFetch({ "/checks": [502, { detail: "Fundamentals timed out" }] });
    renderStory();
    expect((await screen.findAllByText("Couldn't work out the checks")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Retry/ }).length).toBeGreaterThan(0);
    expect(await screen.findByText("Suggested trade")).toBeInTheDocument();
  });
});

describe("StockStory (phone)", () => {
  it("shows one section at a time behind tabs", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined }));
    mockFetch();
    renderStory();
    const tabs = screen.getByRole("tablist", { name: "Sections" });
    expect(within(tabs).getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    fireEvent.click(await within(tabs).findByRole("tab", { name: /Financial Health/ }));
    const panel = screen.getByRole("tabpanel");
    expect(await within(panel).findByRole("heading", { name: "Financial Health" })).toBeInTheDocument();
    expect(within(panel).queryByText("Summary")).not.toBeInTheDocument();
  });

  it("opens the section an old ?view= link pointed at", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined }));
    mockFetch();
    renderStory("backtest");
    expect(screen.getByRole("tab", { name: "Test the rules" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Backtest the signal rules on RELIANCE.NS").closest("details")).toHaveAttribute("open");
  });
});
