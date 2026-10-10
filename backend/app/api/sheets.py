"""Google Sheets: settings, service-account key upload, connection test, export and import.

The service-account key is a Google Cloud robot identity you share one sheet with; it has
nothing to do with your broker. Its private key never leaves secrets/ or this process."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.api.convert import imported_out
from app.api.imports import needs_mapping_out
from app.core.db import get_session
from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.importers.groww import NeedsMapping, UserMapping
from app.importers.tabular import ImportFileError
from app.models.schemas import (
    ImportedOut,
    NeedsMappingOut,
    ServiceAccountOut,
    SheetCheckOut,
    SheetExportIn,
    SheetExportOut,
    SheetImportIn,
    SheetSettingsIn,
    SheetSettingsOut,
    SheetsStatusOut,
    SheetSyncOut,
    SheetTabOut,
    SheetTestOut,
)
from app.models.tables import SheetSync, UserProfile
from app.sheets import sync
from app.sheets.auth import MAX_KEY_BYTES, ServiceAccountError, key_status, save_key
from app.sheets.client import SheetsError
from app.sheets.urls import SheetLinkError, parse_link, sheet_url, spreadsheet_id

router = APIRouter(prefix="/sheets", tags=["google sheets"])
HISTORY = 10


def _status(session: Session) -> SheetsStatusOut:
    s = sync.get_sheet_settings(session)
    link = sync.sheet_link(session)
    sid, link_error = None, None
    if link:
        try:
            sid = spreadsheet_id(link)
        except SheetLinkError as e:
            link_error = str(e)
    ks = key_status()
    cfg = get_profiles()
    q = select(SheetSync).order_by(SheetSync.at.desc()).limit(HISTORY)  # type: ignore[attr-defined]
    return SheetsStatusOut(
        service_account=ServiceAccountOut(**ks.__dict__),
        sheet_url=link,
        spreadsheet_url=sheet_url(sid) if sid else None,
        link_error=link_error,
        settings=SheetSettingsOut(
            stocks_tab=sync.import_tab(s, "stocks"),
            mf_tab=sync.import_tab(s, "mf"),
            stocks_csv_url=s.stocks_csv_url,
            mf_csv_url=s.mf_csv_url,
            screener_screen=s.screener_screen,
            auto_export=s.auto_export,
        ),
        export_tabs=dict(cfg.sheets.export_tabs),
        default_import_tabs=dict(cfg.sheets.import_tabs),
        history=[SheetSyncOut.model_validate(r, from_attributes=True) for r in session.exec(q)],
        refresh_time_ist=cfg.data.refresh_time_ist,
    )


@router.get("/status", response_model=SheetsStatusOut)
def sheets_status(session: Session = Depends(get_session)) -> SheetsStatusOut:
    """What's configured (key, link, tabs, auto-export) and the last few syncs."""
    return _status(session)


def _sheets_http(e: SheetsError) -> HTTPException:
    """Things you can fix (sharing, link, tab name) are 400; Google being down or busy is 502."""
    busy = e.status is not None and (e.status == 429 or e.status >= 500)
    return HTTPException(502 if busy else 400, str(e))


def _clean(v: str | None) -> str | None:
    return v.strip() or None if v else None


@router.put("/settings", response_model=SheetsStatusOut)
def put_sheet_settings(
    body: SheetSettingsIn, session: Session = Depends(get_session)
) -> SheetsStatusOut:
    """Save the sheet link, import tabs, published CSV links, export screen and auto-export.
    Links must be Google Sheets links (https://docs.google.com/spreadsheets/…)."""
    for label, url in (
        ("Sheet link", body.sheet_url),
        ("Stocks CSV link", body.stocks_csv_url),
        ("Mutual funds CSV link", body.mf_csv_url),
    ):
        if _clean(url):
            try:
                parse_link(url or "")
            except SheetLinkError as e:
                raise HTTPException(422, f"{label}: {e}") from None
    s = sync.get_sheet_settings(session)
    defaults = get_profiles().sheets.import_tabs
    stocks_tab, mf_tab = _clean(body.stocks_tab), _clean(body.mf_tab)
    s.stocks_tab = None if stocks_tab == defaults["stocks"] else stocks_tab
    s.mf_tab = None if mf_tab == defaults["mf"] else mf_tab
    s.stocks_csv_url = _clean(body.stocks_csv_url)
    s.mf_csv_url = _clean(body.mf_csv_url)
    s.screener_screen = body.screener_screen
    s.auto_export = body.auto_export
    s.updated_at = now_ist()
    session.add(s)
    profile = session.get(UserProfile, 1)
    if profile is None:
        d = get_profiles().defaults
        profile = UserProfile(id=1, style=d.style, risk=d.risk)
    profile.gsheet_url = _clean(body.sheet_url)
    session.add(profile)
    session.commit()
    return _status(session)


