import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SectionResult } from "../../api/client";
import {
  axesFromPortfolio,
  axesFromRecord,
  axesFromSections,
  ChartFigure,
  CheckList,
  FundSignalPill,
  orderAxes,
  RewardsRisks,
  ScoreShape,
  SectionHeader,
  SignalPill,
  stepFor,
} from ".";
import { SAMPLE_FUND, SAMPLE_HOLDINGS, SAMPLE_STOCK } from "./samples";

const stockAxes = axesFromSections(SAMPLE_STOCK.sections);
const section = (key: string): SectionResult => SAMPLE_STOCK.sections.find((s) => s.key === key)!;

describe("ScoreShape helpers", () => {
  it("maps the share of the maximum to colour steps 1–5 like checks.yaml", () => {
    expect(stepFor(0, 36)).toBe(1);
    expect(stepFor(7.2, 36)).toBe(2); // exactly 20%
    expect(stepFor(19, 36)).toBe(3);
    expect(stepFor(23.4, 36)).toBe(4);
    expect(stepFor(36, 36)).toBe(5);
  });

  it("puts Momentum first for swing and intraday, and leaves other styles alone", () => {
    expect(orderAxes(stockAxes, "swing").map((a) => a.key)).toEqual(["momentum", "valuation", "growth", "past", "health", "dividends"]);
    expect(orderAxes(stockAxes, "intraday")[0]!.key).toBe("momentum");
    expect(orderAxes(stockAxes, "long_term")).toBe(stockAxes);
    expect(orderAxes(stockAxes, null)).toBe(stockAxes);
  });

  it("describes each axis with its pass count and headline pass and fail", () => {
    const valuation = stockAxes[0]!;
    expect(valuation).toMatchObject({ key: "valuation", label: "Valuation", score: 2 });
    expect(valuation.detail).toEqual([
      "2 of 6 checks passed",
      "Top pass: P/E below its own recent median",
      "Top fail: P/E below the sector median",
    ]);
  });

  it("builds axes from a bare record and from the portfolio shape", () => {
    const h = SAMPLE_HOLDINGS.holdings[0]!;
    expect(axesFromRecord(h.axes).map((a) => a.label)).toEqual(["Valuation", "Future Growth", "Past Performance", "Financial Health", "Momentum", "Dividends"]);
    expect(axesFromPortfolio(SAMPLE_HOLDINGS.portfolio)[0]!.detail).toContain("Covers 82% of stock value");
  });
});

