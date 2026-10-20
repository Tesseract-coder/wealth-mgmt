import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StockRow, StocksPage } from "../api/client";
import { Stocks } from "./Stocks";

const row = (o: Partial<StockRow>): StockRow => ({
  ticker: "TCS.NS", symbol: "TCS", name: "Tata Consultancy", exchange: "NSE", index: "nifty50", sector: "Information Technology",
  mcap_cr: 1_200_000, close: 3100.5, as_of: "2026-10-19", loaded: true, held: true, watched: false, ...o,
});

afterEach(() => vi.unstubAllGlobals());

function setup(total = 2) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      const rows = [row({}), row({ ticker: "ANDHRAPET.BO", symbol: "ANDHRAPET", name: "Andhra Petrochemicals", exchange: "BSE", index: null, sector: null, mcap_cr: null, close: null, as_of: null, loaded: false, held: false })];
      const body: StocksPage = { total, all: 4547, loaded: 588, rows, sectors: [{ name: "Information Technology", count: 1 }] };
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Stocks />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return urls;
}

describe("All stocks", () => {
  it("lists NSE and BSE-only stocks, says which aren't loaded and links to each", async () => {
    setup();
    expect(await screen.findByText(/588 of 4,547 are loaded so far/)).toBeInTheDocument();
    const bse = screen.getByRole("link", { name: "Andhra Petrochemicals" });
    expect(bse).toHaveAttribute("href", "/analysis/ANDHRAPET.BO");
    const bseRow = bse.closest("tr")!;
    expect(within(bseRow).getByText("BSE only")).toBeInTheDocument();
    expect(within(bseRow).getByText(/Not loaded yet/)).toBeInTheDocument();
    const tcsRow = screen.getByRole("link", { name: "Tata Consultancy" }).closest("tr")!;
    expect(within(tcsRow).getByText("Held")).toBeInTheDocument();
    expect(within(tcsRow).getByText("₹12,00,000 Cr")).toBeInTheDocument();
  });

  it("sends the filters to the server and loads more on request", async () => {
    const urls = setup(250);
    await screen.findByText(/588 of 4,547/);
    fireEvent.click(screen.getByRole("radio", { name: "BSE only" }));
    fireEvent.change(screen.getByLabelText("Index"), { target: { value: "outside" } });
    fireEvent.click(screen.getByLabelText("Loaded only"));
    await vi.waitFor(() => expect(urls.at(-1)).toContain("exchange=BSE&index=outside&loaded=true"));
    fireEvent.click(await screen.findByRole("button", { name: "Show 100 more" }));
    await vi.waitFor(() => expect(urls.at(-1)).toContain("limit=200"));
  });
});
