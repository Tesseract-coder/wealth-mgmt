"""CSV and PDF exports of your signals. CSV numbers stay plain (no ₹ or grouping) so
spreadsheets can use them; the PDF is laid out to read on a phone. Every file ends with the
generation time and the disclaimer."""

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
from app.export.pdf import table_pdf
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


def pdf_response(t: Table) -> Response:
    stamp = now_ist().strftime("%Y-%m-%d")
    return Response(
        content=table_pdf(t),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{t.slug}-{stamp}.pdf"'},
    )


def _screener(
    preset: str | None,
    screen_id: int | None,
    include_held: bool,
    scan_id: int | None,
    session: Session,
) -> Table:
    d = screen_scan(
        ScreenIn(scan_id=scan_id, preset=preset, screen_id=screen_id, include_held=include_held),
        session,
    )
    return screener_table(d)


@router.get("/stocks.csv")
def stocks_csv(session: Session = Depends(get_session)) -> Response:
    """Your stock holdings with signal, scores, confidence, stop and suggested action."""
    return csv_response(stocks_table(holdings_signals(None, None, session)))


@router.get("/stocks.pdf")
def stocks_pdf(session: Session = Depends(get_session)) -> Response:
    """Your stock holdings as a phone-readable PDF, one card per stock."""
    return pdf_response(stocks_table(holdings_signals(None, None, session)))


@router.get("/funds.csv")
def funds_csv(session: Session = Depends(get_session)) -> Response:
    """Your mutual funds with signal, returns vs benchmark, cost and reasons."""
    return csv_response(funds_table(mf_holdings(session)))


@router.get("/funds.pdf")
def funds_pdf(session: Session = Depends(get_session)) -> Response:
    """Your mutual funds as a phone-readable PDF, one card per fund."""
    return pdf_response(funds_table(mf_holdings(session)))


@router.get("/screener.csv")
def screener_csv(
    preset: str | None = Query(None, description="Preset key (default: the first preset)"),
    screen_id: int | None = Query(None, description="A saved screen instead of a preset"),
    include_held: bool = False,
    scan_id: int | None = None,
    session: Session = Depends(get_session),
) -> Response:
    """The candidates of a preset or saved screen on the latest (or given) scan."""
    return csv_response(_screener(preset, screen_id, include_held, scan_id, session))


@router.get("/screener.pdf")
def screener_pdf(
    preset: str | None = Query(None, description="Preset key (default: the first preset)"),
    screen_id: int | None = Query(None, description="A saved screen instead of a preset"),
    include_held: bool = False,
    scan_id: int | None = None,
    session: Session = Depends(get_session),
) -> Response:
    """The screen's candidates as a phone-readable PDF, one card per stock."""
    return pdf_response(_screener(preset, screen_id, include_held, scan_id, session))


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
