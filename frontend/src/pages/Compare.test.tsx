import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StockChecks } from "../api/client";
import { axesFromSections, ShapeOverlay } from "../components/analysis";
import { SAMPLE_STOCK } from "../components/analysis/samples";
import { Compare, parseTickers, unionChecks } from "./Compare";
import { WeekBadge, weekChangeText } from "./Watchlist";

const tcs: StockChecks = {
  ...SAMPLE_STOCK,
  ticker: "TCS.NS",
  label: "Tata Consultancy Services Ltd",
  total: 23,
  signal: "hold",
  signal_label: "Hold",
  sections: SAMPLE_STOCK.sections.map((s) => (s.key === "momentum" ? { ...s, score: 2, passed: 2, checks: s.checks.map((c, i) => (i < 2 ? { ...c, status: "pass" as const } : c)) } : s)),
};

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/settings/profile")
        ? { style: "positional", risk: "medium", custom_technical_weight: 0.5, gsheet_url: null, onboarded: true, updated_at: "" }
        : url.includes("/analysis/stock/TCS.NS/checks")
          ? tcs
          : url.includes("/analysis/stock/RELIANCE.NS/checks")
            ? SAMPLE_STOCK
            : url.includes("/portfolio/summary")
              ? { by_holding: [{ key: "ITC.NS", label: "ITC Ltd", value: 1, weight: 0.1 }] }
              : [];
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/compare" element={<Compare />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Compare", () => {
  it("reads up to four unique tickers from the URL", () => {
    expect(parseTickers("tcs.ns, RELIANCE.NS,TCS.NS,a,b,c")).toEqual(["TCS.NS", "RELIANCE.NS", "A", "B"]);
    expect(parseTickers(null)).toEqual([]);
  });

  it("asks for two stocks and offers your holdings", async () => {
    renderAt("/compare?t=RELIANCE.NS");
    expect(screen.getByText("Pick at least two stocks")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /ITC Ltd/ })).toBeInTheDocument();
  });

  it("overlays the shapes and lines up every check", async () => {
    renderAt("/compare?t=RELIANCE.NS,TCS.NS");
    const overlay = await screen.findByRole("img", { name: /^Score Shapes compared/ });
    expect(overlay.getAttribute("aria-label")).toContain("Reliance Industries Ltd 19 of 36");
    expect(overlay.getAttribute("aria-label")).toContain("Tata Consultancy Services Ltd 23 of 36");
    expect(screen.getByText(/Tata Consultancy Services Ltd has the biggest shape at 23\/36/)).toBeInTheDocument();

    const table = screen.getByRole("table");
    const momentum = within(table).getByRole("rowheader", { name: "Momentum" }).closest("tr")!;
    expect(within(momentum).getByText("0/6")).toBeInTheDocument();
    expect(within(momentum).getByText("2/6")).toBeInTheDocument();
    const row = within(table).getByRole("rowheader", { name: "Price above its 200-day average" }).closest("tr")!;
    expect(within(row).getByText("Fail")).toBeInTheDocument();
    expect(within(row).getByText("Pass")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove Tata Consultancy Services Ltd" }));
    expect(await screen.findByText("Pick at least two stocks")).toBeInTheDocument();
  });

  it("lists checks that only some stocks have", () => {
    const bank = { ...tcs, sections: tcs.sections.map((s) => (s.key === "health" ? { ...s, checks: [{ ...s.checks[0]!, check_id: "capital_cushion", label: "Capital cushion" }] } : s)) };
    expect(unionChecks([SAMPLE_STOCK, bank], "health").map((c) => c.check_id)).toContain("capital_cushion");
    expect(unionChecks([SAMPLE_STOCK, bank], "health")).toHaveLength(7);
  });

  it("tells overlaid shapes apart by line style and a legend, not colour alone", () => {
    const { container } = render(
      <ShapeOverlay
        series={[
          { name: "A", axes: axesFromSections(SAMPLE_STOCK.sections), total: 19, maxTotal: 36 },
          { name: "B", axes: axesFromSections(tcs.sections), total: 23, maxTotal: 36 },
        ]}
      />,
    );
    const polys = container.querySelectorAll("g.shape-in polygon");
    expect(polys[0]?.getAttribute("stroke-dasharray")).toBeNull();
    expect(polys[1]?.getAttribute("stroke-dasharray")).toBe("6 3");
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText("B")).toBeInTheDocument();
  });
});

describe("Watchlist week badge", () => {
  const wc = { since: "2026-10-04", axes: { valuation: -1, growth: 0, past: 0, health: 0, momentum: -2, dividends: null }, total: -3, previous_signal: "reduce" as const, previous_signal_label: "Reduce", signal_changed: true };
  it("names the axes that moved and the signal change", () => {
    expect(weekChangeText(wc)).toBe("Since 04 Oct 2026: total −3 · Valuation −1, Momentum −2 · was Reduce");
    render(<WeekBadge wc={wc} />);
    expect(screen.getByText(/total −3/)).toBeInTheDocument();
  });
  it("explains when there's no history yet", () => {
    render(<WeekBadge wc={null} />);
    expect(screen.getByText(/after a week of history/)).toBeInTheDocument();
  });
});
