from datetime import date, timedelta

import httpx
from sqlmodel import Session

from app.data import bse, http
from app.data.files import locate
from app.data.reference_refresh import is_due, refresh_reference
from app.importers.reference import ticker_resolver
from tests.conftest import FRI_EVENING

HEAD = "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,FinInstrmNm,ClsPric\n"


def bhav(day: date, rows: list[tuple[str, str, str, str, str]]) -> str:
    """rows: (code, isin, symbol, group, name)."""
    body = "".join(f"{day},{day},CM,BSE,STK,{c},{i},{s},{g},{n},10\n" for c, i, s, g, n in rows)
    return HEAD + body


def test_bhavcopy_keeps_company_shares_only() -> None:
    text = bhav(
        date(2026, 10, 9),
        [
            ("500012", "INE714B01016", "ANDHRAPET", "X", "ANDHRA PETROCHEMICALS LTD."),
            ("541097", "INF732E01268", "LIQUIDETF", "F", "DSP Liquid ETF"),
            ("800161", "IN0020210012", "883GS2041", "G", "883GOI2041"),
            ("540526", "INE183W23014", "IRBINVIT", "IF", "IRB InvIT Fund"),
            ("543900", "INE0ABC01011", "SMECO", "M", "SME Co Ltd"),
        ],
    )
    assert [s.symbol for s in bse.parse_bhavcopy(text)] == ["ANDHRAPET", "SMECO"]


def test_merge_keeps_the_latest_and_drops_shares_unseen_for_a_month() -> None:
    today = date(2026, 10, 9)
    old = [
        bse.BseScrip("1", "OLDNAME", "Old Name", "INE1", "B", today - timedelta(days=5)),
        bse.BseScrip("2", "GONE", "Gone", "INE2", "B", today - timedelta(days=40)),
    ]
    new = [bse.BseScrip("1", "NEWNAME", "New Name", "INE1", "B", today)]
    merged = bse.merge(old, new, today)
    assert [(s.code, s.symbol) for s in merged] == [("1", "NEWNAME")]
    assert bse.parse_list(bse.write_list(merged)) == merged


def test_refresh_merges_the_latest_published_bhavcopy(session: Session) -> None:
    friday = FRI_EVENING.date()
    rows = [(f"5{i:05d}", f"INE{i:09d}", f"BSESYM{i}", "X", f"Company {i}") for i in range(3200)]
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if f"{friday:%Y%m%d}" in str(req.url):  # today's isn't published: BSE serves a web page
            return httpx.Response(200, content=b"<!DOCTYPE html><html>not yet</html>")
        return httpx.Response(200, content=bhav(friday - timedelta(days=1), rows).encode())

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    r = refresh_reference(session, "bse_equity", now=FRI_EVENING)
    assert r.outcome == "updated" and r.rows is not None and r.rows >= 3200
    assert len(seen) == 2 and "20261008" in seen[1]
    assert locate("bse_equity")[1] == "refreshed"
    assert any(s.symbol == "BSESYM3199" for s in bse.load_bse())  # caches cleared
    assert ticker_resolver().lookup("BSESYM5.BO") is not None
    assert not is_due(session, "bse_equity", FRI_EVENING + timedelta(hours=12))
    assert is_due(session, "bse_equity", FRI_EVENING + timedelta(days=1))


def test_bse_only_shares_resolve_to_bo_tickers_and_dual_listed_to_nse() -> None:
    r = ticker_resolver()
    only = next(iter(r.bse_by_symbol.values()))
    assert only.exchange == "BSE" and only.ticker == f"{only.symbol}.BO"
    assert r.resolve("anything", only.isin).exchange == "BSE"
    # Reliance trades on both: its BSE code and BSE ticker lead to NSE.
    rel = r.lookup("500325")
    assert rel is not None and rel.ticker == "RELIANCE.NS"
    assert r.resolve("x", None, symbol_hint="500325").symbol == "RELIANCE"
    assert {s.exchange for s in r.search(only.name, 5)} >= {"BSE"}
