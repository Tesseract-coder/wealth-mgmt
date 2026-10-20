import { describe, expect, it } from "vitest";
import { SAMPLE_HISTORY } from "./samples";
import {
  cagr,
  crore,
  debtCaption,
  dividendCaption,
  fairValueCaption,
  growthCaption,
  marginCaption,
  ownershipCaption,
  peCaption,
  quarterCaption,
  roeCaption,
  rsiZone,
} from "./captions";

const years = SAMPLE_HISTORY.years;
const fv = { label: "Estimate" as const, value: 879.77, price: 1170.3, gap_pct: 33, methods: [], caveat: "" };

describe("chart captions", () => {
  it("formats crore amounts with Indian grouping or the statement currency", () => {
    expect(crore(398000)).toBe("₹3,98,000 Cr");
    expect(crore(12400, "USD Cr")).toBe("12,400 USD Cr");
  });

  it("works out compound growth and refuses negative starts", () => {
    expect(cagr(100, 121, 2)).toBeCloseTo(10);
    expect(cagr(-5, 10, 2)).toBeNull();
  });

  it("says whether the price is above or below fair value", () => {
    expect(fairValueCaption(fv, 1170.3)).toBe("Price ₹1,170.30 is 33.0% above the estimated fair value of ₹879.77: dearer than its sector's multiples suggest.");
    expect(fairValueCaption({ ...fv, gap_pct: -12, price: 774.2 }, 774.2)).toContain("12.0% below");
    expect(fairValueCaption(null, 100)).toMatch(/^No fair-value estimate/);
    expect(fairValueCaption({ ...fv, value: 0, gap_pct: null, price: 39.83 }, 39.83)).toBe(
      "Price ₹39.83 is far above the estimated fair value of ₹0.00: at its sector's multiples the business is worth less than its debt.",
    );
  });

  it("compares P/E with the sector and its own history", () => {
    expect(peCaption(19.6, 13.3, 23.6)).toBe("P/E of 19.6× is above the sector median of 13.3× and below its own recent median of 23.6×.");
    expect(peCaption(null, 13.3, null)).toMatch(/made a loss/);
  });

  it("describes growth, margins and ROE from the yearly results", () => {
    expect(growthCaption(years)).toMatch(/^Revenue grew from ₹[\d,]+ Cr to ₹10,57,219 Cr over 3 years \(\d+\.\d% a year\); profit grew \d+\.\d% a year\.$/);
    expect(marginCaption(years)).toMatch(/^Operating margin (held steady at about|rose from|fell from) .*11\.5% over 3 years\.$/);
    expect(roeCaption(years)).toMatch(/to 8\.9% over 3 years: a weak return/);
    expect(growthCaption([])).toBe("Not enough yearly results to show growth.");
  });

  it("tells the debt story in debt-to-equity terms", () => {
    expect(debtCaption(years)).toBe("Debt has fallen from 0.47× to 0.44× equity over 3 years.");
    const rising = [
      { fy: "FY2024", year_end: "2024-03-31", debt_equity: 0.4 },
      { fy: "FY2025", year_end: "2025-03-31", debt_equity: 0.9 },
    ];
    expect(debtCaption(rising)).toBe("Debt has risen from 0.40× to 0.90× equity over 1 year.");
    expect(debtCaption([{ fy: "FY2025", year_end: "2025-03-31", debt_equity: 0.01 }, { fy: "FY2026", year_end: "2026-03-31", debt_equity: 0 }])).toBe("Practically debt-free over 1 year.");
  });

  it("compares the latest quarter with a year earlier", () => {
    expect(quarterCaption(SAMPLE_HISTORY.quarters)).toMatch(/^In the Jun 2026 quarter, revenue up \d+\.\d% and profit (up|down) \d+\.\d% on a year earlier\.$/);
    expect(quarterCaption([])).toBe("No quarterly results.");
  });

  it("covers dividends, RSI zones and ownership", () => {
    expect(dividendCaption(years)).toMatch(/^Paid ₹7,443 Cr in dividends in FY2026, rising from .*; that's 9% of profit\.$/);
    expect(dividendCaption([{ fy: "FY2026", year_end: "2026-03-31", dividends_paid: 0 }])).toBe("No dividends paid in the years on record.");
    expect(rsiZone(35.4)).toMatch(/^weak/);
    expect(rsiZone(55)).toMatch(/^healthy/);
    expect(rsiZone(75)).toMatch(/^overbought/);
    expect(rsiZone(20)).toMatch(/^oversold/);
    expect(ownershipCaption(50.1, -0.4, 0)).toBe("Promoters own 50.1%, down 0.4 pp, with none of their shares pledged.");
    expect(ownershipCaption(null, null, null)).toMatch(/Upload Screener.in data/);
  });
});
