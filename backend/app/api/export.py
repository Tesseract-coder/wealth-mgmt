"""CSV exports of your signals. Numbers stay plain (no ₹ or grouping) so spreadsheets can
use them; every file ends with the generation time and the disclaimer."""

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session

from app.api.funds import mf_holdings
from app.api.screener import screen_scan
from app.api.signals import holdings_signals
from app.core.db import get_session
from app.core.formatting import format_freshness, now_ist
from app.core.profiles import get_profiles
from app.export.report import build_report
from app.export.tables import Table, funds_table, screener_table, stocks_table
from app.models.schemas import ScreenIn
from app.sheets.sync import get_sheet_settings, screen_request

router = APIRouter(prefix="/export", tags=["export"])


def csv_response(t: Table) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(t.header)
    for r in t.rows:
        w.writerow(["" if v is None else v for v in r])
    w.writerow([])
    w.writerow(["Generated", format_freshness(now_ist())])
    w.writerow(["Profile", t.context])
    w.writerow(["Disclaimer", get_profiles().disclaimer])
    stamp = now_ist().strftime("%Y-%m-%d")
    return Response(
        content="﻿" + buf.getvalue(),  # BOM so Excel reads ₹ and accents as UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{t.slug}-{stamp}.csv"'},
    )


@router.get("/stocks.csv")
def stocks_csv(session: Session = Depends(get_session)) -> Response:
    """Your stock holdings with signal, scores, confidence, stop and suggested action."""
    return csv_response(stocks_table(holdings_signals(None, None, session)))


@router.get("/funds.csv")
def funds_csv(session: Session = Depends(get_session)) -> Response:
    """Your mutual funds with signal, returns vs benchmark, cost and reasons."""
    return csv_response(funds_table(mf_holdings(session)))


@router.get("/screener.csv")
def screener_csv(
    preset: str | None = Query(None, description="Preset key (default: the first preset)"),
    screen_id: int | None = Query(None, description="A saved screen instead of a preset"),
    include_held: bool = False,
    scan_id: int | None = None,
    session: Session = Depends(get_session),
) -> Response:
    """The candidates of a preset or saved screen on the latest (or given) scan."""
    d = screen_scan(
        ScreenIn(scan_id=scan_id, preset=preset, screen_id=screen_id, include_held=include_held),
        session,
    )
    return csv_response(screener_table(d))


@router.get("/report", response_class=HTMLResponse)
def report(
    download: bool = Query(False, description="Send as a file instead of showing it"),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Portfolio report as one self-contained HTML page: summary, actions, allocation, every
    stock and fund with its signal and reasons, screener ideas, data freshness and the
    disclaimer. Use the browser's Print → Save as PDF for a PDF. Cached data only."""
    html = build_report(session, screen_request(session, get_sheet_settings(session)))
    headers = {"Cache-Control": "no-store"}
    if download:
        stamp = now_ist().strftime("%Y-%m-%d")
        headers["Content-Disposition"] = f'attachment; filename="portfolio-report-{stamp}.html"'
    return HTMLResponse(html, headers=headers)
