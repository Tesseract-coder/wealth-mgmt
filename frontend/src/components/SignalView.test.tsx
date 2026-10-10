import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HoldingSignals, SideScore, StockSignal } from "../api/client";
import { HoldingSignalsTable, SignalPill, StockSignalBody } from "./SignalView";

const side = (score: number | null): SideScore => ({
  score,
  coverage: 0.9,
  applicable: true,
  subscores: [{ category: "trend", score, weight: 0.3, bullish: 2, bearish: 1, neutral: 0 }],
  timeframes: [],
  notes: [],
});

const signal: StockSignal = {
  ticker: "ITC.NS",
  label: "ITC Ltd",
  style: "swing",
  style_label: "Swing",
  risk: "medium",
  risk_label: "Medium",
  signal: "reduce",
  signal_label: "Reduce / Trim",
  rule: "Position is 14.8% of your portfolio, above your 12% limit per stock (Medium risk)",
  scores: {
    composite: 52.2,
    technical: side(47.3),
    fundamental: side(63.1),
    technical_weight: 0.7,
    fundamental_weight: 0.3,
    coverage: 0.97,
    confidence: "high",
    confidence_reason: "97% of the score's inputs had data",
  },
  bullish: [
    { source: "technical", key: "breakout", category: "structure", direction: "bullish", text: "Broke out above resistance ₹256.60", minor: false, weight: 1.5, points: 3.94, timeframes: [] },
  ],
  bearish: [
    { source: "fundamental", key: "debt_above_limit", category: "health", direction: "bearish", text: "Debt/equity 2.40, above your limit of 1", minor: false, weight: 2, points: -2.4, timeframes: [] },
  ],
  readings: [],
  flags: [{ key: "sector_concentration", severe: false, text: "Banks is 34.4% of your portfolio, above your 30% sector limit" }],
  levels: {
    interval: "1d",
    close: 266,
    as_of: "2026-10-09",
    atr: 6.48,
    multiple: 2,
    trailing_stop: 258.1,
    entry_stop: 253.05,
    stop_breached: false,
    risk_per_share: 12.95,
    targets: [
      { label: "Nearest resistance", price: 273.76, pct: 2.9 },
      { label: "2R", price: 291.9, pct: 9.7 },
    ],
    basis: "Trailing stop = highest high of the last 22 days − 2 × ATR(14).",
  },
  beta: 0.73,
  beta_basis: "daily returns vs Nifty 50 over 252 sessions",
  position: { quantity: 120, avg_price: 412.1, invested: 49452, price: 266, price_source: "close on 09 Oct 2026", value: 31920, pnl: -17532, pnl_pct: -35.45, lots: [] },
  weight: 0.148,
  max_weight: 0.12,
  sector: "Fast Moving Consumer Goods",
  sector_weight: 0.08,
  max_sector_weight: 0.3,
  rebalance: { action: "trim", quantity: 26, value: 6916, target_weight: 0.12, text: "Trim 26 share(s) (≈ ₹6,916) to bring the weight from 14.8% to your 12.0% limit." },
  tax: { holding_days: null, term: "unknown", long_term_from: null, text: ["Purchase date unknown: your import has no buy date"], verify_note: "Verify current rates." },
  price_freshness: { status: "fresh", reason: "Up to date" },
  fundamental_freshness: { status: "stale", reason: "9 days old" },
  notes: [],
  disclaimer: "x",
};

function wrap(node: ReactNode) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("SignalPill", () => {
  it("always shows text, not colour alone", () => {
    render(<SignalPill signal="sell" label="Sell / Exit" />);
    expect(screen.getByText("Sell / Exit")).toBeInTheDocument();
  });
});

