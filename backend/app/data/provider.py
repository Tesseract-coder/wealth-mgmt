"""The one interface the analysis code uses for market data.

Analysis modules depend on `DataProvider`, never on yfinance/mfapi/NSE directly, so a source can
be swapped (a paid API, a broker's read-only API) by writing another implementation.
`CachedProvider` serves the SQLite cache and fetches through the free sources when a series
is missing or stale.
"""

from datetime import date
from typing import Protocol

import pandas as pd
from sqlmodel import Session

from app.core.formatting import now_ist
from app.data import delivery, fundamentals, navs, prices, store
from app.data.freshness import Freshness
from app.data.fundamentals import RawFundamentals
from app.data.navs import LatestNav
from app.data.prices import Bars, DailyInterval, IntradayInterval
from app.data.store import RefreshResult


class DataProvider(Protocol):
    def daily(
        self, ticker: str, interval: DailyInterval = "1d", start: date | None = None
    ) -> Bars: ...

    def intraday(self, ticker: str, interval: IntradayInterval) -> Bars: ...

    def ensure_daily(
        self, ticker: str, label: str | None = None, force: bool = False
    ) -> RefreshResult: ...

    def ensure_intraday(
        self, ticker: str, interval: IntradayInterval, force: bool = False
    ) -> RefreshResult: ...

    def nav_history(self, code: str, start: date | None = None) -> pd.Series: ...

    def latest_nav(self, code: str) -> LatestNav: ...

    def ensure_nav(
        self, code: str, label: str | None = None, force: bool = False
    ) -> RefreshResult: ...

    def delivery(self, symbol: str, sessions: int) -> pd.DataFrame: ...

    def fundamentals(self, ticker: str) -> RawFundamentals | None: ...

    def fundamentals_freshness(self, ticker: str) -> Freshness: ...

    def ensure_fundamentals(
        self, ticker: str, label: str | None = None, force: bool = False
    ) -> RefreshResult: ...


class CachedProvider:
    """SQLite cache backed by Yahoo Finance, mfapi.in, AMFI and NSE archives."""

    def __init__(self, session: Session) -> None:
        self.session = session
        # Daily bars already read through this provider (one per request or job step). Analysing
        # one stock reads its history about five times and the Nifty 50's twice; across every
        # holding that was hundreds of identical reads. Cleared when a refresh may change them.
        self._daily: dict[tuple[str, DailyInterval, date | None], Bars] = {}

    def daily(self, ticker: str, interval: DailyInterval = "1d", start: date | None = None) -> Bars:
        key = (ticker, interval, start)
        bars = self._daily.pop(key, None) or prices.get_daily(self.session, ticker, interval, start)
        self._daily[key] = bars  # most recently used last
        if len(self._daily) > 32:  # a screener scan walks hundreds of stocks: keep only recent ones
            del self._daily[next(iter(self._daily))]
        return bars

    def _forget_daily(self, ticker: str) -> None:
        for key in [k for k in self._daily if k[0] == ticker]:
            del self._daily[key]

    def intraday(self, ticker: str, interval: IntradayInterval) -> Bars:
        return prices.get_intraday(self.session, ticker, interval)

    def ensure_daily(
        self, ticker: str, label: str | None = None, force: bool = False
    ) -> RefreshResult:
        """Fetch only when nothing is cached or the cache is stale (or force)."""
        self._forget_daily(ticker)
        return prices.refresh_daily(self.session, ticker, label, force=force)

    def ensure_intraday(
        self, ticker: str, interval: IntradayInterval, force: bool = False
    ) -> RefreshResult:
        return prices.refresh_intraday(self.session, ticker, interval, force=force)

    def nav_history(self, code: str, start: date | None = None) -> pd.Series:
        pts = store.read_navs(self.session, code, start)
        return pd.Series(
            [p.nav for p in pts], index=pd.Index([p.date for p in pts], name="date"), name=code
        )

    def latest_nav(self, code: str) -> LatestNav:
        return navs.latest_nav(self.session, code)

    def ensure_nav(self, code: str, label: str | None = None, force: bool = False) -> RefreshResult:
        return navs.refresh_nav(self.session, code, label or code, force=force)

    def delivery(self, symbol: str, sessions: int) -> pd.DataFrame:
        return delivery.delivery_history(self.session, symbol, sessions)

    def fundamentals(self, ticker: str) -> RawFundamentals | None:
        return fundamentals.load_raw(self.session, ticker)

    def fundamentals_freshness(self, ticker: str) -> Freshness:
        st = store.get_status(self.session, fundamentals.fund_key(ticker))
        return fundamentals.fundamentals_freshness(st, now_ist())

    def ensure_fundamentals(
        self, ticker: str, label: str | None = None, force: bool = False
    ) -> RefreshResult:
        return fundamentals.refresh_fundamentals(self.session, ticker, label, force=force)
