import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Holdings, MFHolding, StockHolding } from "../api/client";
import { Import } from "./Import";

const stock = {
  id: 1,
  snapshot_id: 1,
  name: "Reliance Industries Ltd",
  isin: null,
  symbol: "RELIANCE",
  exchange: "NSE",
  resolution: "isin",
  resolution_score: 100,
  suggestions: [],
  quantity: 10,
  avg_price: 2400,
  close_price: null,
  invested: 24000,
  current_value: 25000,
  unrealised_pnl: null,
  purchase_date: null,
} as unknown as StockHolding;

function renderImport(holdings: Holdings) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body =
      init?.method === "DELETE"
        ? { kind: "stocks", snapshots: 1, holdings: 1 }
        : url.includes("/portfolio/holdings")
          ? holdings
          : [];
    return new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Import />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("clearing imported holdings", () => {
  const holdings: Holdings = { stocks_snapshot: null, stocks: [stock], mf_snapshot: null, mf: [] as MFHolding[] };

  it("offers a clear button only for kinds that have holdings", async () => {
    renderImport(holdings);
    expect(await screen.findByRole("button", { name: "Clear stocks" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Clear mutual funds" })).toBeNull();
  });

  it("asks first, and clears only when confirmed", async () => {
    const fetchMock = renderImport(holdings);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const button = await screen.findByRole("button", { name: "Clear stocks" });

    fireEvent.click(button);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);

    fireEvent.click(button);
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/portfolio/stocks" && init?.method === "DELETE")).toBe(true),
    );
  });
});
