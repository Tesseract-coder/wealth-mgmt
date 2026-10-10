import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job, MarketStatus } from "../api/client";
import { MarketData } from "./MarketData";

const status: MarketStatus = {
  generated_at: "2026-10-10T12:00:00+05:30",
  summary: { fresh: 2, stale: 1, unavailable: 1 },
  references: [
    {
      key: "nse_equity",
      label: "NSE equity list",
      source: "nse",
      origin: "bundled",
      as_of: "2026-10-09",
      rows: null,
      freshness: { status: "fresh", reason: "Bundled list from 09 Oct 2026, 12:00 AM IST." },
    },
  ],
  quotes: [
    { kind: "benchmark", code: "^NSEI", label: "Nifty 50", price: 22520.45, previous: 22230, change_pct: 1.3, as_of: "2026-10-09", source: "yahoo", freshness: { status: "fresh", reason: "Up to date" } },
    { kind: "stock", code: "RELIANCE.NS", label: "Reliance Industries", price: 1170.3, previous: 1178, change_pct: -0.65, as_of: "2026-10-09", source: "yahoo", freshness: { status: "fresh", reason: "Up to date" } },
    { kind: "stock", code: "ITC.NS", label: "ITC", price: null, previous: null, change_pct: null, as_of: null, source: null, freshness: { status: "unavailable", reason: "No data. Last attempt failed: HTTP 503" } },
    { kind: "mf", code: "118989", label: "HDFC Mid Cap", price: 219.816, previous: 217.078, change_pct: 1.26, as_of: "2026-10-08", source: "amfi", freshness: { status: "stale", reason: "Data from 08 Oct 2026, never refreshed." } },
  ],
  schedule: { enabled: true, prices: "Mon–Fri 16:00 IST", navs: "Daily 23:30 IST" },
  last_job: null,
  notes: ["Prices are end-of-day closes from Yahoo Finance."],
};

const job = (over: Partial<Job>): Job => ({
  id: 7, kind: "market_refresh", status: "running", trigger: "manual", params: {}, created_at: "2026-10-10T12:00:00+05:30",
  started_at: null, finished_at: null, done: 1, total: 4, message: "Refreshing ITC", errors: [], ...over,
});

function mockFetch(routes: Record<string, () => unknown>) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    const key = Object.keys(routes).find((k) => url.endsWith(k));
    if (!key) return new Response("not found", { status: 404 });
    return new Response(JSON.stringify(routes[key]!()), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MarketData />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("MarketData", () => {
  it("shows prices with Indian formatting and explains anything not fresh", async () => {
    mockFetch({ "/market/status": () => status });
    renderIt();
    expect(await screen.findByText("Reliance Industries")).toBeInTheDocument();
    expect(screen.getByText("22,520.45")).toBeInTheDocument(); // index level: no ₹
    expect(screen.getByText("₹1,170.30")).toBeInTheDocument();
    expect(screen.getByText("₹219.8160")).toBeInTheDocument();
    expect(screen.getByText("−0.65%")).toBeInTheDocument();
    expect(screen.getByText("No data. Last attempt failed: HTTP 503")).toBeInTheDocument();
    expect(screen.getByText("Data from 08 Oct 2026, never refreshed.")).toBeInTheDocument();
    expect(screen.getByText("08 Oct 2026")).toBeInTheDocument();
    // a missing price is a dash, never a number
    const itcRow = screen.getByText("ITC").closest("tr")!;
    expect(itcRow).toHaveTextContent("—");
  });

  it("starts a refresh and tracks the job until it finishes", async () => {
    let polls = 0;
    const fetchMock = mockFetch({
      "/market/status": () => status,
      "/market/refresh": () => job({ status: "queued", done: 0 }),
      "/jobs/7": () => (++polls < 2 ? job({}) : job({ status: "done", done: 4, message: "3 updated, 0 already fresh, 1 failed", errors: ["ITC: HTTP 503"], finished_at: "2026-10-10T12:01:00+05:30" })),
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: /refresh now/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/refresh", expect.objectContaining({ method: "POST" })));
    const body = JSON.parse(fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/market/refresh"))![1]!.body as string);
    expect(body).toEqual({ scope: "all", force: false });
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
    await waitFor(() => expect(polls).toBeGreaterThanOrEqual(2), { timeout: 4000 });
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter((c) => String(c[0]).endsWith("/market/status")).length).toBeGreaterThanOrEqual(2),
    );
  });
});
