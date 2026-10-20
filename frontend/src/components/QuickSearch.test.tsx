import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Holdings } from "../api/client";
import { QuickSearch, searchItems, tickerFromInput } from "./QuickSearch";

const HOLDINGS = {
  stocks_snapshot: null,
  mf_snapshot: null,
  stocks: [
    { symbol: "TCS", exchange: "NSE", name: "Tata Consultancy", current_value: 100 },
    { symbol: "500325", exchange: "BSE", name: "Reliance Industries", current_value: 300 },
    { symbol: null, exchange: null, name: "Unresolved Co", current_value: 50 },
  ],
  mf: [{ scheme_name: "Parag Parikh Flexi Cap Fund - Direct Plan - Growth", amfi_code: "122639" }],
} as unknown as Holdings;

describe("searchItems", () => {
  it("with nothing typed lists your stocks by value, your funds and the pages", () => {
    const items = searchItems("", HOLDINGS, [], undefined, undefined);
    expect(items.filter((i) => i.group === "Your stocks").map((i) => i.href)).toEqual(["/analysis/500325.BO", "/analysis/TCS.NS"]);
    expect(items.find((i) => i.group === "Your funds")?.href).toBe("/mutual-funds/122639");
    expect(items.some((i) => i.group === "Pages" && i.href === "/holdings")).toBe(true);
  });

  it("puts your holdings before the whole market and drops repeats and weak matches", () => {
    const stocks = [
      { symbol: "TCS", amfi_code: null, name: "Tata Consultancy", score: 100 },
      { symbol: "TATAELXSI", amfi_code: null, name: "Tata Elxsi", score: 90 },
      { symbol: "XYZ", amfi_code: null, name: "Barely Related", score: 30 },
    ];
    const items = searchItems("tata", HOLDINGS, ["TATAMOTORS.NS"], stocks, []);
    expect(items.map((i) => `${i.group}|${i.href}`)).toEqual([
      "Your stocks|/analysis/TCS.NS",
      "Watchlist|/analysis/TATAMOTORS.NS",
      "All stocks|/analysis/TATAELXSI.NS",
      "Open|/analysis/TATA.NS",
    ]);
  });

  it("opens BSE-only shares by their .BO ticker", () => {
    const stocks = [{ symbol: "ANDHRAPET", amfi_code: null, name: "Andhra Petrochemicals", score: 95, exchange: "BSE" as const }];
    expect(searchItems("andhra", HOLDINGS, [], stocks, []).find((i) => i.group === "All stocks")?.href).toBe("/analysis/ANDHRAPET.BO");
  });

  it("offers to open a symbol as typed", () => {
    expect(tickerFromInput("infy")).toBe("INFY.NS");
    expect(tickerFromInput("500325.bo")).toBe("500325.BO");
    expect(tickerFromInput("^nsei")).toBe("^NSEI");
    expect(tickerFromInput("two words")).toBeNull();
  });
});

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

afterEach(() => vi.unstubAllGlobals());

describe("QuickSearch", () => {
  it("opens with Ctrl+K, moves with the arrow keys and opens the choice with Enter", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const body = url.includes("/portfolio/holdings") ? HOLDINGS : [];
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <QuickSearch />
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Search" });
    const box = within(dialog).getByRole("combobox");
    expect(box).toHaveFocus();
    expect(await within(dialog).findByRole("option", { name: /Reliance Industries/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(within(dialog).getByRole("option", { name: /Tata Consultancy/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/analysis/TCS.NS");
  });

  it("closes with Escape and opens with / when not typing", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <QuickSearch />
          <input aria-label="other field" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.keyDown(screen.getByLabelText("other field"), { key: "/" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); // typing "/" in a field stays a "/"
    fireEvent.keyDown(document.body, { key: "/" });
    const box = screen.getByRole("combobox");
    fireEvent.keyDown(box, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
