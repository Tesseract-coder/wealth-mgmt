"""Google Sheets import/export against an in-memory fake of Google's token endpoint, the
Sheets API v4 and published-CSV links. Nothing reaches the network."""

import base64
import json
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.data import http
from app.export.tables import Table
from app.sheets import auth
from app.sheets.auth import ServiceAccountError, TokenSource, parse_key
from app.sheets.client import SheetsClient, a1
from app.sheets.sync import MARKER, tab_values, write_tables
from app.sheets.urls import SheetLinkError, parse_link, spreadsheet_id

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data"
SID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEF"
PUB = "2PACX-1vQabcdefghijklmnopqrstuvwxyz0123456789"
EMAIL = "portfolio-bot@my-project.iam.gserviceaccount.com"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SID}/edit#gid=0"


@pytest.fixture(scope="module")
def key_info() -> dict[str, Any]:
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = pk.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": "my-project",
        "private_key_id": "abc123",
        "private_key": pem,
        "client_email": EMAIL,
        "client_id": "1",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


# ------------------------------------------------------------------------------ fake Google


def _tab_name(rng: str) -> str:
    if rng.startswith("'"):
        end = rng.index("'", 1)
        while rng[end : end + 2] == "''":
            end = rng.index("'", end + 2)
        return rng[1:end].replace("''", "'")
    return rng.split("!")[0]


class FakeGoogle:
    def __init__(self) -> None:
        self.title = "My portfolio"
        self.tabs: list[dict[str, Any]] = [
            {"id": 0, "title": "Notes", "rows": 1000, "cols": 26, "values": [["my own notes"]]}
        ]
        self.shared = True
        self.writable = True
        self.api_disabled = False
        self.tokens_issued = 0
        self.value_input: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.csv: tuple[int, str, bytes] = (200, "text/csv", b"")
        self.calls: list[str] = []

    def tab(self, title: str) -> dict[str, Any] | None:
        return next((t for t in self.tabs if t["title"].lower() == title.lower()), None)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        u = req.url
        self.calls.append(f"{req.method} {u.host}{u.path}")
        if u.host == "oauth2.googleapis.com":
            form = parse_qs(req.content.decode())
            assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
            payload = form["assertion"][0].split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            assert claims["iss"] == EMAIL and claims["scope"].endswith("/auth/spreadsheets")
            self.tokens_issued += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{self.tokens_issued}", "expires_in": 3600}
            )
        if u.host == "docs.google.com":
            status, ctype, body = self.csv
            return httpx.Response(status, content=body, headers={"content-type": ctype})
        assert u.host == "sheets.googleapis.com"
        assert req.headers["authorization"].startswith("Bearer tok-")
        if self.api_disabled:
            return self._err(403, "Google Sheets API has not been used in project 1 before")
        path = u.path.removeprefix("/v4/spreadsheets/")
        if not path.startswith(SID):
            return self._err(404, "Requested entity was not found.")
        if not self.shared:
            return self._err(403, "The caller does not have permission")
        rest = path[len(SID) :]
        q = parse_qs(u.query.decode())
        body = json.loads(req.content) if req.content else {}
        if rest == "" and req.method == "GET":
            return httpx.Response(200, json=self._meta())
        if rest.startswith("/values/") and req.method == "GET":
            t = self.tab(_tab_name(rest.removeprefix("/values/")))
            if t is None:
                return self._err(400, f"Unable to parse range: {rest}")
            return httpx.Response(200, json={"values": t["values"]})
        if rest == "/values:batchGet":
            out = []
            for r in q["ranges"]:
                t = self.tab(_tab_name(r))
                assert t is not None
                out.append({"values": [row[:3] for row in t["values"][:3]]})
            return httpx.Response(200, json={"valueRanges": out})
        if not self.writable:
            return self._err(403, "The caller does not have permission")
        if rest == "/values:batchClear":
            for r in body["ranges"]:
                self.tab(_tab_name(r))["values"] = []  # type: ignore[index]
            return httpx.Response(200, json={})
        if rest == "/values:batchUpdate":
            self.value_input.append(body["valueInputOption"])
            for d in body["data"]:
                self.tab(_tab_name(d["range"]))["values"] = d["values"]  # type: ignore[index]
            return httpx.Response(200, json={})
        if rest == ":batchUpdate":
            self.requests += body["requests"]
            for r in body["requests"]:
                if "addSheet" in r:
                    p = r["addSheet"]["properties"]
                    g = p["gridProperties"]
                    self.tabs.append(
                        {
                            "id": 100 + len(self.tabs),
                            "title": p["title"],
                            "rows": g["rowCount"],
                            "cols": g["columnCount"],
                            "values": [],
                        }
                    )
                elif "updateSheetProperties" in r:
                    p = r["updateSheetProperties"]["properties"]
                    t = next(x for x in self.tabs if x["id"] == p["sheetId"])
                    g = p["gridProperties"]
                    t["rows"] = g.get("rowCount", t["rows"])
                    t["cols"] = g.get("columnCount", t["cols"])
            return httpx.Response(200, json={"replies": []})
        raise AssertionError(f"unexpected call {req.method} {u}")

    def _meta(self) -> dict[str, Any]:
        return {
            "properties": {"title": self.title},
            "sheets": [
                {
                    "properties": {
                        "sheetId": t["id"],
                        "title": t["title"],
                        "gridProperties": {"rowCount": t["rows"], "columnCount": t["cols"]},
                    }
                }
                for t in self.tabs
            ],
        }

    @staticmethod
    def _err(code: int, msg: str) -> httpx.Response:
        return httpx.Response(code, json={"error": {"code": code, "message": msg}})


