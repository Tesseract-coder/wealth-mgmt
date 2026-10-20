import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppConfig, HoldingSignal, HoldingSignals, Profile, Thresholds } from "../api/client";
import { fromDisplay, ThresholdsForm, toDisplay } from "../pages/Settings";
import { ProfileForm } from "../pages/Onboarding";
import { ActionListBody } from "./ActionList";
import { sortHoldings } from "./HoldingsTable";
import { HoldingsView } from "./portfolio/HoldingsView";
import { SAMPLE_HOLDINGS } from "./analysis/samples";
import { SAMPLE_SIGNALS } from "./portfolio/samples";

function wrap(node: ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={node} />
          <Route path="/analysis/:ticker" element={<p>detail page</p>} />
          <Route path="/import" element={<p>import page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

const base: HoldingSignal = {
  ticker: "A.NS", label: "Alpha", signal: "hold", signal_label: "Hold", rule: "Composite 52 is between 45 and 70",
  composite: 52, technical: 40, fundamental: 70, confidence: "medium", weight: 0.05, max_weight: 0.12, quantity: 10,
  avg_price: 100, price: 110, invested: 1000, value: 1100, pnl: 100, pnl_pct: 10, day_change: 20, day_change_pct: 1.85, peg: 1.2, peg_basis: null, sector: "IT", flags: [], top_bullish: [],
  top_bearish: [], rebalance: { action: "none", quantity: 0, value: null, target_weight: null, text: "No change suggested." },
  stop: 95, stop_breached: false, price_freshness: { status: "fresh", reason: "ok" },
};

const holdings: HoldingSignal[] = [
  base,
  { ...base, ticker: "B.NS", label: "Beta Bank", signal: "sell", signal_label: "Sell / Exit", composite: 30, weight: 0.15, pnl: -500, pnl_pct: -20, sector: "Financial Services", flags: [{ key: "pledge_severe", severe: true, text: "Promoter pledge 60%" }] },
  { ...base, ticker: "C.NS", label: "Gamma", signal: "no_signal", signal_label: "No signal", composite: null, technical: null, fundamental: null, confidence: null, weight: 0.02, sector: "IT" },
];

const d: HoldingSignals = {
  style: "long_term", style_label: "Long-term", risk: "medium", risk_label: "Medium", technical_weight: 0.3, weight_base: "portfolio",
  total_value: 20000, stock_value: 12000, fund_value: 8000, sectors: [], holdings, notes: [], disclaimer: "x",
};

const names = () => screen.getAllByRole("row").slice(1, -1).map((r) => within(r).getAllByRole("link")[0]?.textContent);

describe("Holdings table", () => {
  it("sorts by signal urgency by default, with missing values last either way", () => {
    expect(sortHoldings(holdings, "composite", -1).map((h) => h.label)).toEqual(["Alpha", "Beta Bank", "Gamma"]);
    expect(sortHoldings(holdings, "composite", 1).map((h) => h.label)).toEqual(["Beta Bank", "Alpha", "Gamma"]);
    wrap(<HoldingsView d={d} layout="table" onLayout={() => undefined} />);
    expect(names()).toEqual(["Beta Bank", "Alpha", "Gamma"]);
    expect(within(screen.getByRole("table")).getByText("Sell / Exit")).toBeInTheDocument(); // pill has text, not just colour
    expect(screen.getByText(/Promoter pledge 60%/)).toBeInTheDocument();
    expect(screen.getByText("max 12%")).toBeInTheDocument(); // overweight
  });

  it("re-sorts on header click and filters", () => {
    wrap(<HoldingsView d={d} layout="table" onLayout={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "P&L" }));
    expect(names()).toEqual(["Alpha", "Gamma", "Beta Bank"]);
    expect(screen.getByRole("columnheader", { name: /P&L/ })).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(within(screen.getByRole("group", { name: "Sector" })).getByRole("button", { name: /^IT/ }));
    expect(names()).toEqual(["Alpha", "Gamma"]);
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "gam" } });
    expect(names()).toEqual(["Gamma"]);
    expect(screen.getByText(/1 of 3/)).toBeInTheDocument();
  });

  it("opens the stock on row click", () => {
    wrap(<HoldingsView d={d} layout="table" onLayout={() => undefined} />);
    fireEvent.click(screen.getAllByText("₹110.00", { selector: "td" })[0]!);
    expect(screen.getByText("detail page")).toBeInTheDocument();
  });
});

