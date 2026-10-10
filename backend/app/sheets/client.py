"""A small Google Sheets API v4 client over the app's shared HTTP client: rate-limited
(data.rate_limits_per_minute.google), retried with backoff, with errors turned into
messages that say what to fix."""

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.profiles import get_profiles
from app.data import http
from app.data.http import RETRY_STATUSES
from app.data.rate_limit import limiter
from app.sheets.auth import TokenSource, token_source

logger = logging.getLogger(__name__)
API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(RuntimeError):
    """A Sheets API call failed; the message is safe to show and says what to do."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def a1(tab: str, cells: str = "") -> str:
    """'My tab' → "'My tab'" (quotes doubled), plus an optional '!A1:B2'."""
    quoted = "'" + tab.replace("'", "''") + "'"
    return f"{quoted}!{cells}" if cells else quoted


@dataclass(frozen=True)
class Tab:
    sheet_id: int
    title: str
    rows: int
    cols: int


@dataclass(frozen=True)
class Spreadsheet:
    id: str
    title: str
    tabs: list[Tab]

    def tab(self, title: str) -> Tab | None:
        want = title.strip().lower()
        return next((t for t in self.tabs if t.title.strip().lower() == want), None)


class SheetsClient:
    def __init__(self, tokens: TokenSource, client: httpx.Client | None = None) -> None:
        self.tokens = tokens
        self._http = client or http.client()

    @property
    def email(self) -> str:
        return self.tokens.email

    def _call(self, method: str, url: str, **kw: Any) -> dict[str, Any]:
        cfg = get_profiles().data
        backoff = cfg.http_backoff_seconds
        last: SheetsError | None = None
        for attempt in range(cfg.http_retries + 1):
            limiter("google").acquire()
            headers = {"Authorization": f"Bearer {self.tokens.token()}"}
            try:
                r = self._http.request(method, url, headers=headers, **kw)
            except httpx.HTTPError as e:
                last = SheetsError(f"Couldn't reach Google Sheets ({e.__class__.__name__})")
            else:
                if r.status_code == 200:
                    return r.json() if r.content else {}
                last = self._error(r)
                if r.status_code not in RETRY_STATUSES:
                    raise last
                if r.status_code == 429:
                    limiter("google").penalise(backoff * 2**attempt)
            if attempt < cfg.http_retries:
                delay = backoff * 2**attempt
                logger.info("Sheets API: %s; retrying in %.1fs", last, delay)
                time.sleep(delay)
        assert last is not None
        raise last

    def _error(self, r: httpx.Response) -> SheetsError:
        try:
            err = r.json().get("error", {})
            msg = str(err.get("message", ""))
            reason = str(err.get("status", ""))
        except ValueError:
            msg, reason = r.text[:200], ""
        low = msg.lower()
        if r.status_code == 403 and ("has not been used" in low or "is disabled" in low):
            text = (
                "The Google Sheets API isn't enabled for the service account's Cloud project. "
                "Enable it (APIs & Services → Library → Google Sheets API), wait a minute, retry."
            )
        elif r.status_code == 403:
            text = (
                f"The service account can't open this sheet. Share the sheet with {self.email} "
                "as an Editor (Share button, top right of the sheet)."
            )
        elif r.status_code == 404:
            text = "Sheet not found. Check the link; it should be the sheet's normal address."
        elif r.status_code == 400 and "unable to parse range" in low:
            text = "That tab doesn't exist in the sheet."
        elif r.status_code == 429:
            text = "Google Sheets rate limit reached; try again in a minute."
        else:
            why = f", {reason}" if reason else ""
            text = f"Google Sheets error (HTTP {r.status_code}{why}): {msg}"
        return SheetsError(text, r.status_code)

    # ------------------------------------------------------------------------ reads

    def spreadsheet(self, sid: str) -> Spreadsheet:
        fields = "properties.title,sheets.properties(sheetId,title,gridProperties)"
        d = self._call("GET", f"{API}/{sid}", params={"fields": fields})
        tabs = [
            Tab(
                int(p["sheetId"]),
                str(p["title"]),
                int(p.get("gridProperties", {}).get("rowCount", 0)),
                int(p.get("gridProperties", {}).get("columnCount", 0)),
            )
            for p in (s["properties"] for s in d.get("sheets", []))
        ]
        return Spreadsheet(sid, str(d.get("properties", {}).get("title", "")), tabs)

    def values(self, sid: str, rng: str) -> list[list[Any]]:
        """Cells as numbers where they are numbers, dates as shown in the sheet."""
        d = self._call(
            "GET",
            f"{API}/{sid}/values/{quote(rng, safe='')}",
            params={
                "valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "FORMATTED_STRING",
            },
        )
        return list(d.get("values", []))

    def batch_values(self, sid: str, ranges: list[str]) -> list[list[list[Any]]]:
        if not ranges:
            return []
        d = self._call(
            "GET",
            f"{API}/{sid}/values:batchGet",
            params=[("ranges", r) for r in ranges] + [("valueRenderOption", "FORMATTED_VALUE")],
        )
        return [list(v.get("values", [])) for v in d.get("valueRanges", [])]

    # ----------------------------------------------------------------------- writes

    def batch_update(self, sid: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not requests:
            return {}
        return self._call("POST", f"{API}/{sid}:batchUpdate", json={"requests": requests})

    def clear(self, sid: str, ranges: list[str]) -> None:
        self._call("POST", f"{API}/{sid}/values:batchClear", json={"ranges": ranges})

    def write(self, sid: str, data: list[tuple[str, list[list[Any]]]]) -> None:
        """RAW input: text is stored as typed, so a cell starting with '=' never runs."""
        self._call(
            "POST",
            f"{API}/{sid}/values:batchUpdate",
            json={
                "valueInputOption": "RAW",
                "data": [{"range": r, "values": v} for r, v in data],
            },
        )


def sheets_client() -> SheetsClient:
    """A client signed in as the service account in secrets/ (raises if there's no key)."""
    c = http.client()
    return SheetsClient(token_source(c), c)
