from fastapi.testclient import TestClient

from app.core.profiles import get_profiles
from app.export import report as rp
from tests.unit.test_sheets import upload_stocks


def test_helpers_escape_and_format() -> None:
    assert rp.e("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert rp.e(None) == "—" and rp.e("") == "—"
    assert rp.inr(1234567.8) == "₹12,34,568"
    assert rp.inr(None) == "—"
    assert rp.pct(12.345) == "+12.3%" and rp.pct(-4.0) == "−4.0%" and rp.pct(None) == "—"
    assert rp.frac(0.123) == "12.3%"
    # A signal pill always carries its words, not just a colour.
    assert rp.pill("sell", "Sell / Exit") == '<span class="pill bad">Sell / Exit</span>'
    assert rp.pill("weird", "<b>") == '<span class="pill muted">&lt;b&gt;</span>'
    assert rp.pill_sev("high") == '<span class="pill bad">High</span>'


def test_report_with_no_data_says_so(client: TestClient) -> None:
    r = client.get("/export/report")
    assert r.status_code == 200
    html = r.text
    assert html.startswith("<!doctype html>")
    assert "Content-Security-Policy" in html and "default-src 'none'" in html
    assert "No stock holdings imported yet." in html
    assert "No mutual fund holdings imported yet." in html
    assert "Open the Screener page to run one." in html
    assert html.count(rp.e(get_profiles().disclaimer)) == 2
    assert "content-disposition" not in r.headers
    d = client.get("/export/report", params={"download": True})
    assert d.headers["content-disposition"].startswith('attachment; filename="portfolio-report-')


def test_report_lists_imported_stocks(client: TestClient) -> None:
    upload_stocks(client)
    held = client.get("/analysis/signals/holdings").json()["holdings"]
    assert held
    html = client.get("/export/report").text
    for h in held:
        assert rp.e(h["label"]) in html
        assert rp.e(h["signal_label"]) in html  # no prices cached: "Insufficient data", said so
    assert "Positional style" in html  # no style saved yet: the fallback is named


def test_summary_xirr_is_not_scaled_twice() -> None:
    from app.export.tables import summary_table
    from app.models.schemas import (
        ActionsOut,
        HoldingSignalsOut,
        MFHoldingsAnalysisOut,
        OverlapMatrixOut,
        PortfolioSummaryOut,
    )

    s = PortfolioSummaryOut.model_construct(
        as_of=None,
        total_value=100.0,
        stock_value=100.0,
        fund_value=0.0,
        invested=90.0,
        invested_note=None,
        pnl=10.0,
        pnl_pct=11.1,
        day_change=None,
        day_change_pct=None,
        day_change_note=None,
        xirr=14.2,
        xirr_basis="Covers 100%",
        warnings=[],
    )
    stocks = HoldingSignalsOut.model_construct(
        style_label="Swing", risk_label="Medium", holdings=[]
    )
    funds = MFHoldingsAnalysisOut.model_construct(
        funds=[], overlap=OverlapMatrixOut.model_construct(), warnings=[]
    )
    acts = ActionsOut.model_construct(actions=[])
    t = summary_table(s, stocks, funds, acts)
    row = next(r for r in t.rows if r[0] == "XIRR %")
    assert row[1] == 14.2  # already a percentage
