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
| Nifty 500 constituents + industry | NSE archives `ind_nifty500list.csv` | Weekly | Sector weights (Phase 7) and the screener universe (Phase 9). |
| Delivery % and traded value | NSE archives `sec_bhavdata_full_DDMMYYYY.csv` (one file per session, all stocks) | With prices | The last 21 sessions are kept (`technical.delivery_lookback_sessions`). The first download takes 2–3 minutes at NSE's rate limit; after that it's one file a day. Days with no file (holidays) are remembered. |

BSE-only stocks are fetched as `SYMBOL.BO`. Yahoo knows BSE stocks by trading symbol, not by the numeric scrip code, and its BSE history can have gaps.

## How refreshing works

- **Incremental.** After the first full download, each refresh re-fetches only the last `incremental_overlap_days` (7) days.
- **Splits and bonuses.** Yahoo rewrites old prices after a split. If the overlapping days no longer match what's stored (by more than `split_check_tolerance`), the whole history is re-downloaded.
- **Skips fresh data.** A refresh only fetches what is stale, so **Refresh now** is cheap. **Force re-download** fetches everything.
- **Rate limits** per source (`data.rate_limits_per_minute`): Yahoo 60, mfapi 60, NSE 10, AMFI 10 requests a minute. Failed requests are retried with exponential backoff, and HTTP 429 slows that source down further.
- **One failure doesn't stop the job.** It is listed under "could not be refreshed", the old data is kept, and the item shows as stale with the error.
- **Reference lists are checked before use.** A download that can't be parsed, or has fewer rows than `data.reference_min_rows`, is rejected and the previous copy stays.
- **Holidays.** No exchange-holiday calendar is bundled. A series counts as fresh if we asked after the day's cut-off and the source is at most `max_missing_sessions` weekdays behind, so holidays don't raise false alarms, but a stock that stops trading does.
- **Restarts.** On startup the app catches up on anything stale (`refresh_on_startup`). A job cut off by a restart is marked "Interrupted".

All of these settings live in the `data:` section of `backend/config/profiles.yaml`.

## API

| Endpoint | |
|---|---|
| `GET /market/status` | Freshness of every holding, benchmark and reference list, plus the last refresh job |
| `POST /market/refresh` `{"scope": "all"\|"reference"\|"prices"\|"navs", "force": false}` | Starts a background refresh and returns the job |
| `GET /jobs/{id}`, `GET /jobs` | Job progress and errors |
| `GET /market/prices/{ticker}?interval=1d\|1wk\|1mo\|15m\|1h&start=YYYY-MM-DD&refresh=false` | Cached bars (fetched on first request). Weekly/monthly bars are built from daily ones; `last_complete=false` means the final bar's week/month isn't over |
| `GET /market/nav/{amfi_code}?start=&refresh=` | NAV history |
| `GET /analysis/technical/{ticker}?style=&timeframes=&fetch=true` | Technical readings for one stock (style defaults to your saved one) |
| `GET /analysis/technical/holdings?style=` | A short summary for every current holding (cached data only) |
| `GET /analysis/technical/{ticker}/series?interval=&start=` | Indicator lines for charts |

## Swapping a data source

Analysis code never calls Yahoo, mfapi or NSE directly. It goes through the `DataProvider` interface in `backend/app/data/provider.py` (daily and intraday bars, NAV history, latest NAV, delivery history). `CachedProvider` is the default: the SQLite cache, filled from the free sources above. To use another source, such as a paid API or a broker's *read-only* data API, write a class with the same methods.
