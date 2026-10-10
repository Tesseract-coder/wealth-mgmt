"""NAV history from mfapi.in (a free mirror of AMFI's daily NAVs).

GET https://api.mfapi.in/mf/{code} →
  {"meta": {...}, "data": [{"date": "09-10-2026", "nav": "219.81"}], "status": "SUCCESS"}.
The whole history comes back on every call.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime

from app.data.http import FetchError, get_bytes

BASE_URL = "https://api.mfapi.in/mf"


@dataclass(frozen=True)
class NavHistory:
    code: str
    scheme_name: str | None
    points: list[tuple[date, float]]  # ascending by date


def parse_nav_history(code: str, payload: bytes) -> NavHistory:
    try:
        doc = json.loads(payload)
    except ValueError as e:
        raise FetchError(f"mfapi: response for scheme {code} is not JSON") from e
    if not isinstance(doc, dict) or doc.get("status") != "SUCCESS":
        raise FetchError(f"mfapi: no NAV history for scheme {code}")
    meta = doc.get("meta") or {}
    if str(meta.get("scheme_code", code)) != code:
        raise FetchError(f"mfapi: asked for scheme {code}, got {meta.get('scheme_code')}")
    points: dict[date, float] = {}
    for row in doc.get("data") or []:
        try:
            d = datetime.strptime(str(row["date"]), "%d-%m-%Y").date()
            nav = float(str(row["nav"]).replace(",", ""))
        except (KeyError, ValueError, TypeError):
            continue  # malformed row: skip, never guess
        if nav > 0:
            points[d] = nav
    if not points:
        raise FetchError(f"mfapi: scheme {code} has no usable NAV rows")
    return NavHistory(code, meta.get("scheme_name"), sorted(points.items()))


def fetch_nav_history(code: str) -> NavHistory:
    if not code.isdigit():
        raise FetchError(f"Invalid AMFI scheme code {code!r}")
    return parse_nav_history(code, get_bytes("mfapi", f"{BASE_URL}/{code}"))
