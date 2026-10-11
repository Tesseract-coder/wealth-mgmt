import { describe, expect, it } from "vitest";
import { formatDate, formatFreshness, formatINR, formatINRCompact, formatNumber, formatPct } from "./format";

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
    expect(formatPct(1.234)).toBe("+1.2%");
    expect(formatPct(-0.65)).toBe("−0.7%");
    expect(formatPct(0)).toBe("0.0%");
    expect(formatPct(-0.04)).toBe("0.0%");
    expect(formatPct(1.234, 2)).toBe("+1.23%");
    expect(formatPct(null)).toBe("—");
  });
});

describe("formatINRCompact", () => {
  it.each([
    [0, "₹0"],
    [45230.4, "₹45,230"],
    [99999, "₹99,999"],
    [124000, "₹1.2 L"],
    [1240000, "₹12.4 L"],
    [9999999, "₹1.0 Cr"],
    [32000000, "₹3.2 Cr"],
    [15837053400000, "₹15,83,705 Cr"],
    [-1328.67, "−₹1,329"],
    [-612221, "−₹6.1 L"],
  ])("%s -> %s", (amount, expected) => {
    expect(formatINRCompact(amount)).toBe(expected);
  });

  it("signs gains on request and shows a dash for missing values", () => {
    expect(formatINRCompact(8948.27, { signed: true })).toBe("+₹8,948");
    expect(formatINRCompact(-8948.27, { signed: true })).toBe("−₹8,948");
    expect(formatINRCompact(null)).toBe("—");
  });
});
