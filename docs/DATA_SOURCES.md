# Market data sources

All sources are free and public. The app never logs in anywhere. Every number on screen carries an **as-of date** and a status:

| Status | Meaning |
|---|---|
| **Fresh** | Refreshed recently, and the source has the latest session we expect. |
| **Stale** | Old, or a refresh failed, or the source itself has stopped updating (e.g. a suspended stock). The reason is shown. The last good data is kept and still shown with its date. |
| **Unavailable** | No data at all. The app shows "—"; it never fills in a number. |

## Sources

| Data | Source | Refresh | Notes |
|---|---|---|---|
| Daily OHLCV for stocks, ETFs, indices | Yahoo Finance via `yfinance` | Mon–Fri 16:00 IST | Unofficial and delayed. A day's bar is stored only after `refresh_time_ist`, so a half-finished session never ends up in the history. 5 years kept (`price_history_years`). |
| Intraday bars (15m / 1h) | Yahoo Finance | On demand, cached 15 min | For the intraday style only. Yahoo keeps ~60 days of 15m and ~730 days of 1h bars. |
| Benchmarks | Yahoo: `^NSEI` (Nifty 50), `^CRSLDX` (Nifty 500) | With prices | Change in `data.benchmarks`. |
| MF NAV history | [mfapi.in](https://www.mfapi.in/) | Daily 23:30 IST | Full history per scheme. |
| Latest NAVs + scheme list | AMFI `NAVAll.txt` | Daily 23:30 IST | Also used to match fund names to scheme codes. If it has a newer NAV than mfapi, the newer one is used. |
| Equity + ETF symbol lists | NSE archives `EQUITY_L.csv`, `eq_etfseclist.csv` | Weekly | Used to match ISINs / names to symbols. |
| BSE equity list | BSE's daily equity bhavcopy (`BhavCopy_BSE_CM_…_YYYYMMDD_F_0000.CSV`): code, symbol, name, ISIN and group of every share traded that day | Daily, with prices | BSE's scrip-list API refuses scripted downloads, so each refresh merges the latest bhavcopy into the stored list; a share unseen for 30 days drops out. Debt, government securities, gold bonds, REITs/InvITs, ETFs and rights entitlements are left out. Shares also on NSE are used through NSE; the rest become `SYMBOL.BO`. A bundled copy (22 sessions) is used until a download succeeds. |
| Nifty 50/100/200/500 constituents + industry | NSE archives `ind_nifty50list.csv` … `ind_nifty500list.csv` | Weekly | Sector weights (the Nifty 500 list's industry) and the screener universes. Bundled copies are used until a download succeeds. |
| Fundamentals (statements, shares, sector) | Yahoo Finance via `yfinance` (`.info`, annual income/balance/cash flow, quarterly income) | Weekly (Sat 10:00 IST), with peers | About 5 requests per stock. Cached for `fundamentals_stale_after_days` (7). Holdings are also refreshed in the daily job when stale. **Refresh fundamentals + peers** fetches holdings plus up to 40 Nifty 500 peers per industry you hold, for sector medians; the first run takes 10–30 minutes. |
| Your holdings and the analysis tabs | **Your Google Sheet**: Sheets API v4 with your service account, or a tab you published as CSV | When you import or export (optionally after the daily refresh) | 50 requests a minute (`rate_limits_per_minute.google`; Google allows 60). An export uses about 7. Only `docs.google.com` links are accepted. See [GOOGLE_SHEETS_SETUP.md](GOOGLE_SHEETS_SETUP.md). |
| Ownership, 10-year statements | **Your Screener.in exports** (uploaded, never scraped) | When you upload | See the import guide. |
| Delivery % and traded value | NSE archives `sec_bhavdata_full_DDMMYYYY.csv` (one file per session, all stocks) | With prices | The last 21 sessions are kept (`technical.delivery_lookback_sessions`). The first download takes 2–3 minutes at NSE's rate limit; after that it's one file a day. Days with no file (holidays) are remembered. |

BSE-only stocks are fetched as `SYMBOL.BO`. Yahoo knows BSE stocks by trading symbol, not by the numeric scrip code, and its BSE history can have gaps. Small companies are often missing figures at Yahoo; their page says **Limited data** when two or more sections can't be scored.

**Loading the whole market.** Nothing is downloaded for a stock until you need it: opening it, a scan that covers it, or the **nightly top-up**, which each weeknight at `data.topup_time_ist` (22:30) downloads prices and fundamentals for the next `data.topup_per_night` (200) stocks not loaded yet: Nifty 50 first, then the bigger Nifty indices, other NSE stocks, and BSE-only ones last. At Yahoo's 60 requests a minute that is about 25 minutes a night; set it to 0 to turn it off. A stock whose download fails is left alone for a week. Opening a page doesn't retry a download that failed in the last `data.failed_retry_after_minutes` (60); jobs and **Refresh now** always do.

## How refreshing works

- **Incremental.** After the first full download, each refresh re-fetches only the last `incremental_overlap_days` (7) days.
- **Splits and bonuses.** Yahoo rewrites old prices after a split. If the overlapping days no longer match what's stored (by more than `split_check_tolerance`), the whole history is re-downloaded.
- **Skips fresh data.** A refresh only fetches what is stale, so **Refresh now** is cheap. **Force re-download** fetches everything.
- **Rate limits** per source (`data.rate_limits_per_minute`): Yahoo 60, mfapi 60, NSE 10, BSE 10, AMFI 10 requests a minute. Failed requests are retried with exponential backoff, and HTTP 429 slows that source down further.
- **One failure doesn't stop the job.** It is listed under "could not be refreshed", the old data is kept, and the item shows as stale with the error.
- **Reference lists are checked before use.** A download that can't be parsed, or has fewer rows than `data.reference_min_rows`, is rejected and the previous copy stays.
- **Holidays.** No exchange-holiday calendar is bundled. A series counts as fresh if we asked after the day's cut-off and the source is at most `max_missing_sessions` weekdays behind, so holidays don't raise false alarms, but a stock that stops trading does.
- **Restarts.** On startup the app catches up on anything stale (`refresh_on_startup`). A job cut off by a restart is marked "Interrupted".

All of these settings live in the `data:` section of `backend/config/profiles.yaml`.

## API

| Endpoint | |
|---|---|
| `GET /market/status` | Freshness of every holding, benchmark and reference list, plus the last refresh job |
| `POST /market/refresh` `{"scope": "all"\|"reference"\|"prices"\|"navs"\|"fundamentals", "force": false}` | Starts a background refresh and returns the job |
| `GET /jobs/{id}`, `GET /jobs` | Job progress and errors |
| `GET /market/prices/{ticker}?interval=1d\|1wk\|1mo\|15m\|1h&start=YYYY-MM-DD&refresh=false` | Cached bars (fetched on first request). Weekly/monthly bars are built from daily ones; `last_complete=false` means the final bar's week/month isn't over |
| `GET /market/nav/{amfi_code}?start=&refresh=` | NAV history |
| `GET /analysis/technical/{ticker}?style=&timeframes=&fetch=true` | Technical readings for one stock (style defaults to your saved one) |
| `GET /analysis/technical/holdings?style=` | A short summary for every current holding (cached data only) |
| `GET /analysis/technical/{ticker}/series?interval=&start=` | Indicator lines for charts |
| `GET /analysis/fundamental/{ticker}?fetch=true` | Fundamental metrics, F-score and readings |
| `GET /analysis/fundamental/holdings` | A short fundamentals summary per holding (cached data only) |
| `GET /analysis/stock/{ticker}?style=&risk=&fetch=true` | Signal, scores, reasons, flags, stop-loss/targets, position size and tax note for one stock |
| `GET /analysis/signals/holdings?style=&risk=` | Signals for every holding plus sector weights (cached data only; saved to the history) |
| `GET /analysis/stock/{ticker}/history?style=` | Past daily signals |
| `POST /import/screener` (file, optional `mapping`, optional `symbol`) | Upload a Screener.in screen or company export |
| `GET /analysis/mf/{amfi_code}?fetch=true` | One fund: your XIRR, 1/3/5-year CAGR vs benchmark, rolling returns, risk, Regular vs Direct, cost, overlap, signal |
| `GET /analysis/mf/holdings` | Every fund you hold with its signal, plus the overlap matrix (cached data only) |
| `PUT /analysis/mf/{amfi_code}/expense-ratio` `{"expense_ratio_pct": 0.65}` | Save a fund's TER from its factsheet |
| `POST /import/fund-portfolio` (file, `amfi_code`, optional `as_of`, `sheet`, `mapping`) | A fund's holdings from the AMC's monthly portfolio file, for overlap |
| `GET /portfolio/summary` | Value, P&L, day change, XIRR, allocation, concentration, beta, correlation, performance vs Nifty 50 |
| `GET /portfolio/actions` | The Overview's "Action needed" list: signals, red flags and fund switches, most severe first |
| `GET /analysis/mf/{code}/chart` | NAV vs benchmark (growth of 100) and rolling-return series, from cache |
| `GET /market/prices/{ticker}`, `GET /analysis/technical/{ticker}/series` | Candles and indicator lines for the stock chart |
| `GET/PUT/DELETE /settings/thresholds` | Thresholds editable in Settings (saved to `backend/var/profiles.local.yaml`) |
| `GET /export/stocks.csv`, `GET /export/funds.csv` | Signals as CSV, ending with the date and the disclaimer |
| `GET /screener/config` | Universes, presets, filter fields, your saved screens and the latest scan |
| `POST /screener/run` `{"universe": "nifty500"\|…\|"custom", "symbols": "TCS, INFY", "fetch": "missing"\|"cached", "style", "risk"}` | Starts a scan as a background job; returns the job |
| `GET /screener/jobs/{id}`, `GET /screener/active`, `POST /jobs/{id}/cancel` | Scan progress, the running scan, stop a job (finished work is kept) |
| `POST /screener/screen` `{"preset"\|"screen_id"\|"filters", "include_held", "scan_id", "top_n"}` | Ranked ideas from a stored scan (instant, no downloads) |
| `GET /screener/scans`, `GET /screener/scans/{id}/stocks?status=` | Stored scans; every stock in one with why it was or wasn't scored |
| `GET/POST /screener/screens`, `PUT/DELETE /screener/screens/{id}` | Your saved screens |
| `GET /export/screener.csv?preset=&screen_id=&include_held=` | A screen's ideas as CSV |
| `GET/POST /watchlist`, `GET /watchlist/tickers`, `PATCH/DELETE /watchlist/{ticker}` | The watchlist, scored live from the cache |
| `GET /sheets/status`, `PUT /sheets/settings` | Google Sheets setup (the key's e-mail only, never the private key) and recent syncs |
| `POST /sheets/service-account` (file) | Store a service-account key in `secrets/` (mode 600) |
| `POST /sheets/test` | Connection test, step by step; changes nothing |
| `POST /sheets/export` `{"overwrite": []}` | Write the four export tabs; 409 lists same-named tabs the app didn't write |
| `POST /sheets/import` `{"kind": "stocks"\|"mf", "source": "tab"\|"csv", "tab", "url", "mapping"}` | Holdings from a tab or a published CSV link (same importer as a file) |

## Mutual fund benchmarks

Each fund is compared with the Yahoo index for its category (`mf.benchmarks`). For example:
- large cap → Nifty 50 (`^NSEI`);
- mid cap → Nifty Midcap 150 (`NIFTYMIDCAP150.NS`);
- small cap → Nifty Smallcap 250 (`NIFTYSMLCAP250.NS`);
- flexi/multi cap, ELSS and focused → Nifty 500 (`^CRSLDX`).

Index funds are matched by name. Debt funds get no benchmark, because no free source carries debt indices.

These are **price** indices: Yahoo has no total-return indices, so dividends are left out and funds look about 1–1.5% a year better than in their factsheets. The daily refresh also keeps these benchmarks fresh, along with the Direct plan of any Regular fund you hold (to measure the cost gap).

**Not available free:** expense ratios (TER), which you can type in from the factsheet, and fund portfolio holdings, which you upload from the AMC's monthly portfolio file.

## Swapping a data source

Analysis code never calls Yahoo, mfapi or NSE directly. It goes through the `DataProvider` interface in `backend/app/data/provider.py` (daily and intraday bars, NAV history, latest NAV, delivery history). `CachedProvider` is the default: the SQLite cache, filled from the free sources above. To use another source, such as a paid API or a broker's *read-only* data API, write a class with the same methods.
