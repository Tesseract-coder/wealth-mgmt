"""Export to and import from Google Sheets, and the connection test.

Export writes only the tabs named in sheets.export_tabs (profiles.yaml): each tab is cleared
and rewritten with a title row carrying the update time, the disclaimer, the column header
and the rows. A tab of the same name that this app didn't write is left alone unless you
confirm the overwrite. Import reads one tab (service account) or one published CSV link and
runs it through the same importer as an uploaded Groww file."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlmodel import Session, select

from app.core.formatting import format_freshness, now_ist
from app.core.profiles import SheetTabKey, get_profiles
from app.data import http
from app.data.http import FetchError
from app.export.tables import ExportTables, Table, Value, build_all
from app.importers import column_mapper, groww
from app.importers.groww import Imported, NeedsMapping, UserMapping
from app.importers.tabular import Grid, ImportFileError, read_grid
from app.models.schemas import ScreenIn
from app.models.tables import SavedScreen, SheetSettings, SheetSync, UserProfile
from app.sheets.auth import ServiceAccountError, key_status
from app.sheets.client import SheetsClient, SheetsError, a1, sheets_client
from app.sheets.urls import SheetLinkError, parse_link, sheet_url, spreadsheet_id

logger = logging.getLogger(__name__)

MARKER = "Portfolio Analyzer"  # first cell of every tab this app writes
HEADER_ROWS = 4  # title, disclaimer, blank, column header
# Indian grouping (12,34,56,789.00). Sheets formats allow two conditions, so negative amounts
# of a lakh or more fall back to 1,234,567 grouping.
INR_FORMAT = r"[>=10000000]##\,##\,##\,##0.00;[>=100000]##\,##\,##0.00;##,##0.00"
TAB_ORDER: tuple[SheetTabKey, ...] = ("summary", "stocks", "mf", "screener")
Kind = Literal["stocks", "mf"]


class ForeignTabsError(RuntimeError):
    """Export would overwrite tabs this app didn't create."""

    def __init__(self, tabs: list[str]) -> None:
        super().__init__(
            f"Your sheet already has tab(s) named {', '.join(tabs)} with content this app "
            "didn't write. Confirm to overwrite them, or rename them in profiles.yaml "
            "(sheets.export_tabs)."
        )
        self.tabs = tabs


# ------------------------------------------------------------------------------ settings


def get_sheet_settings(session: Session) -> SheetSettings:
    return session.get(SheetSettings, 1) or SheetSettings(id=1)


def sheet_link(session: Session) -> str | None:
    p = session.get(UserProfile, 1)
    return p.gsheet_url if p and p.gsheet_url else None


def import_tab(s: SheetSettings, kind: Kind) -> str:
    tab = s.stocks_tab if kind == "stocks" else s.mf_tab
    return tab or get_profiles().sheets.import_tabs[kind]


def screen_request(session: Session, s: SheetSettings) -> ScreenIn:
    """The screen exported to the Screener tab ("preset:<key>" or "saved:<id>")."""
    sel = s.screener_screen or ""
    saved_id = int(sel[6:]) if sel.startswith("saved:") and sel[6:].isdigit() else None
    if saved_id is not None and session.get(SavedScreen, saved_id) is not None:
        return ScreenIn(screen_id=saved_id)
    presets = get_profiles().screener.presets
    key = sel[7:] if sel.startswith("preset:") else ""
    return ScreenIn(preset=key if key in presets else next(iter(presets)))


def record(session: Session, direction: str, detail: str | None, ok: bool, message: str) -> None:
    session.add(SheetSync(direction=direction, detail=detail, ok=ok, message=message))
    session.commit()


def last_sync(session: Session, direction: str) -> SheetSync | None:
    q = select(SheetSync).where(SheetSync.direction == direction)
    return session.exec(q.order_by(SheetSync.at.desc())).first()  # type: ignore[attr-defined]


# -------------------------------------------------------------------------------- export


def _cell(v: Value) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def tab_values(t: Table, updated: str, disclaimer: str) -> list[list[Any]]:
    head: list[list[Any]] = [
        [f"{MARKER} · {t.title}", f"Updated {updated}", t.context],
        [disclaimer],
        [],
        list(t.header),
    ]
    if not t.rows:
        return head + [[t.empty_note or "No rows."]]
    return head + [[_cell(v) for v in r] for r in t.rows]


def _is_ours(first_rows: list[list[Any]]) -> bool:
    """Blank, or written by this app (its first cell starts with MARKER)."""
    if not any(str(c).strip() for row in first_rows for c in row):
        return True
    return bool(first_rows and first_rows[0] and str(first_rows[0][0]).startswith(MARKER))


