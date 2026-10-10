import { describe, expect, it } from "vitest";
import { formatDate, formatFreshness, formatINR, formatNumber, formatPct } from "./format";

describe("formatINR", () => {
  it.each([
    [0, "₹0.00"],
    [999, "₹999.00"],
    [123456.78, "₹1,23,456.78"],
    [12345678.9, "₹1,23,45,678.90"],
    [-1234567, "-₹12,34,567.00"],
  ])("%s -> %s", (amount, expected) => {
    expect(formatINR(amount)).toBe(expected);
  });

  it("shows a dash for missing values", () => {
    expect(formatINR(null)).toBe("—");
    expect(formatINR(undefined)).toBe("—");
  });
});

describe("formatFreshness", () => {
  it("converts to IST", () => {
    expect(formatFreshness(new Date("2026-10-09T10:00:00Z"))).toBe("09 Oct 2026, 3:30 PM IST");
  });
});

describe("formatDate / formatNumber / formatPct", () => {
  it("formats calendar dates without shifting the day", () => {
    expect(formatDate("2026-10-09")).toBe("09 Oct 2026");
    expect(formatDate(null)).toBe("—");
  });
  it("uses Indian grouping for non-rupee numbers", () => {
    expect(formatNumber(2252045.5)).toBe("22,52,045.50");
    expect(formatNumber(null)).toBe("—");
  });
  it("signs percentages", () => {
    expect(formatPct(1.234)).toBe("+1.23%");
    expect(formatPct(-0.65)).toBe("−0.65%");
    expect(formatPct(0)).toBe("0.00%");
    expect(formatPct(null)).toBe("—");
  });
});
