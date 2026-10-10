"""Generate FAKE Groww-style exports for testing. All quantities, prices and names are made up.

Run from the repo root:  cd backend && uv run python ../sample_data/generate_samples.py
"""

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

OUT = Path(__file__).resolve().parent
BANNER = "FAKE SAMPLE DATA - for testing only"

# (name, ISIN, qty, avg buy price, closing price)
STOCKS = [
    ("Reliance Industries Ltd", "INE002A01018", 25, 2410.50, 2875.10),
    ("Tata Consultancy Services Ltd", "INE467B01029", 10, 3620.00, 3412.35),
    ("HDFC Bank Ltd", "INE040A01034", 40, 1495.25, 1688.90),
    ("Infosys Ltd", "INE009A01021", 30, 1402.80, 1530.45),
    ("ITC Ltd", "INE154A01025", 120, 412.10, 438.60),
    ("ICICI Bank Ltd", "INE090A01021", 35, 965.40, 1302.15),
    ("State Bank of India", "INE062A01020", 60, 612.75, 818.30),
    ("Asian Paints Ltd", "INE021A01026", 8, 3150.00, 2465.80),
    ("Bharti Airtel Ltd", "INE397D01024", 22, 880.00, 1795.40),
    ("Larsen & Toubro Ltd", "INE018A01030", 12, 2280.60, 3540.25),
    ("Nippon India ETF Nifty 50 BeES", "INF204KB14I2", 150, 228.40, 281.15),
]

# (Groww-style scheme name, AMC, category, sub-category, folio, units, invested, current value)
FUNDS = [
    ("Parag Parikh Flexi Cap Fund Direct Growth", "PPFAS Mutual Fund", "Equity", "Flexi Cap",
     "12345678/90", 812.345, 55000.00, 71210.32),
    ("Mirae Asset Large Cap Fund Regular Growth", "Mirae Asset Mutual Fund", "Equity",
     "Large Cap", "7890123", 402.117, 40000.00, 41908.71),
    ("UTI Nifty 50 Index Fund Direct Growth", "UTI Mutual Fund", "Equity", "Large Cap",
     "556677/12", 310.502, 42000.00, 48607.34),
    ("SBI Small Cap Fund Direct Growth", "SBI Mutual Fund", "Equity", "Small Cap",
     "19283746", 145.880, 25000.00, 29744.51),
    ("Axis ELSS Tax Saver Fund Direct Growth", "Axis Mutual Fund", "Equity", "ELSS",
     "91234567/01", 288.640, 27000.00, 30021.15),
]


