import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { NeedsMapping } from "../api/client";
import { ColumnMapper } from "./ColumnMapper";

const need: NeedsMapping = {
  status: "needs_mapping",
  kind: "stocks",
  header_row: 1,
  headers: ["Security", "Identifier", "Holding", "Rate"],
  detected: {},
  missing_required: ["name", "quantity", "avg_price"],
  fields: [
    { key: "name", label: "Stock name", required: true },
    { key: "isin", label: "ISIN", required: false },
    { key: "quantity", label: "Quantity", required: true },
    { key: "avg_price", label: "Average buy price", required: true },
  ],
  preview: [["Reliance", "INE002A01018", "25", "2410.5"]],
};

const select = (label: RegExp, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("ColumnMapper", () => {
  it("blocks import until every required field is mapped, then sends the mapping", () => {
    const onSubmit = vi.fn();
    render(<ColumnMapper need={need} busy={false} onSubmit={onSubmit} onCancel={() => {}} />);
    const submit = screen.getByRole("button", { name: /import with this mapping/i });
    expect(submit).toBeDisabled();

    select(/stock name/i, "0");
    select(/^quantity/i, "2");
    expect(submit).toBeDisabled();
    select(/average buy price/i, "3");
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({
      header_row: 1,
      columns: { name: 0, quantity: 2, avg_price: 3 },
      remember: true,
    });
  });

  it("shows the file preview and the 1-based header row", () => {
    render(<ColumnMapper need={need} busy={false} onSubmit={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("INE002A01018")).toBeInTheDocument();
    expect(screen.getByLabelText(/header row/i)).toHaveValue(2);
  });

  it("changing the header row asks the server to reload columns", () => {
    const onSubmit = vi.fn();
    render(<ColumnMapper need={need} busy={false} onSubmit={onSubmit} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/header row/i), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /reload columns/i }));
    expect(onSubmit).toHaveBeenCalledWith({ header_row: 2, columns: {}, remember: true });
  });

  it("does not offer a column already used by another field", () => {
    render(<ColumnMapper need={{ ...need, detected: { name: 0 } }} busy={false} onSubmit={() => {}} onCancel={() => {}} />);
    const qty = screen.getByLabelText(/^quantity/i) as HTMLSelectElement;
    const security = Array.from(qty.options).find((o) => o.text === "Security");
    expect(security?.disabled).toBe(true);
  });
});
