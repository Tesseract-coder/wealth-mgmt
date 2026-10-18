import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StyleSwitcher } from "./StyleSwitcher";

afterEach(() => vi.unstubAllGlobals());

const CONFIG = {
  version: 1,
  styles: { swing: { label: "Swing" }, long_term: { label: "Long-term" } },
  risk_levels: {},
  disclaimer: "",
};
const PROFILE = { style: "swing", risk: "medium", custom_technical_weight: 0.5, gsheet_url: null, onboarded: true, updated_at: "" };

function Where() {
  return <span data-testid="where">{useLocation().search}</span>;
}

describe("Style switcher", () => {
  it("shows the page's style, saves a new one to the profile and drops the ?style= override", async () => {
    const saved: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          saved.push(body);
          return new Response(JSON.stringify({ ...PROFILE, ...body }));
        }
        return new Response(JSON.stringify(url.endsWith("/config") ? CONFIG : PROFILE));
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/holdings?style=long_term&layout=table"]}>
          <StyleSwitcher />
          <Where />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const select = await screen.findByRole("combobox", { name: "Style" });
    expect(select).toHaveValue("long_term");
    fireEvent.change(select, { target: { value: "swing" } });
    await waitFor(() => expect(saved).toEqual([{ style: "swing", risk: "medium" }]));
    expect(screen.getByTestId("where")).toHaveTextContent("?layout=table");
    await waitFor(() => expect(select).toHaveValue("swing"));
  });
});