def _repeat(rng: dict[str, int], fmt: dict[str, Any], fields: str) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": rng,
            "cell": {"userEnteredFormat": fmt} if fmt else {},
            "fields": fields,
        }
    }


def _grid(sheet_id: int | None, rows: int, cols: int, title: str | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {"gridProperties": {"rowCount": rows, "columnCount": cols}}
    if title is not None:
        return {"addSheet": {"properties": {"title": title, **props}}}
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, **props},
            "fields": "gridProperties.rowCount,gridProperties.columnCount",
        }
    }


def _format_requests(sheet_id: int, t: Table, n_values: int) -> list[dict[str, Any]]:
    def rng(r0: int, r1: int, c0: int, c1: int) -> dict[str, int]:
        return {
            "sheetId": sheet_id,
            "startRowIndex": r0,
            "endRowIndex": r1,
            "startColumnIndex": c0,
            "endColumnIndex": c1,
        }

    bold, bold_f = {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat.bold"
    inr, inr_f = (
        {"numberFormat": {"type": "NUMBER", "pattern": INR_FORMAT}},
        ("userEnteredFormat.numberFormat"),
    )
    frozen = {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": HEADER_ROWS}}
    reqs: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": frozen,
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Earlier exports may have formatted cells that now hold other columns: reset first.
        _repeat({"sheetId": sheet_id}, {}, "userEnteredFormat"),
        _repeat(rng(0, 1, 0, 1), bold, bold_f),
        _repeat(rng(HEADER_ROWS - 1, HEADER_ROWS, 0, len(t.header)), bold, bold_f),
    ]
    if t.rows:
        reqs += [_repeat(rng(HEADER_ROWS, n_values, c, c + 1), inr, inr_f) for c in t.inr_columns]
        reqs += [
            _repeat(rng(HEADER_ROWS + r, HEADER_ROWS + r + 1, 1, 2), inr, inr_f) for r in t.inr_rows
        ]
    return reqs


@dataclass
class ExportResult:
    url: str
    title: str
    tabs: list[tuple[str, int]]  # (tab name, data rows)
    at: datetime


def write_tables(
    client: SheetsClient, sid: str, tables: ExportTables, overwrite: set[str] | None = None
) -> ExportResult:
    cfg = get_profiles().sheets
    by_key: dict[SheetTabKey, Table] = {
        "stocks": tables.stocks,
        "mf": tables.funds,
        "screener": tables.screener,
        "summary": tables.summary,
    }
    updated = format_freshness(now_ist())
    disclaimer = get_profiles().disclaimer
    plan = [
        (cfg.export_tabs[k], by_key[k], tab_values(by_key[k], updated, disclaimer))
        for k in TAB_ORDER
    ]
    book = client.spreadsheet(sid)

    existing = [name for name, _, _ in plan if book.tab(name)]
    firsts = client.batch_values(sid, [a1(book.tab(n).title, "A1:C3") for n in existing])  # type: ignore[union-attr]
    allowed = {o.strip().lower() for o in overwrite or set()}
    foreign = [
        n
        for n, v in zip(existing, firsts, strict=True)
        if not _is_ours(v) and n.lower() not in allowed
    ]
    if foreign:
        raise ForeignTabsError(foreign)

    # Create missing tabs and make sure each is big enough for its values.
    grow: list[dict[str, Any]] = []
    for name, t, values in plan:
        rows, cols = len(values) + 10, max(len(t.header), 3) + 1
        tab = book.tab(name)
        if tab is None:
            grow.append(_grid(None, max(rows, 100), max(cols, 26), title=name))
        elif tab.rows < rows or tab.cols < cols:
            grow.append(_grid(tab.sheet_id, max(rows, tab.rows), max(cols, tab.cols)))
    client.batch_update(sid, grow)
    if grow:
        book = client.spreadsheet(sid)

    titles = [book.tab(name).title for name, _, _ in plan]  # type: ignore[union-attr]
    client.clear(sid, [a1(t) for t in titles])
    client.write(
        sid, [(a1(t, "A1"), values) for t, (_, _, values) in zip(titles, plan, strict=True)]
    )
    fmt: list[dict[str, Any]] = []
    for title, (_, t, values) in zip(titles, plan, strict=True):
        fmt += _format_requests(book.tab(title).sheet_id, t, len(values))  # type: ignore[union-attr]
    client.batch_update(sid, fmt)
    return ExportResult(
        sheet_url(sid), book.title, [(n, len(t.rows)) for n, t, _ in plan], now_ist()
    )


def export_to_sheet(
    session: Session,
    client: SheetsClient | None = None,
    overwrite: set[str] | None = None,
) -> ExportResult:
    """Build every table from cached data and write the four export tabs. Records the outcome."""
    link = sheet_link(session)
    try:
        if not link:
            raise SheetLinkError("Add your Google Sheet's link first (Settings → Google Sheets).")
        sid = spreadsheet_id(link)
        c = client or sheets_client()
        tables = build_all(session, screen_request(session, get_sheet_settings(session)))
        result = write_tables(c, sid, tables, overwrite)
    except (SheetLinkError, ServiceAccountError, SheetsError, ForeignTabsError) as e:
        record(session, "export", None, False, str(e))
        raise
    msg = "Wrote " + ", ".join(f"{n} ({r} rows)" for n, r in result.tabs)
    record(session, "export", result.title, True, msg)
    logger.info("Exported to Google Sheet %s: %s", sid, msg)
    return result


# -------------------------------------------------------------------------------- import


def _limit(grid: Grid, where: str) -> Grid:
    cap = get_profiles().sheets.max_import_rows
    if len(grid) > cap:
        raise ImportFileError(
            f"{where} has {len(grid)} rows; the limit is {cap} (sheets.max_import_rows)."
        )
    return grid


def _run_import(
    session: Session, kind: Kind, grid: Grid, name: str, source: str, user: UserMapping | None
) -> Imported | NeedsMapping:
    if not any(any(str(c).strip() for c in row if c is not None) for row in grid):
        raise ImportFileError(f"{name} is empty.")
    fn = groww.import_stocks_grid if kind == "stocks" else groww.import_mf_grid
    return fn(session, grid, name, source, user)


def import_from_tab(
    session: Session,
    kind: Kind,
    tab: str | None = None,
    user: UserMapping | None = None,
    client: SheetsClient | None = None,
) -> Imported | NeedsMapping:
    """Holdings from a tab of your sheet, read with the service account."""
    s = get_sheet_settings(session)
    name = (tab or import_tab(s, kind)).strip()
    try:
        link = sheet_link(session)
        if not link:
            raise SheetLinkError("Add your Google Sheet's link first (Settings → Google Sheets).")
        sid = spreadsheet_id(link)
        c = client or sheets_client()
        book = c.spreadsheet(sid)
        t = book.tab(name)
        if t is None:
            tabs = ", ".join(x.title for x in book.tabs)
            raise SheetsError(f"No tab named '{name}'. Tabs in this sheet: {tabs}")
        grid: Grid = _limit(c.values(sid, a1(t.title)), f"Tab '{t.title}'")
        result = _run_import(session, kind, grid, f"Google Sheet · {t.title}", "gsheet", user)
    except (SheetLinkError, ServiceAccountError, SheetsError, ImportFileError, ValueError) as e:
        record(session, "import", f"{kind} · {name}", False, str(e))
        raise
    _record_import(session, kind, name, result)
    return result


def _looks_like_html(content: bytes) -> bool:
    head = content[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return head.startswith((b"<!doctype", b"<html", b"<"))


def fetch_csv(url: str) -> Grid:
    """Download a published (or 'anyone with the link') tab as CSV."""
    link = parse_link(url)
    try:
        content = http.get_bytes("google", link.csv_url)
    except FetchError as e:
        raise SheetLinkError(
            f"Couldn't download the sheet as CSV ({str(e).rsplit('(', 1)[-1].rstrip(')')}). "
            "Publish the tab (File → Share → Publish to web → CSV) or set sharing to "
            "'Anyone with the link'."
        ) from None
    if _looks_like_html(content):
        raise SheetLinkError(
            "Google returned a sign-in page instead of CSV, so the tab isn't public. Publish it "
            "(File → Share → Publish to web → choose the tab → CSV), or use the service account."
        )
    return _limit(read_grid(content, "sheet.csv"), "The published tab")


def import_from_csv(
    session: Session, kind: Kind, url: str, user: UserMapping | None = None
) -> Imported | NeedsMapping:
    try:
        grid = fetch_csv(url)
        result = _run_import(
            session, kind, grid, "Google Sheet (published CSV)", "gsheet_csv", user
        )
    except (SheetLinkError, ImportFileError, ValueError) as e:
        record(session, "import", f"{kind} · published link", False, str(e))
        raise
    _record_import(session, kind, "published link", result)
    return result


def _record_import(session: Session, kind: Kind, where: str, r: Imported | NeedsMapping) -> None:
    if isinstance(r, Imported):
        n = r.snapshot.row_count
        record(session, "import", f"{kind} · {where}", True, f"Imported {n} holding(s)")


# ------------------------------------------------------------------------ connection test


@dataclass
class Check:
    name: str
    ok: bool | None  # None: not run, or informational
    detail: str


def _csv_check(label: str, url: str, kind: Kind) -> Check:
    try:
        grid = fetch_csv(url)
    except (SheetLinkError, ImportFileError) as e:
        return Check(label, False, str(e))
    m = column_mapper.detect(grid, kind, get_profiles().importing)
    if m.complete:
        cols = ", ".join(m.headers[i] for i in sorted(m.mapping.values()))
        return Check(label, True, f"{len(grid)} rows; columns recognised: {cols}")
    return Check(
        label,
        True,
        f"{len(grid)} rows downloaded. Some columns weren't recognised "
        f"({', '.join(m.missing_required)}); you'll be asked to map them on import.",
    )


def check_connection(session: Session, client: SheetsClient | None = None) -> list[Check]:
    """Every step from the key file to write access, plus the published links if any."""
    s = get_sheet_settings(session)
    cfg = get_profiles().sheets
    checks: list[Check] = []
    link = sheet_link(session)
    ks = key_status()
    if ks.configured:
        checks.append(Check("Service-account key", True, f"{ks.client_email} ({ks.path})"))
    else:
        checks.append(
            Check(
                "Service-account key",
                False if ks.error or link else None,
                ks.error
                or f"No key at {ks.path}. Needed only to read tabs directly and to export.",
            )
        )
    sid: str | None = None
    if not link:
        checks.append(Check("Sheet link", None, "No sheet link saved."))
    else:
        try:
            sid = spreadsheet_id(link)
            checks.append(Check("Sheet link", True, sheet_url(sid)))
        except SheetLinkError as e:
            checks.append(Check("Sheet link", False, str(e)))

    if ks.configured and sid:
        try:
            c = client or sheets_client()
            c.tokens.token()
            checks.append(Check("Sign in to Google", True, "Access token received"))
            book = c.spreadsheet(sid)
            checks.append(
                Check(
                    "Open the sheet",
                    True,
                    f"'{book.title}': tabs {', '.join(t.title for t in book.tabs)}",
                )
            )
            # A no-op edit (title set to itself) proves Editor access without changing anything.
            c.batch_update(
                sid,
                [
                    {
                        "updateSpreadsheetProperties": {
                            "properties": {"title": book.title},
                            "fields": "title",
                        }
                    }
                ],
            )
            checks.append(Check("Write access", True, "The service account can edit this sheet"))
            kinds: tuple[Kind, ...] = ("stocks", "mf")
            for kind in kinds:
                tab = import_tab(s, kind)
                t = book.tab(tab)
                checks.append(
                    Check(
                        f"Import tab ({'stocks' if kind == 'stocks' else 'mutual funds'})",
                        True if t else None,
                        f"'{tab}' found"
                        if t
                        else f"No tab '{tab}' (only needed to import from this sheet)",
                    )
                )
            existing = [n for n in cfg.export_tabs.values() if book.tab(n)]
            firsts = c.batch_values(sid, [a1(book.tab(n).title, "A1:C3") for n in existing])  # type: ignore[union-attr]
            foreign = [n for n, v in zip(existing, firsts, strict=True) if not _is_ours(v)]
            names = ", ".join(cfg.export_tabs.values())
            checks.append(
                Check(
                    "Export tabs",
                    not foreign,
                    f"{', '.join(foreign)} already hold other content; export will ask first"
                    if foreign
                    else f"{names} will be written (missing ones are created)",
                )
            )
        except (ServiceAccountError, SheetsError) as e:
            done = {ch.name for ch in checks}
            step = next(
                n
                for n in ("Sign in to Google", "Open the sheet", "Write access", "Export tabs")
                if n not in done
            )
            checks.append(Check(step, False, str(e)))

    links: list[tuple[Kind, str | None]] = [("stocks", s.stocks_csv_url), ("mf", s.mf_csv_url)]
    for k, url in links:
        if url:
            what = "stocks" if k == "stocks" else "mutual funds"
            checks.append(_csv_check(f"Published link ({what})", url, k))
    ok = all(ch.ok is not False for ch in checks) and any(ch.ok for ch in checks)
    record(
        session,
        "test",
        None,
        ok,
        "; ".join(
            f"{ch.name}: {'ok' if ch.ok else 'failed' if ch.ok is False else 'n/a'}"
            for ch in checks
        ),
    )
    return checks


def sheets_refresh_step(session: Session) -> tuple[str, str]:
    """For the scheduled daily refresh: export if auto-export is on. (outcome, message)"""
    s = get_sheet_settings(session)
    if not s.auto_export:
        return "skipped", "Auto-export is off"
    if not sheet_link(session) or not key_status().configured:
        return "skipped", "No sheet link or service-account key"
    try:
        r = export_to_sheet(session)
    except (SheetLinkError, ServiceAccountError, SheetsError, ForeignTabsError) as e:
        return "failed", str(e)
    return "updated", f"Exported to '{r.title}'"
