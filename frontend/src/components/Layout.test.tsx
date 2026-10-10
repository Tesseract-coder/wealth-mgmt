import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { MarketStatus } from "../api/client";
import { closeTime, freshnessText } from "./FreshnessBar";
import { Layout } from "./Layout";

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Layout", () => {
  it("always renders the disclaimer footer", () => {
    renderLayout();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(
      "This is not investment advice. Consult a SEBI-registered investment adviser before acting.",
    );
  });

  it("has a menu button for small screens", () => {
    renderLayout();
    const btn = screen.getByRole("button", { name: /Menu/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });
});

describe("Freshness line", () => {
  it("states the latest close in IST and counts stale items", () => {
    const quote = (kind: "stock" | "benchmark" | "mf", as_of: string | null) => ({
      kind, code: "x", label: "x", price: 1, previous: 1, change_pct: 0, as_of, source: null, freshness: { status: "fresh" as const, reason: "" },
    });
    const s = {
      quotes: [quote("stock", "2026-10-08"), quote("benchmark", "2026-10-09"), quote("mf", "2026-10-08"), quote("stock", null)],
      summary: { fresh: 3, stale: 1, unavailable: 1 },
    } as unknown as MarketStatus;
    const f = freshnessText(s);
    expect(f.prices).toBe("Prices as of 09 Oct 2026, 3:30 PM IST");
    expect(f.navs).toBe("NAVs as of 08 Oct 2026");
    expect(f.stale).toBe(2);
    expect(closeTime("2026-10-09").toISOString()).toBe("2026-10-09T10:00:00.000Z");
  });
});