def stocks_xlsx() -> None:
    """Mimics the Groww web Holdings report: account block, summary block, then the table."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Holdings"
    ws.append(["Name", "Demo Investor"])
    ws.append(["Unique Client Code", "0000000000"])
    ws.append([BANNER])
    ws.append([])
    ws.append(["Holdings statement as on 08-10-2026"])
    ws.append([])
    ws.append(["Summary"])
    invested = sum(q * a for _, _, q, a, _ in STOCKS)
    value = sum(q * c for _, _, q, _, c in STOCKS)
    ws.append(["Invested Value", round(invested, 2)])
    ws.append(["Closing Value", round(value, 2)])
    ws.append(["Unrealised P&L", round(value - invested, 2)])
    ws.append([])
    header = ["Stock Name", "ISIN", "Quantity", "Average buy price", "Buy value",
              "Closing price", "Closing value", "Unrealised P&L"]
    ws.append(header)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for name, isin, q, a, c in STOCKS:
        ws.append([name, isin, q, a, round(q * a, 2), c, round(q * c, 2), round(q * (c - a), 2)])
    wb.save(OUT / "groww_stocks_holdings.xlsx")


def stocks_messy_csv() -> None:
    """Renamed headers, ₹ and Indian commas, a missing ISIN, an unknown stock, a duplicate
    (pledged) row, a Total row and a footnote."""
    rows: list[list[str]] = [
        [BANNER],
        ["Groww - Equity Holdings"],
        ["Generated on", "09 Oct 2026"],
        [],
        ["Company", "ISIN Code", "Qty.", "Avg. Cost (₹)", "LTP", "Current Value (₹)", "P&L"],
    ]

    def inr(x: float) -> str:
        whole, frac = f"{x:.2f}".split(".")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            parts = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            whole = ",".join(parts) + "," + tail
        return f"₹{whole}.{frac}"

    for name, isin, q, a, c in STOCKS[:6]:
        pnl = q * (c - a)
        pnl_s = inr(abs(pnl)) if pnl >= 0 else f"({inr(abs(pnl))})"
        rows.append([name, isin, str(q), inr(a), inr(c), inr(q * c), pnl_s])
    rows.append(["HDFC Bank Ltd", "INE040A01034", "5", "₹1,520.00", "₹1,688.90", "₹8,444.50",
                 "₹844.50"])  # pledged lot of the same stock
    rows.append(["Bajaj Finance Limited", "", "4", "₹6,850.00", "₹7,120.00", "₹28,480.00",
                 "₹1,080.00"])  # no ISIN → name match
    rows.append(["Acme Widgets Ltd", "INE000X01999", "100", "₹45.00", "₹52.00", "₹5,200.00",
                 "₹700.00"])  # not a real company → unresolved
    rows.append(["Sold Out Co Ltd", "INE111X01111", "0", "₹10.00", "₹12.00", "₹0.00", "-"])
    rows.append([])
    rows.append(["Total", "", "", "", "", "₹9,99,999.00", ""])
    rows.append(["* Prices are delayed. This is a fake file."])
    with open(OUT / "groww_stocks_messy.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)


def stocks_unknown_headers_csv() -> None:
    """Headers no fuzzy matcher should guess: forces the manual column-mapping step."""
    rows = [
        [BANNER],
        ["Security", "Identifier", "Holding", "Rate", "Mkt"],
    ]
    for name, isin, q, a, c in STOCKS[:4]:
        rows.append([name, isin, str(q), f"{a:.2f}", f"{c:.2f}"])
    with open(OUT / "groww_stocks_unknown_headers.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def mf_xlsx() -> None:
    """Mimics the Groww mutual fund holdings export."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Mutual Funds"
    ws.append(["Personal Details"])
    ws.append(["Name", "Demo Investor"])
    ws.append(["PAN", "XXXXX0000X"])
    ws.append([BANNER])
    ws.append([])
    ws.append(["Holding Summary"])
    ws.append(["Total Investments", sum(f[6] for f in FUNDS)])
    ws.append(["Current Portfolio Value", sum(f[7] for f in FUNDS)])
    ws.append([])
    ws.append(["Scheme Name", "AMC", "Category", "Sub-category", "Folio No.", "Source",
               "Units", "Invested Value", "Current Value", "Returns", "XIRR"])
    for name, amc, cat, sub, folio, units, inv, cur in FUNDS:
        ws.append([name, amc, cat, sub, folio, "Groww", units, inv, cur, round(cur - inv, 2),
                   "12.3%"])
    wb.save(OUT / "groww_mf_holdings.xlsx")


