import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PatternHolding, PatternReport } from "../../api/client";
import { HoldingsPatterns, PatternGuide, PatternShape, patternSummary, PatternsSection } from ".";
import { SAMPLE_PATTERN_LIBRARY, SAMPLE_PATTERNS } from "./samples";

const KEYS = [
  "head_and_shoulders",
  "inverse_head_and_shoulders",
  "double_top",
  "double_bottom",
  "rounding_bottom",
  "cup_and_handle",
  "rising_wedge",
  "falling_wedge",
  "bull_flag",
  "bear_flag",
  "bull_pennant",
  "bear_pennant",
  "ascending_triangle",
  "descending_triangle",
  "symmetrical_triangle",
];

const EMPTY: PatternReport = { ...SAMPLE_PATTERNS, patterns: [] };

function mockFetch(routes: Record<string, unknown>) {
  const fn = vi.fn(async (url: string) => {
    const hit = Object.entries(routes).find(([k]) => url.includes(k));
    return new Response(JSON.stringify(hit ? hit[1] : {}), { status: hit ? 200 : 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("patternSummary", () => {
  it("counts by direction and says whether to wait", () => {
    expect(patternSummary(SAMPLE_PATTERNS)).toBe("2 patterns on the daily chart: 2 bearish. All are confirmed.");
    const forming = { ...SAMPLE_PATTERNS, patterns: [{ ...SAMPLE_PATTERNS.patterns[0]!, status: "forming" as const, direction: "bullish" as const }] };
    expect(patternSummary(forming)).toBe("1 pattern on the daily chart: 1 bullish. None is confirmed yet: wait for the break.");
    expect(patternSummary({ ...EMPTY, interval: "1wk" })).toBe("No classic pattern on the weekly chart right now.");
  });
});

describe("PatternShape", () => {
  it("draws every pattern the scanner reports", () => {
    const { container } = render(
      <div>
        {KEYS.map((k) => (
          <PatternShape key={k} patternKey={k} direction="bullish" />
        ))}
      </div>,
    );
    expect(container.querySelectorAll("svg")).toHaveLength(KEYS.length);
  });
});

describe("PatternGuide", () => {
  it("filters by signal and by trading style, and marks what's on the chart", async () => {
    mockFetch({ "/analysis/patterns/library": SAMPLE_PATTERN_LIBRARY });
    wrap(<PatternGuide found={new Set(["double_top"])} />);
    expect(await screen.findByRole("heading", { name: "Double top" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(4);
    const top = screen.getByRole("heading", { name: "Double top" }).closest("li")!;
    expect(within(top).getByText("On this chart")).toBeInTheDocument();
    expect(within(top).getByText("Good for selling")).toBeInTheDocument();
    expect(within(top).getByRole("list", { name: "Suits these trading styles" })).toHaveTextContent("Intraday: WorksSwing: Good fitPositional: Good fit");

    fireEvent.click(screen.getByRole("button", { name: /^Bearish/ }));
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Double top"]);

    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    fireEvent.click(screen.getByRole("button", { name: "Intraday" }));
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Bull flag", "Symmetrical triangle"]);
  });
});

describe("PatternsSection", () => {
  it("shows an empty state that offers the weekly chart", async () => {
    const fetch = mockFetch({ "interval=1wk": SAMPLE_PATTERNS, "interval=1d": EMPTY, "/analysis/patterns/library": SAMPLE_PATTERN_LIBRARY });
    wrap(<PatternsSection ticker="RELIANCE.NS" style="swing" />);
    expect(await screen.findByText("No clear pattern on the daily chart")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check the weekly chart" }));
    expect(await screen.findByRole("article", { name: "Double top" })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([u]) => String(u).includes("/RELIANCE.NS/patterns?interval=1wk"))).toBe(true);
  });

  it("opens long-term investors on the weekly chart and hands a pattern to the price chart", async () => {
    mockFetch({ "/patterns?interval=1wk": SAMPLE_PATTERNS, "/analysis/patterns/library": SAMPLE_PATTERN_LIBRARY });
    const onShow = vi.fn();
    wrap(<PatternsSection ticker="RELIANCE.NS" style="long_term" onShow={onShow} />);
    const card = await screen.findByRole("article", { name: "Symmetrical triangle" });
    fireEvent.click(within(card).getByRole("button", { name: "Show on the price chart" }));
    expect(onShow).toHaveBeenCalledWith(expect.objectContaining({ key: "symmetrical_triangle" }), "1d");
  });
});

describe("HoldingsPatterns", () => {
  const holdings: PatternHolding[] = [
    { ticker: "ALKEM.NS", label: "Alkem Laboratories", interval: "1d", as_of: "2026-10-19", bars: 1235, patterns: SAMPLE_PATTERNS.patterns },
    { ticker: "TCS.NS", label: "TCS", interval: "1d", as_of: "2026-10-19", bars: 1235, patterns: [] },
  ];

  it("lists holdings with their patterns, linking to each stock's patterns section", async () => {
    mockFetch({ "/analysis/patterns/holdings": holdings, "/analysis/patterns/library": SAMPLE_PATTERN_LIBRARY });
    wrap(<HoldingsPatterns style="swing" linkQuery={(t) => `/analysis/${t}?view=patterns`} />);
    expect(await screen.findByRole("link", { name: "Alkem Laboratories" })).toHaveAttribute("href", "/analysis/ALKEM.NS?view=patterns");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Double top.*Bearish, confirmed/ })).toBeInTheDocument();
    expect(screen.getByText("1 holding with no clear pattern")).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("group", { name: "Show" })).getByRole("button", { name: /^Bullish/ }));
    expect(screen.getByText("No holding has a pattern matching these filters.")).toBeInTheDocument();
  });
});
