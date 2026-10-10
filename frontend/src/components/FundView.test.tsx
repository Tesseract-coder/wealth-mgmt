import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { FundReport, MFHoldingsAnalysis, PortfolioSummary } from "../api/client";
import { FundHoldingsBody, FundReportBody, FundSignalPill } from "./FundView";
import { PortfolioSummaryBody } from "./PortfolioSummary";

const fund: FundReport = {
  code: "107578",
  name: "Mirae Asset Large Cap Fund - Regular Plan - Growth",
  amc: "Mirae Asset Mutual Fund",
  category: "Equity Schemes - Large Cap Fund",
  asset_class: "equity",
  plan: "regular",
  option: "growth",
  nav: 104.2,
  nav_date: "2026-10-09",
  previous_nav: 103.9,
  nav_freshness: { status: "fresh", reason: "ok" },
  history_start: "2013-01-01",
  holding: { units: 402.117, invested: 40000, value: 41908, pnl: 1908, folios: ["7890123"], first_purchase: null, xirr: null, xirr_basis: "Not available: needs a detailed CAS", xirr_approximate: false },
  returns: [
    { years: 1, fund: -7.39, benchmark: -10.58 },
    { years: 3, fund: 6.62, benchmark: 4.89 },
    { years: 5, fund: 5.39, benchmark: 4.65 },
  ],
  benchmark: { ticker: "^NSEI", label: "Nifty 50" },
  risk: { start: "2023-10-09", end: "2026-10-09", years: 3, cagr: 6.6, volatility: 13.19, sharpe: 0.01, sortino: 0.01, max_drawdown: -16.2, drawdown_peak: "2024-09-27", drawdown_trough: "2025-03-03" },
  benchmark_risk: null,
  rolling: [{ years: 3, windows: 105, fund_avg: 11.63, bench_avg: 11.11, avg_excess: 0.52, beat_share: 0.695, worst_excess: -1.2, best_excess: 2.4, first_start: "2020-10-09", last_start: "2023-10-01" }],
  direct_twin: { code: "118825", name: "Mirae Asset Large Cap Fund - Direct Plan - Growth" },
  direct_gap_pp: 1.04,
  direct_gap_basis: "Direct minus Regular CAGR over 3 years",
  expense_ratio_pct: null,
  overlaps: [],
  segment_peers: [],
  signal: "switch",
  signal_label: "Switch",
  rule: "Regular plan: the Direct plan (118825) has the same portfolio at a lower cost",
  reasons: [{ direction: "bearish", text: "Regular plan: the Direct plan (118825) has the same portfolio at a lower cost" }],
  notes: ["Benchmark: Nifty 50 price index"],
  unavailable: ["Expense ratio (no free API publishes it)"],
  fetch_errors: [],
  disclaimer: "x",
};

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Fund views", () => {
  it("pill shows text", () => {
    render(<FundSignalPill signal="review" label="Review" />);
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("fund detail shows the signal, returns vs benchmark, risk, the Direct plan gap and TER input", () => {
    wrap(<FundReportBody f={fund} />);
    expect(screen.getByText("Switch")).toBeInTheDocument();
    expect(screen.getAllByText(/Direct plan \(118825\)/).length).toBeGreaterThan(0);
    expect(screen.getByText("Returns vs Nifty 50")).toBeInTheDocument();
    expect(screen.getByText("+6.6%")).toBeInTheDocument();
    expect(screen.getByText("1.7 pp")).toBeInTheDocument(); // 6.62 − 4.89
    expect(screen.getByText("70%")).toBeInTheDocument(); // rolling beat share
    expect(screen.getByText("-16.2%")).toBeInTheDocument();
    expect(screen.getByText(/\+1\.04 pp a year more/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 0.65")).toBeInTheDocument();
    expect(screen.getByText(/Expense ratio \(no free API publishes it\)/)).toBeInTheDocument();
  });

  it("holdings list sorts Switch first and shows the overlap matrix", () => {
    const d: MFHoldingsAnalysis = {
      funds: [
        { ...fund, code: "1", name: "Good Fund", signal: "continue", signal_label: "Continue", rule: "No rule fired" },
        { ...fund, code: "2", name: "Bad Fund" },
      ],
      overlap: { codes: ["1", "2"], names: ["Good Fund", "Bad Fund"], pct: [[100, 62], [62, 100]], approximate: false },
      warnings: ["Bad Fund is a Regular plan: a Direct plan costs less."],
      disclaimer: "x",
    };
    wrap(<FundHoldingsBody d={d} />);
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links.slice(0, 2)).toEqual(["Bad Fund", "Good Fund"]);
    expect(screen.getAllByText("62%")).toHaveLength(2);
    expect(screen.getByText(/costs less/)).toBeInTheDocument();
  });
});

describe("Portfolio summary", () => {
  const s: PortfolioSummary = {
    as_of: "2026-10-09",
    total_value: 611682,
    stock_value: 387629,
    fund_value: 224053,
    invested: 613549,
    invested_note: null,
    pnl: -1867,
    pnl_pct: -0.3,
    day_change: 7835,
    day_change_pct: 1.3,
    day_change_note: null,
    xirr: null,
    xirr_coverage: 0,
    xirr_basis: "Not available: needs purchase dates",
    by_holding: [{ key: "SBIN.NS", label: "State Bank of India", value: 57000, weight: 0.094 }],
    by_sector: [{ key: "Financial Services", label: "Financial Services", value: 133000, weight: 0.218 }],
    by_mcap: [{ key: "Large cap", label: "Large cap", value: 479000, weight: 0.78 }],
    by_asset_class: [{ key: "Stocks & ETFs", label: "Stocks & ETFs", value: 387629, weight: 0.634 }],
    warnings: ["Financial Services is 34.4% of your portfolio, above your 30% sector limit"],
    beta: 0.92,
    beta_coverage: 1,
    beta_basis: "Value-weighted",
    correlation_labels: ["A", "B"],
    correlation: [[1, 0.5], [0.5, 1]],
    correlation_basis: "Daily returns",
    performance_dates: ["2025-10-10", "2026-10-09"],
    performance_portfolio: [100, 89.26],
    performance_nifty: [100, 89.07],
    performance_basis: "Your current holdings, held unchanged",
    snapshots: [],
    notes: [],
    disclaimer: "x",
  };

  it("shows KPIs, warnings, allocation, beta and performance vs Nifty", () => {
    wrap(<PortfolioSummaryBody s={s} />);
    expect(screen.getByText("₹6,11,682")).toBeInTheDocument();
    expect(screen.getByText("+1.30%")).toBeInTheDocument();
    expect(screen.getByText(/needs purchase dates/)).toBeInTheDocument();
    expect(screen.getByText(/above your 30% sector limit/)).toBeInTheDocument();
    expect(screen.getByText("State Bank of India")).toBeInTheDocument();
    expect(screen.getByText(/Portfolio beta 0.92/)).toBeInTheDocument();
    expect(screen.getByText(/portfolio -10.7%, Nifty 50 -10.9%/)).toBeInTheDocument();
    expect(screen.getAllByText("0.50")).toHaveLength(2);
  });

  it("prompts an import when empty", () => {
    wrap(<PortfolioSummaryBody s={{ ...s, total_value: 0 }} />);
    expect(screen.getByText(/Import your Groww files/)).toBeInTheDocument();
  });
});
