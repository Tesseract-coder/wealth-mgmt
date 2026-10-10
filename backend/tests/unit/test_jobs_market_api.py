import json
import threading
from datetime import date

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.data import http, yahoo
from app.jobs.runner import JobRunner, Progress, get_runner, mark_interrupted
from app.models.tables import Job
from tests.conftest import yf_frame

SAMPLES = "../sample_data"


def test_runner_records_progress_errors_and_result(session: Session) -> None:
    runner = JobRunner()

    def fn(p: Progress) -> str:
        p.update(1, 2, "half")
        p.error("item failed")
        return "all done"

    job = runner.submit("t", fn)
    assert job.id is not None
    runner.wait(job.id, timeout=5)
    session.expire_all()
    j = session.get(Job, job.id)
    assert j and j.status == "done" and j.message == "all done" and j.done == 1 and j.total == 2
    assert json.loads(j.errors or "[]") == ["item failed"]
    runner.shutdown()


def test_runner_dedupes_and_records_failures(session: Session) -> None:
    runner = JobRunner()
    gate = threading.Event()

    def slow(p: Progress) -> str:
        gate.wait(5)
        raise ValueError("kaboom")

    first = runner.submit("k", slow)
    second = runner.submit("k", lambda p: "never")
    assert first.id == second.id
    gate.set()
    runner.wait(first.id, timeout=5)  # type: ignore[arg-type]
    session.expire_all()
    j = session.get(Job, first.id)
    assert j and j.status == "failed" and "kaboom" in (j.message or "")
    runner.shutdown()


def test_mark_interrupted(session: Session) -> None:
    session.add(Job(kind="x", status="running"))
    session.commit()
    assert mark_interrupted() == 1
    session.expire_all()
    j = session.exec(select(Job)).one()
    assert j.status == "failed" and "Interrupted" in (j.message or "")


def _serve_mfapi() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        code = req.url.path.rsplit("/", 1)[-1]
        if code == "404404":
            return httpx.Response(200, content=b'{"status": "FAIL", "data": []}')
        body = {
            "meta": {"scheme_code": int(code), "scheme_name": f"Fund {code}"},
            "status": "SUCCESS",
            "data": [{"date": "09-10-2026", "nav": "50.5"}, {"date": "08-10-2026", "nav": "50.0"}],
        }
        return httpx.Response(200, content=json.dumps(body))

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))


def _fake_yahoo(monkeypatch: pytest.MonkeyPatch, missing: set[str] = frozenset()) -> list[str]:  # type: ignore[assignment]
    asked: list[str] = []

    def dl(
        ticker: str, *, interval: str, start: date | None = None, period: str | None = None
    ) -> pd.DataFrame:
        asked.append(ticker)
        if ticker in missing:
            return pd.DataFrame()
        return yf_frame(start or date(2026, 9, 1), date.today())

    monkeypatch.setattr(yahoo, "_download", dl)
    return asked


def test_market_status_empty_portfolio(client: TestClient) -> None:
    r = client.get("/market/status")
    assert r.status_code == 200
    body = r.json()
    assert {q["code"] for q in body["quotes"]} == {"^NSEI", "^CRSLDX"}
    assert all(
        q["freshness"]["status"] == "unavailable" and q["price"] is None for q in body["quotes"]
    )
    refs = {x["key"]: x for x in body["references"]}
    lists = ("nse_equity", "nse_etf", "nifty50", "nifty100", "nifty200", "nifty500", "amfi_navall")
    assert set(refs) == {*lists, "nse_delivery"}
    assert all(refs[k]["origin"] == "bundled" for k in lists)
    assert refs["nse_delivery"]["freshness"]["status"] == "unavailable"
    assert body["schedule"]["enabled"] is False and body["last_job"] is None


def test_refresh_job_covers_holdings_and_reports_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with open(f"{SAMPLES}/groww_stocks_holdings.xlsx", "rb") as f:
        assert client.post("/import/groww-stocks", files={"file": f}).json()["status"] == "imported"
    with open(f"{SAMPLES}/groww_mf_holdings.xlsx", "rb") as f:
        assert client.post("/import/groww-mf", files={"file": f}).json()["status"] == "imported"
    asked = _fake_yahoo(monkeypatch, missing={"ITC.NS"})
    _serve_mfapi()

    r = client.post("/market/refresh", json={"scope": "all"})
    assert r.status_code == 202
    job_id = r.json()["id"]
    get_runner().wait(job_id, timeout=30)
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done"
    # 2 benchmarks + 11 stocks + the small-cap fund's benchmark via Yahoo (the other funds'
    # benchmarks are Nifty 50/500, already fetched); reference lists fail (no NSE/AMFI mock)
    assert "^NSEI" in asked and "RELIANCE.NS" in asked and "NIFTYSMLCAP250.NS" in asked
    assert len(asked) == 14
    assert any("ITC" in e for e in job["errors"])
    assert job["message"].endswith("failed") and job["done"] == job["total"]

    status = client.get("/market/status").json()
    quotes = {q["code"]: q for q in status["quotes"]}
    assert quotes["ITC.NS"]["freshness"]["status"] == "unavailable"  # never invented
    assert quotes["ITC.NS"]["price"] is None
    funds = [q for q in status["quotes"] if q["kind"] == "mf"]
    assert len(funds) == 5 and all(q["price"] == 50.5 for q in funds)
    assert status["last_job"]["id"] == job_id
    assert client.get("/jobs").json()[0]["id"] == job_id


