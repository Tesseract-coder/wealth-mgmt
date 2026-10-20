import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Overview, portfolioRisks } from "../../pages/Overview";
import { SAMPLE_HOLDINGS } from "../analysis/samples";
import { sortHoldings } from "../HoldingsTable";
import { HoldingsView } from "./HoldingsView";
import { SAMPLE_ACTIONS, SAMPLE_SIGNALS, SAMPLE_SUMMARY } from "./samples";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={node} />
          <Route path="/analysis/:ticker" element={<p>detail page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const shapes = new Map(SAMPLE_HOLDINGS.holdings.map((h) => [h.ticker, h]));
const cardNames = () => screen.getAllByRole("article").map((a) => within(a).getByRole("heading").textContent);

describe("Holdings view", () => {
  it("shows each holding as a card with its shape, signal, P&L, invested, today, PEG and two key facts", () => {
    wrap(<HoldingsView d={SAMPLE_SIGNALS} shapes={SAMPLE_HOLDINGS.holdings} layout="cards" onLayout={() => undefined} />);
    const card = screen.getByRole("heading", { name: "Reliance Industries Ltd" }).closest("article")!;
    expect(within(card).getByRole("img", { name: /^Score Shape for Reliance Industries Ltd: .*total 19 of 36/ })).toBeInTheDocument();
    expect(within(card).getByText("Sell / Exit")).toBeInTheDocument();
    expect(within(card).getAllByText("Down")).toHaveLength(2); // the loss and today's fall say so in words
    expect(within(card).getByText("Invested")).toBeInTheDocument();
    expect(within(card).getByText("Today")).toBeInTheDocument();
    expect(within(card).getByText("2.98")).toHaveAttribute("title", expect.stringContaining("Current P/E ÷ expected growth"));
    expect(within(card).getByText("Strongest: Financial Health 6/6")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Reliance Industries Ltd" })).toHaveAttribute("href", "/analysis/RELIANCE.NS");
  });

  it("filters with chips: Buy/Hold/Reduce/Sell, sector and confidence", () => {
    wrap(<HoldingsView d={SAMPLE_SIGNALS} shapes={SAMPLE_HOLDINGS.holdings} layout="cards" onLayout={() => undefined} />);
    const signal = screen.getByRole("group", { name: "Signal" });
    const sell = within(signal).getByRole("button", { name: /^Sell/ });
    fireEvent.click(sell);
    expect(sell).toHaveAttribute("aria-pressed", "true");
    expect(cardNames()).toEqual(["Reliance Industries Ltd", "HDFC Bank Ltd"]); // same signal: bigger weight first
    fireEvent.click(within(signal).getByRole("button", { name: /^Reduce/ }));
    expect(cardNames()).toHaveLength(3);
    fireEvent.click(within(screen.getByRole("group", { name: "Sector" })).getByRole("button", { name: /^Information Technology/ }));
    expect(cardNames()).toEqual(["Infosys Ltd"]);
    const confidence = screen.getByRole("group", { name: "Confidence" });
    expect(within(confidence).queryByRole("button", { name: /^High/ })).not.toBeInTheDocument(); // none to show
    fireEvent.click(within(screen.getByRole("group", { name: "Signal" })).getByRole("button", { name: /^Reduce/ }));
    expect(screen.getByText("No holdings match")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(cardNames()).toHaveLength(4);
  });

  it("shows the most-held sectors first and folds the rest away", () => {
    const base = SAMPLE_SIGNALS.holdings[0]!;
    const holdings = Array.from({ length: 11 }, (_, i) => ({ ...base, ticker: `S${i}.NS`, label: `Stock ${i}`, sector: i < 2 ? "Banks" : `Sector ${String.fromCharCode(65 + i)}` }));
    wrap(<HoldingsView d={{ ...SAMPLE_SIGNALS, holdings }} shapes={[]} layout="cards" onLayout={() => undefined} />);
    const group = screen.getByRole("group", { name: "Sector" });
    const names = () => within(group).getAllByRole("button", { pressed: false }).map((b) => b.textContent);
    expect(names()[0]).toBe("Banks2");
    expect(within(group).getAllByRole("button", { pressed: false })).toHaveLength(8);
    fireEvent.click(within(group).getByRole("button", { name: "2 more" }));
    expect(within(group).getAllByRole("button", { pressed: false })).toHaveLength(10);
    fireEvent.click(within(group).getByRole("button", { name: /Sector K/ }));
    fireEvent.click(within(group).getByRole("button", { name: "Fewer" }));
    expect(within(group).getByRole("button", { name: /Sector K/ })).toHaveAttribute("aria-pressed", "true"); // a chosen sector stays
  });

  it("sorts by total score or any axis, missing shapes last", () => {
    expect(sortHoldings(SAMPLE_SIGNALS.holdings, "shape", -1, shapes).map((h) => h.ticker)).toEqual(["TCS.NS", "HDFCBANK.NS", "INFY.NS", "RELIANCE.NS"]);
    expect(sortHoldings(SAMPLE_SIGNALS.holdings, "axis:valuation", -1, shapes)[0]!.ticker).toBe("HDFCBANK.NS");
    expect(sortHoldings(SAMPLE_SIGNALS.holdings, "shape", 1, new Map([["TCS.NS", shapes.get("TCS.NS")!]])).map((h) => h.ticker)[0]).toBe("TCS.NS");

    wrap(<HoldingsView d={SAMPLE_SIGNALS} shapes={SAMPLE_HOLDINGS.holdings} layout="cards" onLayout={() => undefined} />);
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "axis:past" } });
    expect(["Tata Consultancy Services Ltd", "Infosys Ltd"]).toContain(cardNames()[0]); // both 6/6 on Past Performance
    fireEvent.click(screen.getByRole("button", { name: /press for low to high/ }));
    expect(cardNames()[0]).toBe("HDFC Bank Ltd");
  });

  it("switches to a table with a small shape column and keeps every column", () => {
    const onLayout = vi.fn();
    const { rerender } = wrap(<HoldingsView d={SAMPLE_SIGNALS} shapes={SAMPLE_HOLDINGS.holdings} layout="cards" onLayout={onLayout} />);
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    expect(onLayout).toHaveBeenCalledWith("table");
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <HoldingsView d={SAMPLE_SIGNALS} shapes={SAMPLE_HOLDINGS.holdings} layout="table" onLayout={onLayout} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Stock", "Shape", "Signal", "Confidence", "Score", "Tech", "Fund", "Qty", "Avg price", "LTP", "Invested", "Today", "P&L", "Weight", "PEG", "Suggested", "Prices"]);
    expect(screen.getByText("19")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Score Shape for Tata Consultancy/ })).toHaveAttribute("width", "32");
  });
});