describe("Action list", () => {
  it("shows severity as text and links to the reasons", () => {
    wrap(
      <ActionListBody
        d={{
          style_label: "Long-term",
          risk_label: "Medium",
          disclaimer: "x",
          actions: [
            { severity: "high", kind: "stock", subject: "Beta Bank", title: "Sell", detail: "Severe red flag", link: "/analysis/B.NS" },
            { severity: "low", kind: "fund", subject: "Axis ELSS", title: "Review", detail: "Lags Nifty 500", link: "/mutual-funds/1" },
          ],
        }}
      />,
    );
    expect(screen.getByText("1 high, 0 medium, 1 low.")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Beta Bank" })).toHaveAttribute("href", "/analysis/B.NS");
  });

  it("opens a quick look for a held stock, with a way to its full page", () => {
    const sig = SAMPLE_SIGNALS.holdings.find((h) => h.ticker === "RELIANCE.NS")!;
    const shape = SAMPLE_HOLDINGS.holdings.find((h) => h.ticker === "RELIANCE.NS");
    wrap(
      <>
        <button type="button">before</button>
        <ActionListBody
          d={{
            style_label: "Long-term",
            risk_label: "Medium",
            disclaimer: "x",
            actions: [
              { severity: "high", kind: "stock", subject: sig.label, title: "Sell", detail: sig.rule, link: "/analysis/RELIANCE.NS" },
              { severity: "low", kind: "fund", subject: "Axis ELSS", title: "Review", detail: "Lags", link: "/mutual-funds/1" },
            ],
          }}
          lookup={(t) => (t === "RELIANCE.NS" ? { signal: sig, shape } : {})}
        />
      </>,
    );
    expect(screen.getByRole("link", { name: "Axis ELSS" })).toHaveAttribute("href", "/mutual-funds/1"); // funds still link
    const opener = screen.getByRole("button", { name: sig.label });
    opener.focus();
    fireEvent.click(opener);
    const panel = screen.getByRole("dialog", { name: /RELIANCE\.NS/ });
    expect(within(panel).getByRole("button", { name: "Close" })).toHaveFocus();
    expect(within(panel).getByText("Why")).toBeInTheDocument();
    expect(within(panel).getAllByText(sig.rule).length).toBeGreaterThan(0);
    expect(within(panel).getByRole("link", { name: /Open the full story/ })).toHaveAttribute("href", "/analysis/RELIANCE.NS");
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus(); // back where it was
  });

  it("says when nothing needs attention", () => {
    wrap(<ActionListBody d={{ style_label: "Swing", risk_label: "Low", disclaimer: "x", actions: [] }} />);
    expect(screen.getByText(/Nothing needs attention/)).toBeInTheDocument();
  });
});

const thresholds: Thresholds = {
  override_file: "/x/var/profiles.local.yaml",
  edited: 1,
  note: "Other settings live in profiles.yaml.",
  items: [
    { path: "risk_levels.medium.max_weight_per_stock", group: "Risk: medium", label: "Max weight per stock", unit: "fraction", nullable: false, value: 0.12, default: 0.1, edited: true },
    { path: "risk_levels.medium.max_beta", group: "Risk: medium", label: "Max beta (blank = no limit)", unit: "ratio", nullable: true, value: 1.3, default: 1.3, edited: false },
  ],
};

describe("Thresholds", () => {
  it("converts fractions to percent and back", () => {
    const f = { unit: "fraction" as const, nullable: false };
    expect(toDisplay(f, 0.12)).toBe("12");
    expect(fromDisplay(f, "12.5")).toBe(0.125);
    expect(fromDisplay(f, "")).toBe("invalid");
    expect(fromDisplay({ unit: "ratio", nullable: true }, "")).toBeNull();
    expect(fromDisplay({ unit: "ratio", nullable: true }, "abc")).toBe("invalid");
  });

  it("saves only changed values, in config units", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => new Response(init?.body ? JSON.stringify(thresholds) : "{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<ThresholdsForm d={thresholds} />);
    expect(screen.getByText(/edited; default 10/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Risk: medium: Max weight per stock"), { target: { value: "15" } });
    fireEvent.change(screen.getByLabelText("Risk: medium: Max beta (blank = no limit)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save 2 changes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/settings/thresholds");
    expect(JSON.parse(String(init?.body))).toEqual({
      values: { "risk_levels.medium.max_weight_per_stock": 0.15, "risk_levels.medium.max_beta": null },
    });
  });

  it("blocks saving a non-number", () => {
    wrap(<ThresholdsForm d={thresholds} />);
    fireEvent.change(screen.getByLabelText("Risk: medium: Max weight per stock"), { target: { value: "lots" } });
    expect(screen.getByText(/Not a number: Max weight per stock/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save/ })).toBeDisabled();
  });
});

const config: AppConfig = {
  version: 1,
  disclaimer: "x",
  styles: {
    intraday: { label: "Intraday", horizon: "same day", timeframes: ["15m"], technical_weight: 1, fundamental_weight: 0, note: "Delayed data" },
    swing: { label: "Swing", horizon: "days to weeks", timeframes: ["1d"], technical_weight: 0.8, fundamental_weight: 0.2, note: null },
    positional: { label: "Positional", horizon: "weeks to months", timeframes: ["1d", "1wk"], technical_weight: 0.6, fundamental_weight: 0.4, note: null },
    long_term: { label: "Long-term", horizon: "years", timeframes: ["1wk", "1mo"], technical_weight: 0.3, fundamental_weight: 0.7, note: null },
    custom: { label: "Custom", horizon: "your choice", timeframes: ["1d"], technical_weight: 0.5, fundamental_weight: 0.5, note: null },
  },
  risk_levels: {
    low: { label: "Low", max_weight_per_stock: 0.08, max_weight_per_sector: 0.2, stop_loss_atr_multiple: 1.5, min_market_cap_cr: 20000, max_debt_to_equity: 0.5, max_beta: 1, buy_threshold: 75 },
    medium: { label: "Medium", max_weight_per_stock: 0.12, max_weight_per_sector: 0.3, stop_loss_atr_multiple: 2, min_market_cap_cr: 5000, max_debt_to_equity: 1, max_beta: 1.3, buy_threshold: 70 },
    high: { label: "High", max_weight_per_stock: 0.2, max_weight_per_sector: 0.4, stop_loss_atr_multiple: 3, min_market_cap_cr: 500, max_debt_to_equity: null, max_beta: null, buy_threshold: 65 },
  },
};

const fresh: Profile = { style: null, risk: "medium", custom_technical_weight: 0.5, gsheet_url: null, onboarded: false, updated_at: "" };

describe("Onboarding", () => {
  it("walks three steps with progress, needs a style, defaults risk to Medium and checks the sheet link", () => {
    wrap(<ProfileForm config={config} profile={fresh} firstRun />);
    const progress = screen.getByRole("list", { name: "Setup progress" });
    expect(within(progress).getAllByRole("listitem")[0]).toHaveAttribute("aria-current", "step");
    const next = screen.getByRole("button", { name: "Next" });
    expect(next).toBeDisabled(); // no style yet
    fireEvent.click(screen.getByRole("radio", { name: /Custom/ }));
    expect(screen.getByText(/Technical weight: 50%/)).toBeInTheDocument();
    fireEvent.click(next);
    expect(screen.getByRole("heading", { name: "Your risk level" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Medium/ })).toBeChecked();
    expect(within(progress).getByText(/Your investing style \(done\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByPlaceholderText(/docs.google.com/), { target: { value: "http://evil.example" } });
    expect(screen.getByText(/doesn't look like a Google Sheets link/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save and continue" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Your risk level" })).toBeInTheDocument();
  });

  it("saves and sends a new user to Import", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const body = url.endsWith("/settings/profile")
        ? { ...fresh, ...JSON.parse(String(init?.body)), onboarded: true }
        : { stocks: [], mf: [], snapshots: [] };
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    wrap(<ProfileForm config={config} profile={fresh} firstRun />);
    fireEvent.click(screen.getByRole("radio", { name: /Long-term/ }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByText("import page")).toBeInTheDocument();
    const sent = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body));
    expect(sent).toMatchObject({ style: "long_term", risk: "medium", gsheet_url: null });
  });
});

describe("Risk impact", () => {
  it("lists what each risk level sets and what switching would change", async () => {
    const { RiskImpact } = await import("./RiskImpact");
    render(<RiskImpact config={config} selected="high" saved="medium" />);
    expect(screen.getByText(/Switching from Medium to High changes \d+ settings?/)).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Debt/equity limit" })).toBeInTheDocument();
    expect(screen.getByText(/Check: Debt within your risk limit/)).toBeInTheDocument();
    expect(screen.getAllByText("changes").length).toBeGreaterThan(0);
  });
});