def test_prices_endpoint_fetches_on_first_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _fake_yahoo(monkeypatch)
    r = client.get("/market/prices/abc.ns", params={"start": "2026-09-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "ABC.NS" and body["delayed"] is True and body["fetch_error"] is None
    assert body["bars"][0]["t"] >= "2026-09-01" and body["bars"][-1]["close"] > 0
    client.get("/market/prices/ABC.NS")  # cached now
    assert asked == ["ABC.NS"]
    wk = client.get(
        "/market/prices/ABC.NS", params={"interval": "1wk", "start": "2026-09-01"}
    ).json()
    assert len(wk["bars"]) < len(body["bars"])


def test_prices_endpoint_reports_unknown_ticker(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_yahoo(monkeypatch, missing={"NOPE.NS"})
    body = client.get("/market/prices/NOPE.NS").json()
    assert body["bars"] == [] and body["freshness"]["status"] == "unavailable"
    assert "no 1d data" in body["fetch_error"]


def test_prices_endpoint_validates_input(client: TestClient) -> None:
    assert client.get("/market/prices/bad ticker!").status_code == 422
    assert client.get("/market/prices/ABC.NS", params={"interval": "5m"}).status_code == 422


def test_intraday_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = pd.DatetimeIndex(["2026-10-09 09:15", "2026-10-09 09:30"]).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {
            "Open": [1.0, 2],
            "High": [1.0, 2],
            "Low": [1.0, 2],
            "Close": [1.5, 2.5],
            "Volume": [1.0, 2],
        },
        index=idx,
    )
    monkeypatch.setattr(yahoo, "_download", lambda *a, **k: frame)
    body = client.get("/market/prices/ABC.NS", params={"interval": "15m"}).json()
    assert [b["t"] for b in body["bars"]] == [
        "2026-10-09T09:15:00+05:30",
        "2026-10-09T09:30:00+05:30",
    ]
    assert body["freshness"]["status"] == "fresh"


def test_nav_endpoint(client: TestClient) -> None:
    _serve_mfapi()
    body = client.get("/market/nav/118989").json()
    assert [p["nav"] for p in body["points"]] == [50.0, 50.5]
    assert body["scheme_name"] and "HDFC" in body["scheme_name"]
    bad = client.get("/market/nav/404404").json()
    assert (
        bad["points"] == [] and bad["freshness"]["status"] == "unavailable" and bad["fetch_error"]
    )
    assert client.get("/market/nav/abc").status_code == 422


def test_get_missing_job_404(client: TestClient) -> None:
    assert client.get("/jobs/999").status_code == 404


def test_job_with_skipped_steps_does_not_lock_the_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a skipped step that renamed a series left a write transaction open, and the
    job's progress update (a second connection) then waited 30 s and failed: 'database is locked'."""
    import time

    from sqlmodel import Session

    from app.core.db import get_engine
    from app.models.tables import SeriesStatus

    with open(f"{SAMPLES}/groww_stocks_holdings.xlsx", "rb") as f:
        client.post("/import/groww-stocks", files={"file": f})
    _fake_yahoo(monkeypatch)
    first = client.post("/market/refresh", json={"scope": "prices"}).json()["id"]
    get_runner().wait(first, timeout=30)
    with Session(get_engine()) as s:  # rename every series so the next run has a real change
        for st in s.exec(select(SeriesStatus).where(SeriesStatus.kind == "price")):
            st.label = "renamed"
        s.commit()
    started = time.monotonic()
    second = client.post("/market/refresh", json={"scope": "prices"}).json()["id"]
    get_runner().wait(second, timeout=60)
    job = client.get(f"/jobs/{second}").json()
    assert job["status"] == "done", job["message"]
    assert "13 already fresh" in job["message"]
    assert time.monotonic() - started < 10


def test_analysis_does_not_rename_holding_series(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlmodel import Session

    from app.core.db import get_engine
    from app.models.tables import SeriesStatus

    with open(f"{SAMPLES}/groww_stocks_holdings.xlsx", "rb") as f:
        client.post("/import/groww-stocks", files={"file": f})
    _fake_yahoo(monkeypatch)
    job = client.post("/market/refresh", json={"scope": "prices"}).json()["id"]
    get_runner().wait(job, timeout=30)
    client.get("/analysis/technical/RELIANCE.NS", params={"fetch": "true", "refresh": "true"})
    client.get("/market/prices/RELIANCE.NS", params={"refresh": "true"})
    with Session(get_engine()) as s:
        st = s.get(SeriesStatus, "price:RELIANCE.NS")
        assert st and st.label == "Reliance Industries Ltd"
