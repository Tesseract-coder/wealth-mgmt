import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { FundamentalReport } from "../api/client";
import { FundamentalBody, formatMetric } from "./FundamentalView";

const report: FundamentalReport = {
  ticker: "RELIANCE.NS",
  label: "Reliance Industries Limited",
  sector: "Oil Gas & Consumable Fuels",
  is_financial: false,
  source: "yahoo",
  latest_year: "2026-03-31",
  freshness: { status: "fresh", reason: "ok" },
  metrics: [
    { key: "pe", label: "P/E", value: 19.61, unit: "x", basis: "Market cap ÷ net profit (FY2026)", sector_median: 14.2, peers: 9 },
    { key: "market_cap", label: "Market cap", value: 1583705.34, unit: "₹ Cr", basis: "close", sector_median: null, peers: 0 },
    { key: "op_margin_change", label: "Operating margin change over 3y", value: -0.14, unit: "pp", basis: "FY2023→FY2026", sector_median: null, peers: 0 },
    { key: "roe", label: "ROE", value: 9.25, unit: "%", basis: "Net profit ÷ average equity (FY2026)", sector_median: null, peers: 0 },
  ],
  fscore: {
    score: 6,
    computable: 9,
    tests: [
      { name: "Profitable (ROA > 0)", passed: true, detail: "ROA 4.1%" },
      { name: "Current ratio improving", passed: false, detail: "1.10 → 1.10" },
    ],
  },
  observations: [
    { key: "peg_rich", category: "valuation", direction: "bearish", text: "PEG 2.98: price runs ahead of its growth", value: 2.98, minor: false },
    { key: "fcf_consistent", category: "health", direction: "bullish", text: "Free cash flow positive in each of the last 3 years", value: 1, minor: false },
  ],
  unavailable: ["Revenue CAGR 5y (needs 6 years of results, have 4)"],
  notes: ["Data check: our P/B 1.34 differs from Yahoo's own figure 1.80."],
  fetch_errors: [],
  disclaimer: "x",
};

describe("FundamentalBody", () => {
  it("shows metrics with units, sector medians, basis, F-score tests and gaps", () => {
    render(
      <MemoryRouter>
        <FundamentalBody r={report} />
      </MemoryRouter>,
    );
    expect(screen.getByText("19.61×")).toBeInTheDocument();
    expect(screen.getByText("sector 14.20×")).toBeInTheDocument();
    expect(screen.getByText("₹15,83,705 Cr")).toBeInTheDocument();
    expect(screen.getByText("−0.1 pp")).toBeInTheDocument();
    expect(screen.getByText("Net profit ÷ average equity (FY2026)")).toBeInTheDocument();
    expect(screen.getByText("Piotroski F-score: 6/9")).toBeInTheDocument();
    expect(screen.getByText("✗ fail")).toBeInTheDocument();
    expect(screen.getByText(/▼ Negative \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Revenue CAGR 5y \(needs 6 years/)).toBeInTheDocument();
    expect(screen.getByText(/Data check/)).toBeInTheDocument();
  });

  it("formats each unit", () => {
    expect(formatMetric({ value: null, unit: "%" })).toBe("—");
    expect(formatMetric({ value: 12.345, unit: "%" })).toBe("12.3%");
    expect(formatMetric({ value: 2.5, unit: "pp" })).toBe("+2.5 pp");
    expect(formatMetric({ value: 3, unit: "" })).toBe("3");
  });
});