@pytest.fixture
def google(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key_info: dict[str, Any]
) -> Iterator[FakeGoogle]:
    """A fake Google, a key file in place and a sheet link saved."""
    fake = FakeGoogle()
    key = tmp_path / "secrets" / "sa.json"
    key.parent.mkdir()
    key.write_text(json.dumps(key_info))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key))
    get_settings.cache_clear()
    auth.reset_tokens()
    http.set_client(httpx.Client(transport=httpx.MockTransport(fake)))
    r = client.put("/sheets/settings", json={"sheet_url": SHEET_URL})
    assert r.status_code == 200, r.text
    yield fake
    auth.reset_tokens()


def upload_stocks(client: TestClient) -> None:
    with open(SAMPLES / "groww_stocks_messy.csv", "rb") as f:
        r = client.post("/import/groww-stocks", files={"file": ("s.csv", f)})
    assert r.status_code == 200, r.text


def grid(text: str) -> list[list[Any]]:
    return [line.split(",") for line in text.strip().splitlines()]


STOCK_TAB = grid(
    """
Company,ISIN Code,Qty.,Avg. Cost,LTP
Reliance Industries Ltd,INE002A01018,25,2410.5,2875.1
Infosys Ltd,INE009A01021,30,1402.8,1530.45
"""
)


# ------------------------------------------------------------------------------------ links


def test_parse_links() -> None:
    edit = parse_link(f"https://docs.google.com/spreadsheets/d/{SID}/edit?usp=sharing#gid=123")
    assert (edit.kind, edit.key, edit.gid) == ("spreadsheet", SID, "123")
    assert edit.csv_url == (
        f"https://docs.google.com/spreadsheets/d/{SID}/export?format=csv&gid=123"
    )
    pub = parse_link(f"https://docs.google.com/spreadsheets/d/e/{PUB}/pubhtml?gid=7")
    assert pub.kind == "published"
    assert pub.csv_url == (
        f"https://docs.google.com/spreadsheets/d/e/{PUB}/pub?gid=7&single=true&output=csv"
    )
    assert parse_link(SID).key == SID
    assert spreadsheet_id(SHEET_URL) == SID


