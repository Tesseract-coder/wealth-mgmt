import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TechnicalReport, TechnicalSummary } from "../api/client";
import { Technical } from "./Technical";

const report: TechnicalReport = {
  ticker: "RELIANCE.NS",
  label: "RELIANCE.NS",
  style: "swing",
  timeframes: [
    {
      interval: "1d",
      bars: 1236,
      as_of: "2026-10-09",
      last_close: 1170.3,
      last_complete: true,
      freshness: { status: "fresh", reason: "Up to date" },
      analysis: {
        values: { sma50: 1271.79, sma200: 1355.26, rsi14: 35.4, adx: 39.9, atr14: 22.22, support: null, resistance: 1251.5 },
        observations: [
          { key: "price_vs_sma200", category: "trend", direction: "bearish", text: "Close ₹1,170.30 is 13.6% below its 200-day SMA (₹1,355.26)", value: -13.6, minor: false },
          { key: "stoch_oversold", category: "momentum", direction: "bullish", text: "Stochastic %K 15.0: oversold", value: 15, minor: false },
          { key: "candle_doji", category: "pattern", direction: "neutral", text: "Doji on the latest bar: indecision", value: null, minor: true },
        ],
        unavailable: ["Delivery % (no NSE bhavcopy data yet)"],
        levels: [],
      },
      notes: [],
    },
  ],
  context: { values: {}, observations: [], unavailable: ["52-week high/low (needs 252 sessions, have 100)"], levels: [] },
  fetch_errors: ["^NSEI: HTTP 503"],
  notes: [],
  disclaimer: "x",
};

const summary: TechnicalSummary[] = [
  { ticker: "TCS.NS", label: "Tata Consultancy", interval: "1d", as_of: null, freshness: { status: "unavailable", reason: "Not downloaded yet" }, bullish: 0, bearish: 0, neutral: 0, top_bullish: [], top_bearish: [] },
];

function mockFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/analysis/technical/holdings")
        ? summary
        : url.includes("/analysis/technical/")
          ? report
          : url.endsWith("/config")
            ? { version: 1, styles: {}, risk_levels: {}, disclaimer: "" }
            : { style: "swing", risk: "medium", custom_technical_weight: 0.5, gsheet_url: null, onboarded: true, updated_at: "" };
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/technical" element={<Technical />} />
          <Route path="/technical/:ticker" element={<Technical />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Technical page", () => {
  it("groups readings by direction with text labels, shows gaps and fetch errors", async () => {
    mockFetch();
    renderAt("/technical/RELIANCE.NS");
    expect(await screen.findByText(/13\.6% below its 200-day SMA/)).toBeInTheDocument();
    expect(screen.getAllByText(/▼ Bearish/).length).toBeGreaterThan(0); // never colour alone
    expect(screen.getByText("Stochastic %K 15.0: oversold")).toBeInTheDocument();
    expect(screen.getByText("(minor)")).toBeInTheDocument();
    expect(screen.getByText(/Delivery % \(no NSE bhavcopy data yet\)/)).toBeInTheDocument();
    expect(screen.getByText(/Could not refresh: \^NSEI: HTTP 503/)).toBeInTheDocument();
    expect(screen.getByText("₹1,251.50")).toBeInTheDocument(); // resistance
  });

  it("lists holdings with their data status", async () => {
    mockFetch();
    renderAt("/technical");

    expect(await screen.findByText("Tata Consultancy")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });
});
