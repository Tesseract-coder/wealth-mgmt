# Getting your holdings into Portfolio Analyzer

The app never logs in to your broker. You download files yourself and upload them on the **Import** page (http://localhost:5173/import).

> Groww changes its menus from time to time. If a step below doesn't match what you see, look for a **Download** or **Export** option on the holdings screen. The importer is built to cope with renamed columns.

## 1. Stocks: Groww Holdings report

1. Log in at groww.in on a computer (the web app has the download option).
2. Go to **Stocks → Holdings**.
3. Click **Download** (or **Reports → Holdings statement**) and choose **XLSX** (CSV also works).
4. In Portfolio Analyzer: **Import → Stocks (Groww, Kite…)**, then drop the file in and click **Import**.

What the importer does:
- It skips the account details and summary block at the top and finds the real table header on its own.
- It recognises columns such as *Stock Name, ISIN, Quantity, Average buy price, Buy value, Closing price, Closing value, Unrealised P&L*, including common renamings (*Qty., Avg. Cost, LTP, Current Value, P&L*).
- It understands ₹ signs, Indian digit grouping (1,23,456.78) and losses written in brackets, e.g. (1,234).
- It skips "Total" rows, footnotes and zero-quantity rows. The result screen lists every skipped row and the reason.
- If the same stock appears on two rows (for example a pledged lot), it combines them.

### Zerodha Kite (and other brokers)

1. Log in at console.zerodha.com and go to **Portfolio → Holdings**.
2. Click **Download** and choose **XLSX** (CSV also works).
3. Import the same file twice if you want both: **Import → Stocks (Groww, Kite…)** reads the *Equity* sheet, and **Import → Mutual funds (Groww, Kite…)** reads the *Mutual Funds* sheet. The *Combined* sheet is ignored.

Kite files list only the trading symbol (no company name), so the symbol is used as the name. *Quantity Available* is used as the quantity; shares pledged as margin or loan collateral are listed separately by Kite and are not added in.

Other brokers' holdings exports usually import too. When a workbook has several sheets, the app picks the one whose columns best match what you're importing.

### When columns aren't recognised

You'll see a **column-mapping** step showing your file's columns and its first few rows. Pick which column holds each field (* = required). If the header isn't on the row the app guessed, change **Header row** and click **Reload columns**. Leave "Remember this mapping" ticked, and the next file with the same columns imports without asking.

### Matching stocks to NSE symbols

Each row is matched to an NSE symbol in this order:
1. A fix you made earlier
2. **ISIN**, the most reliable
3. A symbol column, if your file has one
4. **Company name**, accepted only when the match is very close and clearly better than the next candidate

Anything still unmatched appears under **Needs your help**, with suggestions and a search box. For a stock that trades only on BSE, enter its BSE trading symbol (e.g. `TCS`, not the numeric scrip code: Yahoo Finance only knows BSE stocks by symbol, and its BSE price data can have gaps). Your fixes are remembered.

### Purchase dates

Groww's holdings report has no purchase dates, so short-term vs long-term capital gains can't be worked out from it. If your file has a *Purchase date* column, it is picked up. (A way to add dates for each holding comes with the holdings page in a later phase.)

## 2. Mutual funds: three options

### a) Groww mutual fund holdings export
1. On groww.in go to **Mutual Funds → Dashboard / Investments**.
2. Use **Download** / **Export holdings** (XLSX or CSV).
3. **Import → Mutual funds (Groww, Kite…)**.

Each fund is matched to its **AMFI scheme code**, which is needed for NAV history. Matching uses the scheme name **plus** the plan (Direct/Regular) and option (Growth/IDCW). If the file doesn't say Direct or Regular, the app won't guess: you pick from suggestions, because the two plans have different NAVs and costs. Funds that have since been renamed (e.g. "HDFC Mid-Cap Opportunities" → "HDFC Mid Cap Fund") show the new name as the top suggestion.

### b) CAS PDF from CAMS / KFintech (recommended for mutual funds)
A Consolidated Account Statement covers **all** your funds across every platform, and a *detailed* CAS includes every transaction. Later phases use those transactions to calculate your own XIRR and holding periods.

1. Request it from CAMS (camsonline.com → *Statements → CAS – CAMS+KFintech*) or KFintech (mfs.kfintech.com).
   Choose **Detailed**, a period starting from your first investment, and set a password.
2. It arrives by email as a password-protected PDF.
3. **Import → CAS PDF**: drop the PDF in, type the password, click **Import CAS**.

The password is used once, in memory, to open the PDF. It is never saved, logged or sent anywhere else. NSDL/CDSL depository CAS files also work for the mutual fund part. Stocks in them are not imported, so use the Groww file for stocks.

### c) Manual entry
**Import → Add fund manually**: enter the AMFI scheme code (exact; find it at amfiindia.com or with the search in the fixer) or a scheme name, plus units and amount invested.

Manual funds are kept when you later re-import from Groww or a CAS, unless the import already contains the same scheme. You can remove a manual fund from the holdings table on the Import page.

## 3. Screener.in data (optional, recommended)

Yahoo Finance gives about 4 years of statements and no ownership data. Screener.in fills both gaps. You need a free Screener.in account. **The app never visits Screener.in; you export the files and upload them** on **Import → Screener.in data**.

### a) A screen's results (ownership + key ratios for many stocks at once)
1. On screener.in, open a screen. A simple way to cover your holdings is a **watchlist** or a screen like `Market Capitalization > 0` filtered to your stocks.
2. **Edit columns** and add: *NSE Code, Promoter holding, Change in promoter holding, Pledged percentage, FII holding, Change in FII holding, DII holding, Change in DII holding* (optionally *Debt to equity, ROCE, Sales growth 5Years, Profit growth 5Years*).
3. Click **Export** and upload the file.

Rows are matched by **NSE Code**, which is why that column is on the list. Without it, matching falls back to the company name, and Screener.in's short names don't always match. Unmatched rows are listed. If the columns aren't recognised, you'll get the same column-mapping step as for Groww files.

### b) A company's Excel export (10 years of results)
1. On a company page, click **Export to Excel**.
2. Upload the .xlsx. The company is matched by name; if that fails, type its NSE symbol in the box and upload again.

With 10 years of results the app can work out 5-year growth, and it uses Screener.in's statements for that company instead of Yahoo's.

Uploads older than 120 days are ignored. Re-export after each quarterly results season.

## 4. Fund portfolio holdings (optional, for fund overlap)

To see how much your funds hold the same stocks, upload each fund's holdings under **Import → Fund portfolios**:
1. Open your fund's AMC website and look for **Monthly portfolio** or **Portfolio disclosure**. Every AMC must publish one each month.
2. Download the Excel file for the latest month. It often has one sheet per scheme: note your fund's sheet name.
3. On the Fund portfolios tab:
   1. Choose the fund.
   2. Enter the portfolio date and the sheet name.
   3. Upload the file.

Columns such as *Name of the Instrument*, *ISIN* and *% to Net Assets* are found automatically. Totals and "Net current assets" rows are skipped, and weights given as fractions (0.052) are converted to percent. Overlap is marked **approximate** if the weights cover less than 90% of the fund, or if the holdings are over 100 days old.

## 5. Snapshots

Every import (and every manual change) is saved as a dated **snapshot**. The latest stock snapshot plus the latest mutual fund snapshot make up your current portfolio. Older snapshots are kept so later phases can chart your portfolio value and signals over time.

## Trying it without your own data

`sample_data/` contains **fake** files that cover each case:

| File | Shows |
|---|---|
| `groww_stocks_holdings.xlsx` | A clean Groww-style report; all 11 rows match by ISIN |
| `groww_stocks_messy.csv` | Renamed columns, ₹ values, a duplicate row, a name-only row, an unknown stock, Total and footnote rows |
| `groww_stocks_unknown_headers.csv` | Unrecognisable columns, which triggers the mapping step |
| `groww_mf_holdings.xlsx` | A clean Groww-style MF export; all 5 funds match |
| `groww_mf_messy.csv` | A renamed fund, a fund without plan info, an unknown fund |
| `screener_screen.csv` | A Screener.in-style screen with ownership columns, a "Median" row, and an unknown company |
| `screener_company_ITC.xlsx` | A Screener.in-style company export ("Data Sheet" tab) with 10 years of made-up results |

Regenerate them with `cd backend && uv run python ../sample_data/generate_samples.py`.

## Reference data

Matching uses the NSE equity and ETF lists and AMFI's `NAVAll.txt`. The app re-downloads them automatically (NSE lists weekly, the AMFI list daily) into `backend/var/reference/`; the copies bundled in `backend/data/fallback/` are only used until the first successful download, or if the sites are unreachable. See [DATA_SOURCES.md](DATA_SOURCES.md).
