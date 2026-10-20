from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.data import store
from app.data.market import all_listings, market_listings
from app.data.prices import price_key
from app.jobs.tasks import TOPUP_RETRY_AFTER, topup_targets
from app.screener.scan import custom_members, members_for, parse_symbols
from tests.conftest import FRI_EVENING


def test_every_listed_stock_once_with_bse_only_shares_as_bo() -> None:
    every = all_listings()
    assert len({x.ticker for x in every}) == len(every)
    rel = next(x for x in every if x.ticker == "RELIANCE.NS")
    assert rel.index == "nifty50" and rel.industry
    bse = market_listings("bse_only")
    assert bse and all(x.ticker.endswith(".BO") and x.index is None for x in bse)
    assert not any(x.isin == y.isin for x in bse[:50] for y in market_listings("nse_all"))


def test_screener_takes_whole_market_and_bse_symbols() -> None:
    members, unknown = members_for("bse_only")
    assert len(members) == len(market_listings("bse_only")) and not unknown
    bo = members[0].ticker
    found, unknown = custom_members(parse_symbols(f"tcs, {bo.lower()}, NOPEXYZ"))
    assert [m.ticker for m in found] == ["TCS.NS", bo] and unknown == ["NOPEXYZ"]


def test_topup_goes_nifty_50_first_and_skips_loaded_and_recent_failures(session: Session) -> None:
    first = topup_targets(session, 3, FRI_EVENING)
    assert all(x.index == "nifty50" for x in first)
    done, failed = first[0], first[1]
    st = store.status_row(session, price_key(done.ticker), "price", "yahoo", done.symbol)
    st.last_success_at = store.to_utc(FRI_EVENING)
    st = store.status_row(session, price_key(failed.ticker), "price", "yahoo", failed.symbol)
    st.last_attempt_at, st.last_error = store.to_utc(FRI_EVENING), "no data"
    session.commit()
    nxt = [x.ticker for x in topup_targets(session, 3, FRI_EVENING)]
    assert done.ticker not in nxt and failed.ticker not in nxt and first[2].ticker == nxt[0]
    later = FRI_EVENING + TOPUP_RETRY_AFTER + timedelta(days=1)
    assert failed.ticker in [x.ticker for x in topup_targets(session, 3, later)]  # tried again
    last = topup_targets(session, 10_000, FRI_EVENING)
    assert last[-1].exchange == "BSE"  # BSE-only shares come last


def test_directory_lists_filters_and_pages(client: TestClient) -> None:
    b = client.get("/stocks", params={"limit": 5}).json()
    assert b["total"] == b["all"] > 4000 and len(b["rows"]) == 5 and b["loaded"] == 0
    assert all(not r["loaded"] and r["close"] is None for r in b["rows"])
    bse = client.get("/stocks", params={"exchange": "BSE", "limit": 2}).json()
    assert bse["total"] < b["all"] and all(r["exchange"] == "BSE" for r in bse["rows"])
    n50 = client.get("/stocks", params={"index": "nifty50", "limit": 100}).json()
    assert n50["total"] == 50 and {"Financial Services"} <= {s["name"] for s in n50["sectors"]}
    banks = client.get("/stocks", params={"index": "nifty50", "sector": "Financial Services"})
    assert 0 < banks.json()["total"] < 50
    rel = client.get("/stocks", params={"q": "reliance industries"}).json()["rows"]
    assert rel[0]["ticker"] == "RELIANCE.NS" and rel[0]["index"] == "nifty50"
    page2 = client.get("/stocks", params={"limit": 5, "offset": 5}).json()["rows"]
    assert page2[0]["ticker"] != b["rows"][0]["ticker"]


def test_topup_runs_each_weeknight_unless_turned_off(session: Session) -> None:
    from app.jobs import scheduler
    from app.jobs.runner import get_runner

    scheduler.start_scheduler(get_runner())
    try:
        jobs = {j.id: j for j in scheduler.scheduled_jobs()}
        assert "topup" in jobs and jobs["topup"].next_run is not None
        assert jobs["topup"].next_run.hour == 22 and jobs["topup"].next_run.weekday() < 5
    finally:
        scheduler.stop_scheduler()
