import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DownloadMenu } from "./DownloadMenu";

describe("DownloadMenu", () => {
  it("offers PDF and CSV, keeping the query string", () => {
    render(<DownloadMenu href="/api/export/screener?preset=growth" />);
    fireEvent.click(screen.getByRole("button", { name: /Download/ }));
    expect(screen.getByRole("link", { name: /PDF/ })).toHaveAttribute("href", "/api/export/screener.pdf?preset=growth");
    expect(screen.getByRole("link", { name: /CSV/ })).toHaveAttribute("href", "/api/export/screener.csv?preset=growth");
  });
});
