import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SheetsStatus } from "../api/client";
import { CheckRow, GoogleSheetsSettings, SheetImport, SheetsExportButton } from "./GoogleSheets";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

const EMAIL = "bot@proj.iam.gserviceaccount.com";
const status: SheetsStatus = {
  service_account: { configured: true, path: "/app/secrets/service-account.json", client_email: EMAIL, project_id: "proj", error: null },
  sheet_url: "https://docs.google.com/spreadsheets/d/abc/edit",
  spreadsheet_url: "https://docs.google.com/spreadsheets/d/abc/edit",
  link_error: null,
  settings: { stocks_tab: "Holdings_Stocks", mf_tab: "Holdings_MF", stocks_csv_url: null, mf_csv_url: null, screener_screen: null, auto_export: false },
  export_tabs: { stocks: "Analysis_Stocks", mf: "Analysis_MF", screener: "Screener", summary: "Summary" },
  default_import_tabs: { stocks: "Holdings_Stocks", mf: "Holdings_MF" },
  history: [{ at: "2026-10-10T16:05:00+05:30", direction: "export", detail: "My portfolio", ok: true, message: "Wrote Summary (12 rows)" }],
  refresh_time_ist: "16:00",
};

const json = (body: unknown, code = 200) => new Response(JSON.stringify(body), { status: code });

describe("Google Sheets", () => {
  it("shows check results with words, not colour alone", () => {
    render(
      <ul>
        <CheckRow c={{ name: "Write access", ok: false, detail: "Share the sheet" }} />
        <CheckRow c={{ name: "Import tab", ok: null, detail: "No tab" }} />
      </ul>,
    );
    expect(screen.getByText("(Problem)")).toBeInTheDocument();
    expect(screen.getByText("(Not checked)")).toBeInTheDocument();
  });

  it("asks before overwriting tabs the app didn't write, then sends overwrite", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { overwrite: string[] };
      if (body.overwrite.length === 0) return json({ detail: { message: "Summary has your content", tabs: ["Summary"] } }, 409);
      return json({ url: "https://docs.google.com/spreadsheets/d/abc/edit", title: "My portfolio", tabs: [{ name: "Summary", rows: 12 }], at: "2026-10-10T16:05:00+05:30" });
    });
    vi.stubGlobal("fetch", fetchMock);
    wrap(<SheetsExportButton status={status} />);
    fireEvent.click(screen.getByRole("button", { name: "Export to Google Sheets" }));
    const overwrite = await screen.findByRole("button", { name: "Overwrite Summary" });
    expect(screen.getByText(/Your other tabs are never touched/)).toBeInTheDocument();
    fireEvent.click(overwrite);
    await screen.findByText(/Exported to “My portfolio”/);
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toEqual({ overwrite: ["Summary"] });
    expect(screen.getByRole("link", { name: /Open the sheet/ })).toHaveAttribute("href", "https://docs.google.com/spreadsheets/d/abc/edit");
  });

  it("disables export until the key and the link are set", () => {
    wrap(<SheetsExportButton status={{ ...status, service_account: { ...status.service_account, configured: false, client_email: null } }} />);
    expect(screen.getByRole("button", { name: "Export to Google Sheets" })).toBeDisabled();
    expect(screen.getByText(/Needs a service-account key/)).toBeInTheDocument();
  });

  it("shows the robot e-mail to share with and saves settings", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/sheets/status") return json(status);
      if (url === "/api/screener/config") return json({ presets: [{ key: "top_scores", label: "Top scores" }, { key: "growth", label: "Growth" }], screens: [] });
      if (url === "/api/sheets/settings" && init?.method === "PUT") return json({ ...status, settings: { ...status.settings, auto_export: true } });
      return json({});
    });
    vi.stubGlobal("fetch", fetchMock);
    wrap(<GoogleSheetsSettings />);
    expect(await screen.findByText(EMAIL)).toBeInTheDocument();
    expect(screen.getByText(/Last export:/)).toBeInTheDocument();
    expect(screen.getByText("Export succeeded")).toBeInTheDocument();
    await screen.findByRole("option", { name: "Growth" });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "preset:growth" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Export automatically after the daily refresh/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("✓ Saved");
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(String(put[1]?.body))).toMatchObject({
      sheet_url: status.sheet_url,
      screener_screen: "preset:growth",
      auto_export: true,
      stocks_csv_url: null,
    });
  });

  it("imports from a published link and hands back the result", async () => {
    const imported = { status: "imported", snapshot: { id: 3, kind: "mf", row_count: 2 }, skipped: [], warnings: [], unresolved: 0 };
    const fetchMock = vi.fn(async (url: string) => (url === "/api/sheets/status" ? json(status) : json(imported)));
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    wrap(<SheetImport onDone={onDone} />);
    await screen.findByDisplayValue("Holdings_Stocks");
    fireEvent.click(screen.getByLabelText("Mutual funds"));
    fireEvent.click(screen.getByLabelText("A published CSV link"));
    const btn = screen.getByRole("button", { name: "Import from Google Sheets" });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/pub\?output=csv/), { target: { value: "https://docs.google.com/spreadsheets/d/e/X/pub?output=csv" } });
    fireEvent.click(btn);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([u]) => u === "/api/sheets/import")!;
    expect(JSON.parse(String((post as unknown as [string, RequestInit])[1].body))).toEqual({
      kind: "mf",
      source: "csv",
      url: "https://docs.google.com/spreadsheets/d/e/X/pub?output=csv",
    });
  });
});
