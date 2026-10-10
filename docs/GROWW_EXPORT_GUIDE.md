# Getting your holdings into Portfolio Analyzer

The app never logs in to Groww. You download files yourself and upload them on the **Import** page (http://localhost:5173/import).

> Groww changes its menus from time to time. If a step below doesn't match what you see, look for a **Download** or **Export** option on the holdings screen. The importer is built to cope with renamed columns.

## 1. Stocks: Groww Holdings report

1. Log in at groww.in on a computer (the web app has the download option).
2. Go to **Stocks → Holdings**.
3. Click **Download** (or **Reports → Holdings statement**) and choose **XLSX** (CSV also works).
4. In Portfolio Analyzer: **Import → Groww stocks**, then drop the file in and click **Import**.

What the importer does:
- It skips the account details and summary block at the top and finds the real table header on its own.
- It recognises columns such as *Stock Name, ISIN, Quantity, Average buy price, Buy value, Closing price, Closing value, Unrealised P&L*, including common renamings (*Qty., Avg. Cost, LTP, Current Value, P&L*).
- It understands ₹ signs, Indian digit grouping (1,23,456.78) and losses written in brackets, e.g. (1,234).
- It skips "Total" rows, footnotes and zero-quantity rows. The result screen lists every skipped row and the reason.
- If the same stock appears on two rows (for example a pledged lot), it combines them.

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
3. **Import → Groww mutual funds**.

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

## 3. Snapshots

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

Regenerate them with `cd backend && uv run python ../sample_data/generate_samples.py`.

## Reference data

Matching uses the NSE equity and ETF lists and AMFI's `NAVAll.txt`. The app re-downloads them automatically (NSE lists weekly, the AMFI list daily) into `backend/var/reference/`; the copies bundled in `backend/data/fallback/` are only used until the first successful download, or if the sites are unreachable. See [DATA_SOURCES.md](DATA_SOURCES.md).