@router.post("/service-account", response_model=ServiceAccountOut)
async def upload_service_account(file: UploadFile = File(...)) -> ServiceAccountOut:
    """Store a service-account key (JSON) in secrets/, readable only by you. Replaces any
    previous key. Only the robot's e-mail address is returned, never the private key."""
    content = await file.read(MAX_KEY_BYTES + 1)
    try:
        save_key(content)
    except ServiceAccountError as e:
        raise HTTPException(400, str(e)) from None
    finally:
        del content
    return ServiceAccountOut(**key_status().__dict__)


@router.post("/test", response_model=SheetTestOut)
def test_sheets(session: Session = Depends(get_session)) -> SheetTestOut:
    """Check each step: key, link, sign-in, opening the sheet, write access, tabs, and any
    published CSV links. Changes nothing in the sheet."""
    checks = sync.check_connection(session)
    ok = all(c.ok is not False for c in checks) and any(c.ok for c in checks)
    return SheetTestOut(ok=ok, checks=[SheetCheckOut(**c.__dict__) for c in checks])


@router.post("/export", response_model=SheetExportOut)
def export_sheets(
    body: SheetExportIn | None = None, session: Session = Depends(get_session)
) -> SheetExportOut:
    """Write the Summary, Analysis_Stocks, Analysis_MF and Screener tabs (names from
    profiles.yaml), each stamped with the update time and the disclaimer.

    409 if a tab of the same name holds content this app didn't write; resend with those
    names in `overwrite` to replace them."""
    try:
        r = sync.export_to_sheet(session, overwrite=set(body.overwrite) if body else None)
    except sync.ForeignTabsError as e:
        raise HTTPException(409, {"message": str(e), "tabs": e.tabs}) from None
    except (SheetLinkError, ServiceAccountError) as e:
        raise HTTPException(400, str(e)) from None
    except SheetsError as e:
        raise _sheets_http(e) from None
    return SheetExportOut(
        url=r.url, title=r.title, tabs=[SheetTabOut(name=n, rows=k) for n, k in r.tabs], at=r.at
    )


@router.post("/import", response_model=ImportedOut | NeedsMappingOut)
def import_sheets(
    body: SheetImportIn, session: Session = Depends(get_session)
) -> ImportedOut | NeedsMappingOut:
    """Holdings from a tab of your sheet (service account) or from a published CSV link.
    Same columns and column mapping as a Groww file; a new snapshot replaces the old one."""
    m = body.mapping
    user = UserMapping(m.header_row, m.columns, m.remember) if m else None
    try:
        if body.source == "tab":
            result = sync.import_from_tab(session, body.kind, body.tab, user)
        else:
            s = sync.get_sheet_settings(session)
            url = _clean(body.url) or (s.stocks_csv_url if body.kind == "stocks" else s.mf_csv_url)
            if not url:
                raise SheetLinkError("Paste the published CSV link for this tab first.")
            result = sync.import_from_csv(session, body.kind, url, user)
    except (SheetLinkError, ServiceAccountError, ImportFileError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    except SheetsError as e:
        raise _sheets_http(e) from None
    if isinstance(result, NeedsMapping):
        return needs_mapping_out(body.kind, result)
    return imported_out(session, result)