@pytest.mark.parametrize(
    "bad",
    [
        f"http://docs.google.com/spreadsheets/d/{SID}/edit",  # not https
        f"https://docs.google.com.evil.example/spreadsheets/d/{SID}/edit",
        f"https://evil.example/?u=https://docs.google.com/spreadsheets/d/{SID}",
        "https://docs.google.com/document/d/abc/edit",
        f"https://docs.google.com/spreadsheets/d/{SID}/edit#gid=abc",
        "file:///etc/passwd",
    ],
)
def test_rejects_other_links(bad: str) -> None:
    with pytest.raises(SheetLinkError):
        parse_link(bad)


def test_published_link_cannot_be_used_by_service_account() -> None:
    with pytest.raises(SheetLinkError, match="normal"):
        spreadsheet_id(f"https://docs.google.com/spreadsheets/d/e/{PUB}/pub?output=csv")


# ------------------------------------------------------------------------------- key + token


def test_parse_key_validation(key_info: dict[str, Any]) -> None:
    assert parse_key(json.dumps(key_info).encode())["client_email"] == EMAIL
    with pytest.raises(ServiceAccountError, match="valid JSON"):
        parse_key(b"not json")
    with pytest.raises(ServiceAccountError, match="service_account"):
        parse_key(json.dumps({**key_info, "type": "authorized_user"}).encode())
    with pytest.raises(ServiceAccountError, match="client_email"):
        parse_key(json.dumps({**key_info, "client_email": ""}).encode())
    with pytest.raises(ServiceAccountError, match="googleapis.com"):
        parse_key(json.dumps({**key_info, "token_uri": "https://evil.example/token"}).encode())
    with pytest.raises(ServiceAccountError, match="private_key"):
        parse_key(json.dumps({**key_info, "private_key": "garbage"}).encode())


def test_token_is_cached_until_expiry(key_info: dict[str, Any]) -> None:
    fake = FakeGoogle()
    now = [1_000_000.0]
    src = TokenSource(key_info, httpx.Client(transport=httpx.MockTransport(fake)), lambda: now[0])
    assert src.token() == "tok-1"
    now[0] += 3000
    assert src.token() == "tok-1"
    now[0] += 600  # within a minute of expiry
    assert src.token() == "tok-2"


def test_token_refused(key_info: dict[str, Any]) -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "bad"})

    src = TokenSource(key_info, httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(ServiceAccountError, match="refused.*invalid_grant|refused.*bad"):
        src.token()


def test_upload_key_stores_it_privately(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key_info: dict[str, Any]
) -> None:
    dest = tmp_path / "secrets" / "service-account.json"
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(dest))
    get_settings.cache_clear()
    bad = client.post("/sheets/service-account", files={"file": ("k.json", b"{}")})
    assert bad.status_code == 400 and not dest.exists()

    raw = json.dumps(key_info).encode()
    r = client.post("/sheets/service-account", files={"file": ("k.json", raw)})
    assert r.status_code == 200, r.text
    assert r.json()["client_email"] == EMAIL and r.json()["configured"]
    assert "PRIVATE KEY" not in r.text
    assert dest.read_bytes() == raw
    assert stat.S_IMODE(os.stat(dest).st_mode) == 0o600
    status = client.get("/sheets/status")
    assert "PRIVATE KEY" not in status.text and status.json()["service_account"]["configured"]


# ------------------------------------------------------------------------------------ export


