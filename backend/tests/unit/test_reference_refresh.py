import gzip
from datetime import timedelta

import httpx
import pytest
from sqlmodel import Session

from app.core.settings import get_settings
from app.data import http, nse
from app.data.files import locate
from app.data.reference_refresh import is_due, reference_status, refresh_reference
from tests.conftest import FRI_EVENING

HEADER = "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"


def equity_csv(n: int) -> bytes:
    rows = [f"SYM{i},Company {i} Limited,EQ,01-JAN-2000,10,1,INE{i:09d},10" for i in range(n)]
    return (HEADER + "\n".join(rows) + "\n").encode()


def serve(content: bytes, status: int = 200) -> list[str]:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(status, content=content)

    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))
    return seen


def test_bundled_copy_is_used_until_refreshed(session: Session) -> None:
    path, origin = locate("nse_equity")
    assert origin == "bundled" and path.parent == get_settings().fallback_data_dir
    st = {r.key: r for r in reference_status(session, FRI_EVENING)}
    assert st["nse_equity"].origin == "bundled" and st["nse_equity"].as_of is not None


def test_refresh_swaps_in_new_list_and_clears_caches(session: Session) -> None:
    assert len(nse.load_securities()) > 2000  # bundled
    seen = serve(equity_csv(1500))
    r = refresh_reference(session, "nse_equity", now=FRI_EVENING)
    assert r.outcome == "updated" and r.rows == 1500
    assert seen == ["https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"]
    path, origin = locate("nse_equity")
    assert origin == "refreshed" and path.parent == get_settings().reference_data_dir
    assert any(s.symbol == "SYM1499" for s in nse.load_securities())  # cache was cleared
    assert not is_due(session, "nse_equity", FRI_EVENING + timedelta(days=1))
    assert is_due(session, "nse_equity", FRI_EVENING + timedelta(days=8))
    assert refresh_reference(session, "nse_equity", now=FRI_EVENING).outcome == "skipped"


def test_too_small_download_is_rejected(session: Session) -> None:
    serve(equity_csv(10))
    r = refresh_reference(session, "nse_equity", now=FRI_EVENING)
    assert r.outcome == "failed" and "only 10 rows" in r.message
    assert locate("nse_equity")[1] == "bundled"  # old copy kept
    st = {s.key: s for s in reference_status(session, FRI_EVENING)}["nse_equity"]
    assert "only 10 rows" in st.freshness.reason


def test_http_error_is_recorded(session: Session) -> None:
    serve(b"", status=403)
    r = refresh_reference(session, "nifty500", now=FRI_EVENING)
    assert r.outcome == "failed" and "HTTP 403" in r.message


def test_amfi_list_is_stored_gzipped_and_due_after_nav_cutoff(session: Session) -> None:
    text = "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n\nAxis Mutual Fund\n"
    text += "\n".join(
        f"{100000 + i};INF000000000;;Fund {i} - Direct Plan - Growth;10.5;09-Oct-2026"
        for i in range(6000)
    )
    serve(text.encode())
    assert refresh_reference(session, "amfi_navall", now=FRI_EVENING).outcome == "updated"
    path, _ = locate("amfi_navall")
    assert gzip.decompress(path.read_bytes()).decode().startswith("Scheme Code")
    assert not is_due(session, "amfi_navall", FRI_EVENING + timedelta(hours=2))  # 19:00 Fri
    assert is_due(
        session, "amfi_navall", FRI_EVENING + timedelta(hours=7)
    )  # 00:00 Sat, after 23:30


@pytest.mark.parametrize("key", ["nse_etf", "nifty500"])
def test_garbage_html_is_rejected(session: Session, key: str) -> None:
    serve(b"<html><body>Access denied</body></html>")
    assert refresh_reference(session, key, force=True, now=FRI_EVENING).outcome == "failed"  # type: ignore[arg-type]
