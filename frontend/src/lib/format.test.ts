import { describe, expect, it } from "vitest";
import { formatFreshness, formatINR } from "./format";

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