def test_export_writes_four_tabs(client: TestClient, google: FakeGoogle) -> None:
    upload_stocks(client)
    r = client.post("/sheets/export", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "My portfolio" and body["url"].endswith(f"/d/{SID}/edit")
    tabs = {t["name"]: t["rows"] for t in body["tabs"]}
    assert tabs == {
        "Summary": tabs["Summary"],
        "Analysis_Stocks": 7,
        "Analysis_MF": 0,
        "Screener": 0,
    }

    disclaimer = client.get("/meta").json()["disclaimer"]
    for name in tabs:
        v = google.tab(name)["values"]  # type: ignore[index]
        assert v[0][0].startswith(f"{MARKER} · ") and v[0][1].startswith("Updated ")
        assert v[0][1].endswith("IST")
        assert v[1] == [disclaimer]
    stocks = google.tab("Analysis_Stocks")["values"]  # type: ignore[index]
    assert stocks[3][:3] == ["Ticker", "Name", "Sector"]
    assert len(stocks) == 4 + 7  # 8 imported; the unmatched one has no ticker to score
    assert google.tab("Analysis_MF")["values"][4] == ["No mutual fund holdings imported yet."]  # type: ignore[index]
    assert "Run a scan first" in google.tab("Screener")["values"][4][0]  # type: ignore[index]
    summary = {row[0]: row for row in google.tab("Summary")["values"][4:]}  # type: ignore[index]
    assert "Portfolio value" in summary and "Stock signals" in summary
    # Your own tab is untouched; values go in RAW so text never runs as a formula.
    assert google.tab("Notes")["values"] == [["my own notes"]]  # type: ignore[index]
    assert google.value_input == ["RAW"]
    frozen = [
        r
        for r in google.requests
        if "updateSheetProperties" in r and "frozenRowCount" in r["updateSheetProperties"]["fields"]
    ]
    assert len(frozen) == 4
    patterns = {
        r["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"]
        for r in google.requests
        if "numberFormat" in json.dumps(r)
    }
    assert patterns == {r"[>=10000000]##\,##\,##\,##0.00;[>=100000]##\,##\,##0.00;##,##0.00"}

    hist = client.get("/sheets/status").json()["history"]
    assert hist[0]["direction"] == "export" and hist[0]["ok"]

    # A second export finds its own tabs and rewrites them without asking.
    assert client.post("/sheets/export", json={}).status_code == 200
    assert sum(1 for t in google.tabs if t["title"] == "Summary") == 1


def test_export_asks_before_overwriting_your_tab(client: TestClient, google: FakeGoogle) -> None:
    google.tabs.append(
        {"id": 5, "title": "summary", "rows": 10, "cols": 3, "values": [["My budget", 100]]}
    )
    r = client.post("/sheets/export", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["tabs"] == ["Summary"]
    assert google.tab("summary")["values"] == [["My budget", 100]]  # type: ignore[index]
    assert google.value_input == []  # nothing written anywhere

    r = client.post("/sheets/export", json={"overwrite": ["Summary"]})
    assert r.status_code == 200, r.text
    t = google.tab("summary")
    assert t is not None and t["values"][0][0].startswith(MARKER)
    assert t["rows"] >= len(t["values"])  # the small tab was enlarged first


def test_export_errors_say_what_to_fix(client: TestClient, google: FakeGoogle) -> None:
    google.writable = False
    r = client.post("/sheets/export", json={})
    assert r.status_code == 400 and EMAIL in r.json()["detail"] and "Editor" in r.json()["detail"]
    google.api_disabled = True
    assert "Enable it" in client.post("/sheets/export", json={}).json()["detail"]
    client.put("/sheets/settings", json={"sheet_url": None})
    assert "link" in client.post("/sheets/export", json={}).json()["detail"]
    assert client.get("/sheets/status").json()["history"][0]["ok"] is False


def test_write_tables_inr_cells_and_text_kept_as_text(key_info: dict[str, Any]) -> None:
    fake = FakeGoogle()
    c = httpx.Client(transport=httpx.MockTransport(fake))
    sheets = SheetsClient(TokenSource(key_info, c), c)
    t = Table("x", "X", "ctx", ["Name", "Value"], [['=IMPORTXML("x")', 1234567.5]], inr_columns=[1])
    s = Table("summary", "S", "ctx", ["Item", "Value", "Note"], [["Updated", "now", None], ["Value", 5e5, None]], inr_rows=[1])  # fmt: skip
    from app.export.tables import ExportTables

    write_tables(sheets, SID, ExportTables(t, t, t, s))
    stocks = fake.tab("Analysis_Stocks")["values"]  # type: ignore[index]
    assert stocks[4] == ['=IMPORTXML("x")', 1234567.5]
    ranges = [r["repeatCell"]["range"] for r in fake.requests if "numberFormat" in json.dumps(r)]
    summary_id = fake.tab("Summary")["id"]  # type: ignore[index]
    assert {"sheetId": summary_id, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 1, "endColumnIndex": 2} in ranges  # fmt: skip
    vals = tab_values(s, "now", "D")
    assert vals[4] == ["Updated", "now", ""]


def test_a1_quotes_tab_names() -> None:
    assert a1("Bob's tab", "A1") == "'Bob''s tab'!A1"


# ------------------------------------------------------------------------------------ import


def test_import_from_tab(client: TestClient, google: FakeGoogle) -> None:
    google.tabs.append(
        {"id": 9, "title": "Holdings_Stocks", "rows": 100, "cols": 5, "values": STOCK_TAB}
    )
    r = client.post("/sheets/import", json={"kind": "stocks", "source": "tab"})
    assert r.status_code == 200, r.text
    assert r.json()["snapshot"]["row_count"] == 2
    assert r.json()["snapshot"]["source"] == "gsheet"
    syms = {s["symbol"] for s in client.get("/portfolio/holdings").json()["stocks"]}
    assert syms == {"RELIANCE", "INFY"}

    missing = client.post("/sheets/import", json={"kind": "mf", "source": "tab"})
    assert missing.status_code == 400
    assert "No tab named 'Holdings_MF'" in missing.json()["detail"]
    assert "Holdings_Stocks" in missing.json()["detail"]


def test_import_from_tab_needs_mapping(client: TestClient, google: FakeGoogle) -> None:
    odd = [["Thing", "How many", "Paid each", "Code"], ["Infosys Ltd", 30, 1402.8, "INE009A01021"]]
    google.tabs.append({"id": 9, "title": "Mine", "rows": 10, "cols": 4, "values": odd})
    r = client.post("/sheets/import", json={"kind": "stocks", "source": "tab", "tab": "Mine"})
    assert r.status_code == 200 and r.json()["status"] == "needs_mapping"
    mapping = {"header_row": 0, "columns": {"name": 0, "quantity": 1, "avg_price": 2, "isin": 3}, "remember": False}  # fmt: skip
    r = client.post(
        "/sheets/import",
        json={"kind": "stocks", "source": "tab", "tab": "Mine", "mapping": mapping},
    )
    assert r.json()["status"] == "imported" and r.json()["snapshot"]["row_count"] == 1


def test_import_from_published_csv(client: TestClient, google: FakeGoogle) -> None:
    google.csv = (200, "text/csv", (SAMPLES / "groww_stocks_messy.csv").read_bytes())
    url = f"https://docs.google.com/spreadsheets/d/e/{PUB}/pub?gid=0&single=true&output=csv"
    client.put("/sheets/settings", json={"sheet_url": SHEET_URL, "stocks_csv_url": url})
    r = client.post("/sheets/import", json={"kind": "stocks", "source": "csv"})
    assert r.status_code == 200, r.text
    assert r.json()["snapshot"]["row_count"] == 8
    assert r.json()["snapshot"]["source"] == "gsheet_csv"
    assert f"docs.google.com/spreadsheets/d/e/{PUB}/pub" in google.calls[-1]


def test_unpublished_csv_link_explains(client: TestClient, google: FakeGoogle) -> None:
    google.csv = (200, "text/html", b"<!DOCTYPE html><html>Sign in</html>")
    r = client.post("/sheets/import", json={"kind": "mf", "source": "csv", "url": SHEET_URL})
    assert r.status_code == 400 and "Publish" in r.json()["detail"]
    r = client.post(
        "/sheets/import",
        json={"kind": "mf", "source": "csv", "url": "https://example.com/x.csv"},
    )
    assert r.status_code == 400 and "docs.google.com" in r.json()["detail"]
    assert all("example.com" not in c for c in google.calls)


def test_import_refuses_huge_tabs(
    client: TestClient, google: FakeGoogle, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.profiles import get_profiles

    monkeypatch.setattr(get_profiles().sheets, "max_import_rows", 2)
    google.tabs.append(
        {"id": 9, "title": "Holdings_Stocks", "rows": 100, "cols": 5, "values": STOCK_TAB}
    )
    r = client.post("/sheets/import", json={"kind": "stocks", "source": "tab"})
    assert r.status_code == 400 and "limit is 2" in r.json()["detail"]


# --------------------------------------------------------------------------- settings + test


def test_settings_validation_and_defaults(client: TestClient, google: FakeGoogle) -> None:
    bad = client.put("/sheets/settings", json={"sheet_url": "https://example.com/sheet"})
    assert bad.status_code == 422 and "Sheet link" in bad.json()["detail"]
    r = client.put(
        "/sheets/settings",
        json={
            "sheet_url": SHEET_URL,
            "stocks_tab": " Holdings_Stocks ",
            "mf_tab": "My funds",
            "screener_screen": "preset:growth",
            "auto_export": True,
        },
    ).json()
    assert r["settings"]["stocks_tab"] == "Holdings_Stocks"
    assert r["settings"]["mf_tab"] == "My funds"
    assert r["settings"]["auto_export"] is True
    assert r["spreadsheet_url"].endswith(f"/d/{SID}/edit")
    assert client.get("/settings/profile").json()["gsheet_url"] == SHEET_URL
    assert client.put("/sheets/settings", json={"screener_screen": "x"}).status_code == 422


def test_connection_test(client: TestClient, google: FakeGoogle) -> None:
    google.tabs.append(
        {"id": 9, "title": "Holdings_Stocks", "rows": 100, "cols": 5, "values": STOCK_TAB}
    )
    r = client.post("/sheets/test").json()
    checks = {c["name"]: c for c in r["checks"]}
    assert r["ok"] is True
    assert checks["Service-account key"]["detail"].startswith(EMAIL)
    assert checks["Open the sheet"]["detail"].startswith("'My portfolio'")
    assert checks["Write access"]["ok"] is True
    assert checks["Import tab (stocks)"]["ok"] is True
    assert checks["Import tab (mutual funds)"]["ok"] is None
    assert checks["Export tabs"]["ok"] is True
    assert google.title == "My portfolio"  # the write check changed nothing
    assert google.tab("Notes")["values"] == [["my own notes"]]  # type: ignore[index]

    google.shared = False
    r = client.post("/sheets/test").json()
    failed = [c for c in r["checks"] if c["ok"] is False]
    assert r["ok"] is False and failed[0]["name"] == "Open the sheet"
    assert EMAIL in failed[0]["detail"]


def test_connection_test_without_key(
    client: TestClient, google: FakeGoogle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "nope.json"))
    get_settings.cache_clear()
    google.csv = (200, "text/csv", b"Scheme Name,Units,Invested,Current Value\nX Fund,10,100,120\n")
    url = f"https://docs.google.com/spreadsheets/d/e/{PUB}/pub?output=csv"
    client.put("/sheets/settings", json={"sheet_url": None, "mf_csv_url": url})
    r = client.post("/sheets/test").json()
    checks = {c["name"]: c for c in r["checks"]}
    assert checks["Service-account key"]["ok"] is None
    assert checks["Published link (mutual funds)"]["ok"] is True
    assert "2 rows" in checks["Published link (mutual funds)"]["detail"]
    assert r["ok"] is True
    assert not any(c.startswith("POST oauth2") for c in google.calls)


def test_scheduled_step_exports_only_when_on(client: TestClient, google: FakeGoogle) -> None:
    from sqlmodel import Session

    from app.core.db import get_engine
    from app.jobs.tasks import sheets_step

    with Session(get_engine()) as s:
        assert sheets_step(s).outcome == "skipped"
    client.put("/sheets/settings", json={"sheet_url": SHEET_URL, "auto_export": True})
    with Session(get_engine()) as s:
        res = sheets_step(s)
    assert res.outcome == "updated", res.message
    assert google.tab("Summary") is not None
