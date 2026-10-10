import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, OFFLINE_MESSAGE, type Backtest } from "../api/client";
import { NotFound } from "../pages/NotFound";
import { BackendStatus } from "./BackendStatus";
import { BacktestResult, BacktestView } from "./Backtest";
import { ErrorBoundary } from "./ErrorBoundary";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("error states", () => {
  it("turns a network failure into a plain message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.health()).rejects.toEqual(new ApiError(0, OFFLINE_MESSAGE));
  });

  it("explains a dead dev proxy (500 with no body)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    await expect(api.health()).rejects.toThrow(/Can't reach the backend/);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })));
    await expect(api.health()).rejects.toThrow(/HTTP 502.*make dev/);
  });

  it("keeps the backend's own error text", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "No such job" }), { status: 404 })));
    await expect(api.health()).rejects.toThrow("No such job");
  });

  it("shows a banner while the backend is offline", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    wrap(<BackendStatus />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Backend offline.*make dev/);
    expect(screen.getByRole("button", { name: "Retry now" })).toBeInTheDocument();
  });

  it("shows nothing when the backend is fine", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: "ok", database: "ok", config_version: 1, server_time_ist: "" })));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = wrap(<BackendStatus />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("catches a page crash and recovers", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let crash = true;
    function Page() {
      if (crash) throw new Error("Cannot read properties of undefined");
      return <p>Page back</p>;
    }
    render(
      <ErrorBoundary>
        <Page />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't be shown.*Cannot read properties.*nothing was changed/);
    crash = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText("Page back")).toBeInTheDocument();
  });

  it("has a real not-found page", () => {
    wrap(<NotFound />);
    expect(screen.getByRole("link", { name: "Go to the Overview" })).toHaveAttribute("href", "/");
  });
});

const backtest: Backtest = {
  ticker: "RELIANCE.NS",
  label: "Reliance Industries",
  style: "swing",
  style_label: "Swing",
  risk: "medium",
  risk_label: "Medium",
  status: "ok",
  message: "152 evaluations over 755 sessions; 39 Buy signals, 54% higher after 20 sessions.",
  start: "2023-10-06",
  end: "2026-10-09",
  sessions: 755,
  evaluations: 152,
  step_sessions: 5,
  horizon_sessions: 20,
  timeframes: ["1d"],
  stats: [
    { group: "buy", label: "Buy / Strong Buy", count: 39, measured: 39, hit_rate: 0.54, rise_rate: 0.54, avg_forward_return: -0.002 },
    { group: "exit", label: "Reduce / Sell", count: 89, measured: 85, hit_rate: 0.53, rise_rate: 0.46, avg_forward_return: -0.0017 },
    { group: "all", label: "Every evaluation (base rate)", count: 152, measured: 148, hit_rate: null, rise_rate: 0.49, avg_forward_return: 0.002 },
  ],
  strategy: { total_return: -0.056, max_drawdown: -0.16, exposure: 0.265 },
  buy_hold: { total_return: 0.12, max_drawdown: -0.27, exposure: 1 },
  trades: 10,
  points: [
    { date: "2023-10-06", close: 1100, score: 50, signal: "hold", in_market: false, strategy: 1, buy_hold: 1 },
    { date: "2026-10-09", close: 1170.3, score: 31.2, signal: "sell", in_market: false, strategy: 0.944, buy_hold: 1.12 },
  ],
  notes: [],
  caveat: "Historical test of the technical rules only. Past results do not predict future returns.",
};

describe("backtest", () => {
  it("runs only when asked, and labels itself a historical test", async () => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify(backtest)));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<BacktestView ticker="RELIANCE.NS" style="swing" />);
    expect(screen.getByText(/Historical test only/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Run backtest for RELIANCE.NS" }));
    expect(await screen.findByText("Following the rules")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/analysis/backtest/RELIANCE.NS?style=swing");
  });

  it("shows returns, drawdowns, hit rates and the base rate", () => {
    wrap(<BacktestResult b={backtest} />);
    expect(screen.getByText("−5.6%")).toBeInTheDocument();
    expect(screen.getByText("+12.0%")).toBeInTheDocument();
    expect(screen.getByText(/Max drawdown −16.0% · in the market 27% · 10 entries/)).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Buy \/ Strong Buy 39 54% 54%/ })).toBeInTheDocument();
    expect(screen.getByText(/49% of all weeks were followed by a rise/)).toBeInTheDocument();
    expect(screen.getByText("Sell / Exit")).toBeInTheDocument(); // the pill has words, not just colour
    expect(screen.getByText(/do not predict future returns/)).toBeInTheDocument();
  });

  it("says when there isn't enough history", () => {
    wrap(<BacktestResult b={{ ...backtest, status: "insufficient_data", message: "Needs at least 300 sessions; 120 are cached." }} />);
    expect(screen.getByText(/Not enough price history.*120 are cached/)).toBeInTheDocument();
  });
});