describe("Overview", () => {
  function mockApi(summary = SAMPLE_SUMMARY) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const body = url.endsWith("/health")
          ? { status: "ok" }
          : url.endsWith("/settings/profile")
            ? { style: "positional", risk: "medium", custom_technical_weight: 0.5, gsheet_url: null, onboarded: true, updated_at: "" }
            : url.endsWith("/config")
              ? { version: 1, styles: {}, risk_levels: {}, disclaimer: "" }
              : url.endsWith("/portfolio/summary")
                ? summary
                : url.endsWith("/portfolio/actions")
                  ? SAMPLE_ACTIONS
                  : url.includes("/analysis/checks/holdings")
                    ? SAMPLE_HOLDINGS
                    : url.includes("/analysis/signals/holdings")
                      ? SAMPLE_SIGNALS
                      : {};
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
  }

  it("opens with the portfolio shape and figures, then action needed, rewards and risks, charts and holdings", async () => {
    mockApi();
    wrap(<Overview />);
    const shape = await screen.findByRole("img", { name: /^Score Shape for your stocks/ });
    expect(shape.getAttribute("aria-label")).toContain("total 23.4 of 36");
    const hero = screen.getByRole("region", { name: "Portfolio" });
    expect(within(hero).getByText("₹6,12,221")).toBeInTheDocument();
    expect(within(hero).getByText("Unrealised P&L")).toBeInTheDocument();
    expect(within(hero).getByText(/Prices as of/)).toBeInTheDocument();

    expect(await screen.findByText(/^7 high, 0 medium, 0 low\./)).toBeInTheDocument();
    expect(screen.getAllByText("High").length).toBe(7);
    const actions = screen.getByRole("heading", { name: "Action needed" }).closest("section")!;
    expect(within(actions).getByRole("link", { name: "Reliance Industries Ltd" })).toHaveAttribute("href", "/analysis/RELIANCE.NS");

    expect(screen.getByRole("heading", { name: "Rewards (2)" })).toBeInTheDocument();
    expect(screen.getByText(/Mutual funds \(₹2,24,053\) have their own shapes/)).toBeInTheDocument();
    expect(screen.getByText(/^Your biggest sector is/)).toBeInTheDocument();
    expect(screen.getByText(/so you're (ahead|behind|level)/)).toBeInTheDocument();

    expect(await screen.findByRole("heading", { name: "Biggest holdings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View all/ })).toHaveAttribute("href", "/holdings");
  });

  it("explains the next step when there is nothing imported", async () => {
    mockApi({ ...SAMPLE_SUMMARY, total_value: 0, stock_value: 0, fund_value: 0 });
    wrap(<Overview />);
    expect(await screen.findByText("No holdings yet")).toBeInTheDocument();
    expect(screen.getByText(/Import your Groww holdings to see your portfolio score/)).toBeInTheDocument();
  });

  it("merges limit warnings into the risks without repeating them", () => {
    const w = "Financial Services is 34% of your portfolio, above your 30% sector limit";
    expect(portfolioRisks({ ...SAMPLE_HOLDINGS, risks: [w, "x"] }, { ...SAMPLE_SUMMARY, warnings: [w] })).toEqual([w, "x"]);
  });

  it("drops a checks risk that a limit warning already states in other words", () => {
    const warnings = ["BSE is 30.5% of your portfolio, above your 20% limit per stock (High risk)", "Financial Services is 54.3% of your portfolio, above your 40% sector limit"];
    const risks = ["Over-exposed to Financial Services: 54% vs your 40% limit.", "BSE is 30.5% of the portfolio, above your 20% limit per stock.", "Over-exposed to IT: 45% vs your 40% limit.", "2 holdings with a Sell or Reduce signal: A, B."];
    expect(portfolioRisks({ ...SAMPLE_HOLDINGS, risks }, { ...SAMPLE_SUMMARY, warnings })).toEqual([...warnings, risks[2], risks[3]]);
  });
});

describe("Stale data notice", () => {
  it("names what's out of date and why", async () => {
    const { staleLines } = await import("../StaleNotice");
    const q = (code: string, kind: "stock" | "mf", status: "fresh" | "stale" | "unavailable", reason: string) => ({ kind, code, label: code, price: 1, previous: 1, change_pct: 0, as_of: "2026-10-07", source: "yahoo", freshness: { status, reason } });
    const s = {
      generated_at: "", summary: { fresh: 1, stale: 1, unavailable: 1 }, references: [], schedule: {} as never, last_job: null, last_fundamentals_job: null, notes: [],
      quotes: [q("ITC.NS", "stock", "fresh", "ok"), q("TATAMOTORS.NS", "stock", "stale", "2 days old: Yahoo Finance did not respond."), q("Axis ELSS", "mf", "unavailable", "No NAV downloaded yet")],
    };
    expect(staleLines(s).lines).toEqual([
      "Price data for TATAMOTORS is out of date: 2 days old: Yahoo Finance did not respond.",
      "NAV for Axis ELSS is unavailable: No NAV downloaded yet.",
    ]);
  });
});
