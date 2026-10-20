from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import db, profiles
from app.core.formatting import IST
from app.core.memo import clear_memos
from app.core.settings import get_settings
from app.data import http, rate_limit
from app.data.reference_refresh import clear_reference_caches
from app.jobs import runner


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Tests never sleep for rate limits or backoff, never reach the network, and never read
    thresholds you edited in Settings."""
    monkeypatch.setenv("PROFILES_OVERRIDE_PATH", str(tmp_path / "profiles.local.yaml"))
    get_settings.cache_clear()
    profiles._profiles = None
    rate_limit.reset_limiters()
    for source in ("yahoo", "mfapi", "nse", "bse", "amfi", "google"):
        rate_limit._limiters[source] = rate_limit.RateLimiter(1e9, sleep=lambda _: None)
    monkeypatch.setattr("app.data.http.time.sleep", lambda _: None)

    def offline(*_: object, **__: object) -> pd.DataFrame:
        raise ConnectionError("test tried to call Yahoo Finance; patch app.data.yahoo")

    monkeypatch.setattr("app.data.yahoo._download", offline)
    monkeypatch.setattr("app.data.yahoo._fund_download", offline)

    def no_network(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"network disabled in tests ({req.url})")

    http.set_client(httpx.Client(transport=httpx.MockTransport(no_network)))
    yield
    rate_limit.reset_limiters()
    http.set_client(None)


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REFERENCE_DATA_DIR", str(tmp_path / "reference"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("PROFILES_OVERRIDE_PATH", str(tmp_path / "profiles.local.yaml"))
    get_settings.cache_clear()
    db._engine = None
    profiles._profiles = None
    clear_reference_caches()
    clear_memos()


def _teardown() -> None:
    runner.reset_runner()
    db._engine = None
    get_settings.cache_clear()
    clear_reference_caches()
    clear_memos()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App wired to a throwaway SQLite file and reference dir."""
    _isolate(tmp_path, monkeypatch)
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    _teardown()


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    _isolate(tmp_path, monkeypatch)
    db.init_db()
    with Session(db.get_engine()) as s:
        yield s
    _teardown()


# A Friday evening, after the 16:00 IST price cut-off and before the 23:30 NAV cut-off.
FRI_EVENING = datetime(2026, 10, 9, 17, 0, tzinfo=IST)


def yf_frame(start: date, end: date, base: float = 100.0, factor: float = 1.0) -> pd.DataFrame:
    """A yfinance-shaped daily frame for weekdays in [start, end]: tz-aware midnight IST index."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() < 5]
    closes = [(base + (d - date(2020, 1, 1)).days * 0.1) * factor for d in days]
    idx = pd.DatetimeIndex([pd.Timestamp(d).tz_localize("Asia/Kolkata") for d in days])
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Adj Close": [c * 0.98 for c in closes],
            "Volume": [1000.0] * len(days),
        },
        index=idx,
    )
