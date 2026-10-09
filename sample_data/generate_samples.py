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


if __name__ == "__main__":
    stocks_xlsx()
    stocks_messy_csv()
    stocks_unknown_headers_csv()
    mf_xlsx()
    mf_messy_csv()
    print("Wrote fake samples to", OUT)
