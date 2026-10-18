"""Yahoo Finance via yfinance: daily and intraday OHLCV, normalised and rate-limited.

Yahoo data is free, unofficial and delayed. Every call is paced by the "yahoo" rate limiter and
retried with backoff; an empty answer is an error, never an empty-but-valid series.
"""

import logging
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from app.core.profiles import get_profiles
from app.data.http import FetchError
from app.data.rate_limit import limiter

logger = logging.getLogger(__name__)
# yfinance logs "possibly delisted" noise for every miss; failures are reported via FetchError.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def yahoo_ticker(symbol: str, exchange: str | None) -> str:
    """NSE symbol → 'SYMBOL.NS'; BSE symbol → 'SYMBOL.BO'.

    Yahoo keys BSE listings by trading symbol (TCS.BO); numeric scrip codes (532540.BO) return
    nothing."""
    return f"{symbol}.BO" if exchange == "BSE" else f"{symbol}.NS"


def _download(
    ticker: str, *, interval: str, start: date | None = None, period: str | None = None
) -> pd.DataFrame:
    """The raw yfinance call. Isolated so tests can replace it."""
    t = yf.Ticker(ticker)
    if period:
        return t.history(period=period, interval=interval, auto_adjust=False, actions=False)
    end = date.today() + timedelta(days=2)  # end is exclusive; allow for timezone skew
    return t.history(start=start, end=end, interval=interval, auto_adjust=False, actions=False)


def _call(
    ticker: str, *, interval: str, start: date | None = None, period: str | None = None
) -> pd.DataFrame:
    cfg = get_profiles().data
    last = ""
    for attempt in range(cfg.http_retries + 1):
        limiter("yahoo").acquire()
        try:
            df = _download(ticker, interval=interval, start=start, period=period)
        except Exception as e:  # yfinance raises a zoo of exception types
            last = f"{e.__class__.__name__}: {e}"[:200]
            if "RateLimit" in e.__class__.__name__:
                limiter("yahoo").penalise(cfg.http_backoff_seconds * 2 ** (attempt + 2))
        else:
            if df is not None and not df.empty:
                return df
            # Empty means "no such symbol / no data in range"; retrying won't help.
            raise FetchError(
                f"Yahoo Finance has no {interval} data for {ticker} "
                "(the symbol may be wrong, renamed or delisted)"
            )
        if attempt < cfg.http_retries:
            time.sleep(cfg.http_backoff_seconds * 2**attempt)
    raise FetchError(f"Yahoo Finance request for {ticker} failed ({last})")


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):  # yf.download-style frames
        df = df.droplevel(1, axis=1)
    renamed = df.rename(columns=_COLUMNS)
    out = renamed[[c for c in _COLUMNS.values() if c in renamed.columns]]
    if "close" not in out.columns:
        raise FetchError("Yahoo Finance returned data without a Close column")
    out = out.apply(pd.to_numeric, errors="coerce")
    return out[out["close"].notna() & (out["close"] > 0)]


def fetch_daily(ticker: str, start: date) -> pd.DataFrame:
    """Daily bars from `start`, indexed by exchange-local session date."""
    df = _normalise(_call(ticker, interval="1d", start=start))
    idx = pd.DatetimeIndex(df.index)
    # Daily bars are stamped 00:00 exchange time: take the local date (UTC is a day early).
    df.index = pd.Index([ts.date() for ts in idx], name="date")
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_intraday(ticker: str, interval: str, days: int) -> pd.DataFrame:
    """Intraday bars for the last `days` days, indexed by bar-start time in UTC."""
    df = _normalise(_call(ticker, interval=interval, period=f"{days}d"))
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert("UTC").rename("ts")
    return df[~df.index.duplicated(keep="last")].sort_index()


INFO_KEYS = (
    "longName",
    "sector",
    "industry",
    "marketCap",
    "sharesOutstanding",
    "currentPrice",
    "trailingPE",
    "priceToBook",
    "enterpriseToEbitda",
    "dividendYield",
    "beta",
    "heldPercentInsiders",
    "heldPercentInstitutions",
    "financialCurrency",
    "currency",
)
STATEMENTS = {
    "income": "income_stmt",
    "balance": "balance_sheet",
    "cashflow": "cashflow",
    "quarterly_income": "quarterly_income_stmt",
}


def _fund_download(ticker: str, what: str) -> Any:
    """One raw yfinance fundamentals call ("info" or a Ticker statement attribute)."""
    t = yf.Ticker(ticker)
    return t.info if what == "info" else getattr(t, what)


ESTIMATES = "earnings_estimate"


def _eps_estimates(df: pd.DataFrame | None) -> dict[str, float] | None:
    """Analyst EPS consensus: last full year's EPS ("base"), this year ("fy0") and next ("fy1")."""
    if df is None or df.empty or "avg" not in df.columns:
        return None

    def cell(col: str, row: str) -> float | None:
        if col not in df.columns or row not in df.index:
            return None
        v = df.at[row, col]
        return None if v is None or pd.isna(v) else float(v)

    out = {
        "base": cell("yearAgoEps", "0y"),
        "fy0": cell("avg", "0y"),
        "fy1": cell("avg", "+1y"),
        "analysts": cell("numberOfAnalysts", "+1y") or cell("numberOfAnalysts", "0y"),
    }
    clean = {k: v for k, v in out.items() if v is not None}
    return clean if "base" in clean and ("fy0" in clean or "fy1" in clean) else None


def _frame_json(df: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    if df is None or df.empty:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row, series in df.iterrows():
        vals = {
            pd.Timestamp(col).date().isoformat(): float(v)
            for col, v in series.items()
            if v is not None and not pd.isna(v)
        }
        if vals:
            out[str(row)] = vals
    return out


def fetch_fundamentals(ticker: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(info subset, statements) for a ticker. Each call is rate-limited and retried.

    A statement Yahoo doesn't have comes back empty; only a total failure raises."""
    cfg = get_profiles().data
    results: dict[str, Any] = {}
    errors: list[str] = []
    for what in ("info", *STATEMENTS.values(), ESTIMATES):
        for attempt in range(cfg.http_retries + 1):
            limiter("yahoo").acquire()
            try:
                results[what] = _fund_download(ticker, what)
                break
            except Exception as e:
                msg = f"{e.__class__.__name__}: {e}"[:160]
                if "RateLimit" in e.__class__.__name__:
                    limiter("yahoo").penalise(cfg.http_backoff_seconds * 2 ** (attempt + 2))
                if attempt == cfg.http_retries:
                    errors.append(f"{what}: {msg}")
                else:
                    time.sleep(cfg.http_backoff_seconds * 2**attempt)
    info_raw = results.get("info") or {}
    info = {k: info_raw.get(k) for k in INFO_KEYS if info_raw.get(k) is not None}
    statements = {key: _frame_json(results.get(attr)) for key, attr in STATEMENTS.items()}
    # Always present after a fetch (None = no analyst cover), so a cache without it is refetched.
    info["eps_estimates"] = _eps_estimates(results.get(ESTIMATES))
    if not any(v is not None for v in info.values()) and not any(statements.values()):
        detail = "; ".join(errors) if errors else "nothing returned"
        raise FetchError(f"Yahoo Finance has no fundamentals for {ticker} ({detail})")
    return info, statements
