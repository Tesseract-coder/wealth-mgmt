"""Google Sheets links: which spreadsheet a link points to, and its CSV download address.

Only https://docs.google.com links are accepted, so a pasted link can never make the app
fetch anything else."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

HOST = "docs.google.com"
_ID = r"[A-Za-z0-9_-]{20,}"
_EDIT = re.compile(rf"^/spreadsheets/d/({_ID})(/|$)")
_PUBLISHED = re.compile(rf"^/spreadsheets/d/e/({_ID})/pub(html)?$")
_BARE_ID = re.compile(rf"^{_ID}$")


class SheetLinkError(ValueError):
    """The link can't be used; the message says why and is safe to show."""


@dataclass(frozen=True)
class SheetLink:
    kind: str  # "spreadsheet" (normal link) | "published" (File → Share → Publish to web)
    key: str  # spreadsheet id, or the 2PACX… publish id
    gid: str | None  # tab id from the link, if any

    @property
    def csv_url(self) -> str:
        """Where this tab downloads as CSV without signing in. Works for a published tab, or
        for a normal link when sharing is "Anyone with the link"."""
        q = {"gid": self.gid} if self.gid else {}
        if self.kind == "published":
            q |= {"single": "true", "output": "csv"}
            return f"https://{HOST}/spreadsheets/d/e/{self.key}/pub?{urlencode(q)}"
        return f"https://{HOST}/spreadsheets/d/{self.key}/export?{urlencode({'format': 'csv'} | q)}"


def parse_link(text: str) -> SheetLink:
    raw = text.strip()
    if _BARE_ID.match(raw):
        return SheetLink("spreadsheet", raw, None)
    u = urlsplit(raw)
    if u.scheme != "https" or u.hostname != HOST:
        raise SheetLinkError(
            f"Paste a Google Sheets link starting with https://{HOST}/spreadsheets/"
        )
    q = parse_qs(u.query)
    frag = parse_qs(u.fragment)
    gids = q.get("gid") or frag.get("gid")
    gid = gids[0] if gids else None
    if gid is not None and not gid.isdigit():
        raise SheetLinkError("The link's gid (tab id) should be a number")
    if m := _PUBLISHED.match(u.path):
        return SheetLink("published", m.group(1), gid)
    if m := _EDIT.match(u.path):
        return SheetLink("spreadsheet", m.group(1), gid)
    raise SheetLinkError("This doesn't look like a Google Sheets link (…/spreadsheets/d/…)")


def spreadsheet_id(text: str) -> str:
    """The id the Sheets API needs, from the sheet's normal link (or the id itself)."""
    link = parse_link(text)
    if link.kind == "published":
        raise SheetLinkError(
            "That is a 'Publish to web' link. The service account needs the sheet's normal "
            "link, copied from the address bar (…/spreadsheets/d/<id>/edit)."
        )
    return link.key


def sheet_url(sid: str) -> str:
    return f"https://{HOST}/spreadsheets/d/{sid}/edit"