def mf_messy_csv() -> None:
    """A renamed scheme, a name without plan/option, an unknown fund and a total row."""
    rows = [
        [BANNER],
        [],
        ["Fund Name", "Folio Number", "Balance Units", "Amount Invested", "Market Value"],
        ["HDFC Mid-Cap Opportunities Fund Direct Growth", "1122334", "95.5", "15,000",
         "20,731.20"],  # old name → suggestion only
        ["Parag Parikh Flexi Cap Fund", "12345678/90", "100", "8,000", "8,765.55"],  # plan unknown
        ["Imaginary Bluechip Fund Direct Growth", "000111", "50", "5,000", "5,500"],
        ["SBI Small Cap Fund Direct Growth", "19283746", "20.5", "4,000", "4,180.00"],
        ["Total", "", "", "32,000", "39,176.75"],
    ]
    with open(OUT / "groww_mf_messy.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def screener_screen_csv() -> None:
    """Mimics a Screener.in screen export with ownership columns added. Numbers are FAKE."""
    header = ["S.No.", "Name", "NSE Code", "CMP Rs.", "P/E", "Mar Cap Rs.Cr.", "ROCE %",
              "Prom. Hold. %", "Chg in Prom Hold %", "Pledged %", "FII Hold %",
              "Chg in FII Hold %", "DII Hold %", "Chg in DII Hold %", "Debt / Eq",
              "Sales Var 5Yrs %", "Profit Var 5Yrs %"]
    rows = [
        [1, "Reliance Industr", "RELIANCE", 1170.3, 19.6, 1583705, 9.1, 50.1, -0.2, 0.0, 19.2, -1.4, 18.9, 1.6, 0.44, 11.2, 9.8],
        [2, "TCS", "TCS", 3412.4, 24.1, 1234567, 62.5, 71.8, 0.0, 0.6, 12.1, -2.3, 11.0, 2.1, 0.09, 10.4, 9.9],
        [3, "HDFC Bank", "HDFCBANK", 707.3, 15.5, 1090472, 7.4, 0.0, 0.0, 0.0, 47.9, 1.8, 35.2, -1.1, "", 18.7, 17.2],
        [4, "ITC", "", 438.6, 25.3, 548000, 37.9, 0.0, 0.0, 0.0, 40.2, 0.4, 42.3, 0.9, 0.0, 9.1, 11.4],
        [5, "Asian Paints", "ASIANPAINT", 2465.8, 52.0, 236500, 27.1, 52.6, -1.8, 12.4, 13.4, -2.0, 16.1, 1.2, 0.12, 8.0, 6.1],
        [6, "Acme Imaginary Widgets", "", 99.0, 8.0, 1200, 4.0, 60.0, 0.0, 32.0, 1.0, 0.0, 2.0, 0.0, 2.6, -5.0, -12.0],
        ["", "Median: 6 Co.", "", 805.0, 21.8, 392283, 18.0, 51.3, 0.0, 0.3, 16.3, -0.5, 17.5, 1.0, 0.12, 9.6, 9.9],
    ]
    with open(OUT / "screener_screen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([BANNER])
        w.writerow(header)
        w.writerows(rows)


def screener_company_xlsx() -> None:
    """Mimics Screener.in's company "Export to Excel" (Data Sheet tab), 10 years. FAKE numbers."""
    from datetime import date

    wb = Workbook()
    wb.active.title = "Profit & Loss"
    wb.active.append([BANNER])
    ws = wb.create_sheet("Data Sheet")
    years = [date(y, 3, 31) for y in range(2017, 2027)]
    quarters = [date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31),
                date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31),
                date(2026, 6, 30), date(2026, 9, 30)]

    def grow(base: float, rate: float) -> list[float]:
        return [round(base * (1 + rate) ** i, 2) for i in range(len(years))]

    sales = grow(42000, 0.08)
    raw = [round(x * 0.38, 2) for x in sales]
    other_exp = [round(x * 0.26, 2) for x in sales]
    other_inc = [round(x * 0.05, 2) for x in sales]
    dep = [round(x * 0.03, 2) for x in sales]
    interest = [40.0] * len(years)
    pbt = [round(s - r - o + oi - d - i, 2) for s, r, o, oi, d, i in zip(sales, raw, other_exp, other_inc, dep, interest)]
    tax = [round(x * 0.25, 2) for x in pbt]
    np_ = [round(p - t, 2) for p, t in zip(pbt, tax)]
    rows = [
        ["COMPANY NAME", "ITC Ltd"],
        [BANNER],
        ["META"],
        ["Number of shares", 12_500_000_000],
        ["Face Value", 1],
        ["Current Price", 438.6],
        ["Market Capitalization", 548250],
        [],
        ["PROFIT & LOSS"],
        ["Report Date", *years],
        ["Sales", *sales],
        ["Raw Material Cost", *raw],
        ["Change in Inventory", *[0.0] * len(years)],
        ["Power and Fuel", *[0.0] * len(years)],
        ["Other Mfr. Exp", *[0.0] * len(years)],
        ["Employee Cost", *[0.0] * len(years)],
        ["Selling and admin", *[0.0] * len(years)],
        ["Other Expenses", *other_exp],
        ["Other Income", *other_inc],
        ["Depreciation", *dep],
        ["Interest", *interest],
        ["Profit before tax", *pbt],
        ["Tax", *tax],
        ["Net profit", *np_],
        ["Dividend Amount", *[round(x * 0.8, 2) for x in np_]],
        [],
        ["Quarters"],
        ["Report Date", *quarters],
        ["Sales", *[round(13000 * 1.02 ** i, 2) for i in range(len(quarters))]],
        ["Expenses", *[round(8500 * 1.02 ** i, 2) for i in range(len(quarters))]],
        ["Other Income", *[600.0] * len(quarters)],
        ["Depreciation", *[400.0] * len(quarters)],
        ["Interest", *[10.0] * len(quarters)],
        ["Profit before tax", *[round(4690 * 1.02 ** i, 2) for i in range(len(quarters))]],
        ["Tax", *[round(1172 * 1.02 ** i, 2) for i in range(len(quarters))]],
        ["Net profit", *[round(3518 * 1.02 ** i, 2) for i in range(len(quarters))]],
        ["Operating Profit", *[round(4500 * 1.02 ** i, 2) for i in range(len(quarters))]],
        [],
        ["BALANCE SHEET"],
        ["Report Date", *years],
        ["Equity Share Capital", *[1250.0] * len(years)],
        ["Reserves", *grow(55000, 0.07)],
        ["Borrowings", *[300.0] * len(years)],
        ["Other Liabilities", *grow(15000, 0.05)],
        ["Total", *[round(1250 + r + 300 + o, 2) for r, o in zip(grow(55000, 0.07), grow(15000, 0.05))]],
        ["Net Block", *grow(22000, 0.05)],
        ["Capital Work in Progress", *[2500.0] * len(years)],
        ["Investments", *grow(25000, 0.06)],
        ["Other Assets", *grow(21750, 0.08)],
        ["Total", *[round(1250 + r + 300 + o, 2) for r, o in zip(grow(55000, 0.07), grow(15000, 0.05))]],
        ["Receivables", *grow(3000, 0.05)],
        ["Inventory", *grow(10000, 0.05)],
        ["Cash & Bank", *grow(4000, 0.05)],
        ["No. of Equity Shares", *[12_500_000_000] * len(years)],
        ["New Bonus Shares", *[None] * len(years)],
        ["Face value", *[1] * len(years)],
        [],
        ["CASH FLOW:"],
        ["Report Date", *years],
        ["Cash from Operating Activity", *[round(x * 1.1, 2) for x in np_]],
        ["Cash from Investing Activity", *[round(-x * 0.4, 2) for x in np_]],
        ["Cash from Financing Activity", *[round(-x * 0.7, 2) for x in np_]],
        ["Net Cash Flow", *[0.0] * len(years)],
        [],
        ["PRICE:", *[round(200 + 25 * i, 2) for i in range(len(years))]],
        [],
        ["DERIVED:"],
        ["Adjusted Equity Shares in Cr", *[1250.0] * len(years)],
    ]
    for r in rows:
        ws.append(r)
    wb.save(OUT / "screener_company_ITC.xlsx")


if __name__ == "__main__":
    stocks_xlsx()
    stocks_messy_csv()
    stocks_unknown_headers_csv()
    mf_xlsx()
    mf_messy_csv()
    screener_screen_csv()
    screener_company_xlsx()
    print("Wrote fake samples to", OUT)
