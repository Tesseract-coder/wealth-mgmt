import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScreenerImport } from "./ScreenerImport";

afterEach(() => vi.unstubAllGlobals());

describe("ScreenerImport", () => {
  it("uploads the file and reports matched, unmatched and warnings", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          status: "imported",
          kind: "screen",
          upload_id: 1,
          matched: [{ symbol: "TCS", name: "TCS" }],
          unmatched: ["Acme Imaginary Widgets"],
          warnings: ["Add the 'NSE Code' column"],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const qc = new QueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ScreenerImport />
      </QueryClientProvider>,
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "screen.csv", { type: "text/csv" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/saved for 1 stock\(s\): TCS/)).toBeInTheDocument();
    expect(screen.getByText(/Not matched to an NSE symbol: Acme Imaginary Widgets/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/import/screener", expect.objectContaining({ method: "POST" }));
  });
});
