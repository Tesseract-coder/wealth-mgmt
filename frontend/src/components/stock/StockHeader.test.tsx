import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SAMPLE_STOCK } from "../analysis/samples";
import { StockHeader } from "./StockHeader";

function show(ticker: string, unscored: number) {
  const sections = SAMPLE_STOCK.sections.map((s, i) => (i < unscored ? { ...s, score: null } : s));
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StockHeader ticker={ticker} checks={{ ...SAMPLE_STOCK, sections, max_total: 24 }} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StockHeader", () => {
  it("marks a BSE-only share and data too thin to score", () => {
    show("ANDHRAPET.BO", 2);
    expect(screen.getByText("BSE only")).toBeInTheDocument();
    expect(screen.getByText("Limited data").closest("[title]")).toHaveAttribute("title", expect.stringContaining("out of 24"));
    expect(screen.getByRole("link", { name: /Compare/ })).toBeInTheDocument();
  });

  it("adds neither for a well-covered NSE stock", () => {
    show("RELIANCE.NS", 1);
    expect(screen.queryByText("BSE only")).not.toBeInTheDocument();
    expect(screen.queryByText("Limited data")).not.toBeInTheDocument();
  });
});