describe("StockSignalBody", () => {
  it("shows the signal, why, reasons with points, levels, sizing and tax", () => {
    wrap(<StockSignalBody s={signal} />);
    expect(screen.getByText("Reduce / Trim")).toBeInTheDocument();
    expect(screen.getByText(/above your 12% limit per stock/)).toBeInTheDocument();
    expect(screen.getByText("High confidence")).toBeInTheDocument();
    expect(screen.getByText("Broke out above resistance ₹256.60")).toBeInTheDocument();
    expect(screen.getByText("+3.9")).toBeInTheDocument();
    expect(screen.getByText("−2.4")).toBeInTheDocument();
    expect(screen.getByText(/Red flag: Banks is 34.4%/)).toBeInTheDocument();
    expect(screen.getByText("₹258.10")).toBeInTheDocument(); // trailing stop
    expect(screen.getByText("Target: 2R")).toBeInTheDocument();
    expect(screen.getByText(/Trim 26 share/)).toBeInTheDocument();
    expect(screen.getByText(/never places orders/)).toBeInTheDocument();
    expect(screen.getByText(/Purchase date unknown/)).toBeInTheDocument();
    expect(screen.getByText("Verify current rates.")).toBeInTheDocument();
    expect(screen.getByText("14.8% of 12% max")).toBeInTheDocument();
  });

  it("says so when there is no stop or position", () => {
    wrap(<StockSignalBody s={{ ...signal, levels: null, position: null, weight: null, tax: null }} />);
    expect(screen.getByText(/Not enough price history/)).toBeInTheDocument();
    expect(screen.getByText(/You don't hold this stock/)).toBeInTheDocument();
  });
});

describe("HoldingSignalsTable", () => {
  const d: HoldingSignals = {
    style: "swing",
    style_label: "Swing",
    risk: "medium",
    risk_label: "Medium",
    technical_weight: 0.7,
    weight_base: "portfolio",
    total_value: 400000,
    stock_value: 300000,
    fund_value: 100000,
    sectors: [{ sector: "Financial Services", weight: 0.34, limit: 0.3, over: true }],
    notes: [],
    disclaimer: "x",
    holdings: [
      {
        ticker: "TCS.NS", label: "TCS", signal: "hold", signal_label: "Hold", rule: "Composite 52 is between 45 and 70",
        composite: 52, technical: 40, fundamental: 80, confidence: "medium", weight: 0.05, max_weight: 0.12, quantity: 5, avg_price: 3980, price: 4000, invested: 19900, value: 20000, pnl_pct: 0.5,
        pnl: 100, sector: "IT", flags: [], top_bullish: ["ROE 48%"], top_bearish: [], stop: 2100, stop_breached: false,
        rebalance: { action: "none", quantity: 0, value: null, target_weight: null, text: "No change suggested." },
        price_freshness: { status: "fresh", reason: "ok" },
      },
      {
        ticker: "SBIN.NS", label: "SBI", signal: "sell", signal_label: "Sell / Exit", rule: "Severe red flag: closed below stop",
        composite: 40, technical: 16, fundamental: 94, confidence: "high", weight: 0.148, max_weight: 0.12, quantity: 60, avg_price: 750, price: 950, invested: 45000, value: 57000, pnl_pct: 26.7,
        pnl: 12000, sector: "Financial Services", flags: [{ key: "stop_breached", severe: true, text: "Closed below the stop" }],
        top_bullish: [], top_bearish: ["ADX 30: sellers in control"], stop: 977, stop_breached: true,
        rebalance: { action: "exit", quantity: 60, value: 57000, target_weight: 0, text: "Sell all 60 shares to exit." },
        price_freshness: { status: "fresh", reason: "ok" },
      },
    ],
  };

  it("lists the most urgent first with pills, flags and suggestions", () => {
    wrap(<HoldingSignalsTable d={d} />);
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links).toEqual(["SBI", "TCS"]);
    expect(screen.getByText("Sell / Exit")).toBeInTheDocument();
    expect(screen.getByText(/⛔ Closed below the stop/)).toBeInTheDocument();
    expect(screen.getByText("Sell all 60 shares to exit.")).toBeInTheDocument();
    expect(screen.getByText(/above your 30% limit/)).toBeInTheDocument();
    expect(screen.getByText(/funds ₹1,00,000/)).toBeInTheDocument();
  });

  it("prompts an import when empty", () => {
    wrap(<HoldingSignalsTable d={{ ...d, holdings: [] }} />);
    expect(screen.getByText(/Import your Groww file/)).toBeInTheDocument();
  });
});