describe("ScoreShape", () => {
  it("labels the SVG with every axis score and the total", () => {
    render(<ScoreShape axes={stockAxes} total={19} maxTotal={36} step={3} name="Reliance" size="lg" />);
    const img = screen.getByRole("img", { name: /Score Shape for Reliance/ });
    const label = img.getAttribute("aria-label")!;
    expect(label).toContain("Valuation 2 of 6");
    expect(label).toContain("Financial Health 6 of 6");
    expect(label).toContain("Momentum 0 of 6");
    expect(label).toContain("total 19 of 36");
    expect(img.querySelector("title")?.textContent).toBe(label);
    expect(document.body).toHaveTextContent("Total 19/36");
  });

  it("fills with the score colour for the step and writes the total as text", () => {
    const { container } = render(<ScoreShape axes={stockAxes} step={3} />);
    expect(container.querySelector("[data-testid=shape-fill] polygon")?.getAttribute("fill")).toBe("var(--score-3)");
    expect(screen.getByText("19")).toBeInTheDocument();
  });

  it("works out the total and step itself when not given", () => {
    const { container } = render(<ScoreShape axes={axesFromRecord({ a: 6, b: 6, c: 6, d: 5 })} />);
    expect(container.querySelector("[data-testid=shape-fill] polygon")?.getAttribute("fill")).toBe("var(--score-5)");
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("total 23 of 24");
  });

  it("reads out each axis with the arrow keys", () => {
    render(<ScoreShape axes={stockAxes} size="lg" />);
    const group = screen.getByRole("group", { name: /arrow keys/ });
    fireEvent.focus(group);
    expect(screen.getByText("Valuation: 2/6")).toBeInTheDocument();
    fireEvent.keyDown(group, { key: "ArrowRight" });
    expect(screen.getByText("Future Growth: 3/6")).toBeInTheDocument();
    fireEvent.keyDown(group, { key: "ArrowLeft" });
    fireEvent.keyDown(group, { key: "ArrowLeft" });
    expect(screen.getByText("Dividends: 5/6")).toBeInTheDocument();
    expect(screen.getByText("Top pass: Payout under 75% of profit")).toBeInTheDocument();
  });

  it("shows an axis's detail when it is tapped", () => {
    const { container } = render(<ScoreShape axes={stockAxes} size="md" />);
    fireEvent.click(container.querySelector("[data-axis=health]")!);
    expect(screen.getByText("Financial Health: 6/6")).toBeInTheDocument();
    expect(screen.getByText("Top pass: Debt within your risk limit")).toBeInTheDocument();
  });

  it("says when an axis has too little data", () => {
    const fund = axesFromSections(SAMPLE_FUND.sections);
    render(<ScoreShape axes={fund} size="lg" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Cost not enough data");
    expect(screen.getByText("no data", { exact: false })).toBeInTheDocument();
  });

  it("shows the style label for swing and keeps the scores", () => {
    render(<ScoreShape axes={stockAxes} style="swing" size="lg" />);
    expect(screen.getByText("Style: Swing")).toBeInTheDocument();
    const label = screen.getByRole("img").getAttribute("aria-label")!;
    expect(label.indexOf("Momentum 0 of 6")).toBeLessThan(label.indexOf("Valuation 2 of 6"));
  });

  it("is a static, untabbable thumbnail at sm size", () => {
    render(<ScoreShape axes={stockAxes} size="sm" />);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("width", "32");
  });

  it("falls back to text with fewer than three axes", () => {
    render(<ScoreShape axes={axesFromRecord({ momentum: 3 })} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Momentum 3 of 6")).toBeInTheDocument();
  });
});

describe("CheckList", () => {
  it("shows the status, the plain-English line, and the value against its threshold", () => {
    render(<CheckList checks={section("valuation").checks} label="Valuation checks" />);
    const rows = within(screen.getByRole("list", { name: "Valuation checks" })).getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent("Fail");
    expect(rows[0]).toHaveTextContent("P/E of 19.6× is above the sector median of 13.3×");
    expect(rows[0]).toHaveTextContent("Value19.6×");
    expect(rows[0]).toHaveTextContent("vs13.3×");
    expect(rows[1]).toHaveTextContent("Pass");
    expect(screen.getAllByRole("button", { name: /^About / })).toHaveLength(6);
  });

  it("marks missing data as no data, not as a pass or fail", () => {
    render(<CheckList checks={section("health").checks} />);
    const pledge = screen.getByText("Under 5% of promoter shares pledged").closest("li")!;
    expect(pledge).toHaveTextContent("No data");
    expect(pledge).not.toHaveTextContent(/\bPass\b|\bFail\b/);
  });

  it("drops the explanations and figures when compact", () => {
    render(<CheckList checks={section("valuation").checks} compact />);
    expect(screen.queryByText(/costs more than its peers/)).not.toBeInTheDocument();
    expect(screen.queryByText("19.6×")).not.toBeInTheDocument();
  });
});

describe("SectionHeader", () => {
  it("shows x/6 checks, the bar and the axis score", () => {
    render(<SectionHeader section={section("valuation")} id="valuation" />);
    expect(screen.getByRole("heading", { level: 2, name: "Valuation" })).toBeInTheDocument();
    expect(screen.getByText("Is the price reasonable?")).toBeInTheDocument();
    expect(screen.getByText("2/6 checks")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "2 passed, 4 failed" })).toBeInTheDocument();
    expect(screen.getByText("2/6")).toBeInTheDocument();
  });

  it("counts checks without data and explains the rounding", () => {
    render(<SectionHeader section={section("health")} />);
    expect(screen.getByText("· 1 no data", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "5 passed, 0 failed, 1 no data" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About Financial Health score" })).toBeInTheDocument();
  });

  it("says when there is not enough data to score", () => {
    render(<SectionHeader section={SAMPLE_FUND.sections.find((s) => s.key === "cost")!} level={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "Cost" })).toBeInTheDocument();
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
  });
});

describe("RewardsRisks", () => {
  it("lists rewards and risks with counts", () => {
    render(<RewardsRisks rewards={SAMPLE_STOCK.rewards} risks={SAMPLE_STOCK.risks} />);
    expect(screen.getByRole("heading", { name: "Rewards (2)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Risks (5)" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Risks" })).getAllByRole("listitem")).toHaveLength(5);
  });

  it("collapses long lists and explains empty ones", () => {
    render(<RewardsRisks rewards={[]} risks={SAMPLE_STOCK.risks} limit={2} notes={["Funds have their own shapes."]} />);
    expect(screen.getByText("No standout strengths in the checks.")).toBeInTheDocument();
    const risks = screen.getByRole("region", { name: "Risks" });
    expect(within(risks).getAllByRole("listitem")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Show all 5" }));
    expect(within(risks).getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("Funds have their own shapes.")).toBeInTheDocument();
  });
});

describe("ChartFigure", () => {
  it("wraps a chart with a title, an accessible label and its caption", () => {
    render(
      <ChartFigure title="Debt vs equity" label="Debt and equity by year" caption="Debt fell from 0.47× to 0.44× equity over 3 years." source="Yahoo Finance">
        <svg />
      </ChartFigure>,
    );
    const fig = screen.getByRole("figure", { name: "Debt and equity by year" });
    expect(within(fig).getByText(/Debt fell from 0.47×/)).toBeInTheDocument();
    expect(within(fig).getByText("Source: Yahoo Finance")).toBeInTheDocument();
  });
});

describe("Signal pills", () => {
  it("always pair the colour with an icon and text", () => {
    const { container } = render(
      <>
        <SignalPill signal="sell" label="Sell / Exit" />
        <FundSignalPill signal="switch" label="Switch" size="md" />
      </>,
    );
    expect(screen.getByText("Sell / Exit")).toBeInTheDocument();
    expect(screen.getByText("Switch")).toBeInTheDocument();
    expect(container.querySelectorAll("svg[aria-hidden]")).toHaveLength(2);
  });
});
