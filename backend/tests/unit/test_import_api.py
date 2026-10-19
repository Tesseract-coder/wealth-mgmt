"""Importer behaviour through the HTTP API, using the FAKE files in sample_data/."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from casparser.exceptions import IncorrectPasswordError
from casparser.types import CASData
from fastapi.testclient import TestClient

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data"


def upload(client: TestClient, url: str, name: str, **form: str) -> Any:
    with open(SAMPLES / name, "rb") as f:
        return client.post(url, files={"file": (name, f)}, data=form)


# --------------------------------------------------------------------------- stocks


def test_groww_stocks_xlsx(client: TestClient) -> None:
    r = upload(client, "/import/groww-stocks", "groww_stocks_holdings.xlsx")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["snapshot"]["row_count"] == 11
    assert body["unresolved"] == 0
    assert body["snapshot"]["created_at"].endswith("+05:30")

    h = client.get("/portfolio/holdings").json()
    by_sym = {s["symbol"]: s for s in h["stocks"]}
    assert by_sym["RELIANCE"]["quantity"] == 25
    assert by_sym["RELIANCE"]["invested"] == pytest.approx(25 * 2410.50)
    assert by_sym["NIFTYBEES"]["resolution"] == "isin"


def test_messy_csv(client: TestClient) -> None:
    body = upload(client, "/import/groww-stocks", "groww_stocks_messy.csv").json()
    assert body["status"] == "imported"
    assert body["snapshot"]["row_count"] == 8
    assert body["unresolved"] == 1
    reasons = {s["reason"] for s in body["skipped"]}
    assert reasons == {"Quantity is zero", "Total row", "No quantity (not a holding row)"}
    assert any("Combined two rows for HDFC Bank" in w for w in body["warnings"])

    stocks = {s["name"]: s for s in client.get("/portfolio/holdings").json()["stocks"]}
    hdfc = stocks["HDFC Bank Ltd"]
    assert hdfc["quantity"] == 45
    assert hdfc["avg_price"] == pytest.approx((40 * 1495.25 + 5 * 1520) / 45, rel=1e-4)
    assert stocks["Bajaj Finance Limited"]["symbol"] == "BAJFINANCE"
    assert stocks["Bajaj Finance Limited"]["resolution"] == "name"
    assert stocks["Acme Widgets Ltd"]["symbol"] is None
    # Parenthesised negative P&L parsed correctly (TCS is at a loss in the fake data)
    assert stocks["Tata Consultancy Services Ltd"]["unrealised_pnl"] < 0


def test_unknown_headers_need_mapping_then_remembered(client: TestClient) -> None:
    first = upload(client, "/import/groww-stocks", "groww_stocks_unknown_headers.csv").json()
    assert first["status"] == "needs_mapping"
    assert first["header_row"] == 1
    assert first["headers"] == ["Security", "Identifier", "Holding", "Rate", "Mkt"]
    assert set(first["missing_required"]) == {"name", "quantity", "avg_price"}
    assert len(first["preview"]) == 4
    assert {f["key"] for f in first["fields"]} >= {"name", "quantity", "avg_price"}

    mapping = {
        "header_row": 1,
        "columns": {"name": 0, "isin": 1, "quantity": 2, "avg_price": 3, "close_price": 4},
    }
    second = upload(
        client,
        "/import/groww-stocks",
        "groww_stocks_unknown_headers.csv",
        mapping=json.dumps(mapping),
    ).json()
    assert second["status"] == "imported"
    assert second["snapshot"]["row_count"] == 4

    # Same headers again: the saved mapping is used without asking.
    third = upload(client, "/import/groww-stocks", "groww_stocks_unknown_headers.csv").json()
    assert third["status"] == "imported"


def test_bad_mapping_json_rejected(client: TestClient) -> None:
    r = upload(
        client, "/import/groww-stocks", "groww_stocks_unknown_headers.csv", mapping="{not json"
    )
    assert r.status_code == 422


def test_incomplete_manual_mapping_asks_again(client: TestClient) -> None:
    mapping = {"header_row": 1, "columns": {"name": 0}}
    body = upload(
        client,
        "/import/groww-stocks",
        "groww_stocks_unknown_headers.csv",
        mapping=json.dumps(mapping),
    ).json()
    assert body["status"] == "needs_mapping"
    assert set(body["missing_required"]) == {"quantity", "avg_price"}


def test_ticker_fix_and_override_applied_on_reimport(client: TestClient) -> None:
    upload(client, "/import/groww-stocks", "groww_stocks_messy.csv")
    acme = next(
        s
        for s in client.get("/portfolio/holdings").json()["stocks"]
        if s["name"] == "Acme Widgets Ltd"
    )

    bad = client.patch(f"/portfolio/stocks/{acme['id']}/ticker", json={"symbol": "NOPE123"})
    assert bad.status_code == 422

    ok = client.patch(f"/portfolio/stocks/{acme['id']}/ticker", json={"symbol": "itc.ns"})
    assert ok.status_code == 200
    assert ok.json()["symbol"] == "ITC" and ok.json()["resolution"] == "manual"

    body = upload(client, "/import/groww-stocks", "groww_stocks_messy.csv").json()
    assert body["unresolved"] == 0
    acme2 = next(
        s
        for s in client.get("/portfolio/holdings").json()["stocks"]
        if s["name"] == "Acme Widgets Ltd"
    )
    assert (acme2["symbol"], acme2["resolution"]) == ("ITC", "override")


def test_bse_ticker_accepted_without_nse_check(client: TestClient) -> None:
    upload(client, "/import/groww-stocks", "groww_stocks_messy.csv")
    acme = next(
        s
        for s in client.get("/portfolio/holdings").json()["stocks"]
        if s["name"] == "Acme Widgets Ltd"
    )
    r = client.patch(
        f"/portfolio/stocks/{acme['id']}/ticker",
        json={"symbol": "ACMEW", "exchange": "BSE", "remember": False},
    )
    assert r.status_code == 200 and r.json()["exchange"] == "BSE"


def test_rejects_unsupported_and_empty_files(client: TestClient) -> None:
    r = client.post("/import/groww-stocks", files={"file": ("h.xls", b"x")})
    assert r.status_code == 400 and "Save As" in r.json()["detail"]
    r = client.post("/import/groww-stocks", files={"file": ("h.csv", b"")})
    assert r.status_code == 400


def test_file_with_no_holdings(client: TestClient) -> None:
    content = b"Stock Name,Quantity,Average buy price\nTotal,,\n"
    r = client.post("/import/groww-stocks", files={"file": ("h.csv", content)})
    assert r.status_code == 400
    assert "No holdings" in r.json()["detail"]


def test_upload_size_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.profiles import get_profiles

    monkeypatch.setattr(get_profiles().importing, "max_upload_mb", 0.0001)
    r = client.post("/import/groww-stocks", files={"file": ("h.csv", b"x" * 1000)})
    assert r.status_code == 413


def test_kite_stocks_xlsx(client: TestClient) -> None:
    # Kite: symbol only (no name column), table at B23, and three sheets including a Combined one
    # that also lists mutual funds; the Equity sheet must be the one used.
    r = upload(client, "/import/groww-stocks", "kite_holdings.xlsx")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["snapshot"]["row_count"] == 3
    stocks = {s["symbol"]: s for s in client.get("/portfolio/holdings").json()["stocks"]}
    assert set(stocks) == {"RELIANCE", "TCS", "ITC"}
    assert stocks["RELIANCE"]["name"] == "RELIANCE"
    assert stocks["RELIANCE"]["quantity"] == 25
    assert stocks["RELIANCE"]["invested"] == pytest.approx(25 * 2410.50)
    assert stocks["RELIANCE"]["close_price"] == pytest.approx(2875.10)


def test_kite_mf_xlsx(client: TestClient) -> None:
    body = upload(client, "/import/groww-mf", "kite_holdings.xlsx").json()
    assert body["status"] == "imported"
    assert body["snapshot"]["row_count"] == 1
    (fund,) = client.get("/portfolio/holdings").json()["mf"]
    assert fund["amfi_code"] == "122639"
    assert fund["units"] == pytest.approx(812.345)
    assert fund["invested"] == pytest.approx(812.345 * 67.70, abs=0.01)


# --------------------------------------------------------------------------- mutual funds


def test_groww_mf_xlsx(client: TestClient) -> None:
    body = upload(client, "/import/groww-mf", "groww_mf_holdings.xlsx").json()
    assert body["status"] == "imported"
    assert body["snapshot"]["row_count"] == 5
    assert body["unresolved"] == 0
    funds = {f["scheme_name"]: f for f in client.get("/portfolio/holdings").json()["mf"]}
    ppfas = funds["Parag Parikh Flexi Cap Fund Direct Growth"]
    assert (ppfas["amfi_code"], ppfas["plan"], ppfas["option"]) == ("122639", "direct", "growth")
    assert ppfas["category"] == "Equity Scheme - Flexi Cap Fund"
    assert funds["Mirae Asset Large Cap Fund Regular Growth"]["plan"] == "regular"


def test_mf_messy_and_scheme_fix(client: TestClient) -> None:
    body = upload(client, "/import/groww-mf", "groww_mf_messy.csv").json()
    assert body["snapshot"]["row_count"] == 4
    assert body["unresolved"] == 3
    funds = {f["scheme_name"]: f for f in client.get("/portfolio/holdings").json()["mf"]}
    renamed = funds["HDFC Mid-Cap Opportunities Fund Direct Growth"]
    assert renamed["suggestions"][0]["amfi_code"] == "118989"

    r = client.patch(f"/portfolio/mf/{renamed['id']}/scheme", json={"amfi_code": "118989"})
    assert r.status_code == 200
    assert r.json()["plan"] == "direct" and r.json()["nav"] is not None
    assert (
        client.patch(
            f"/portfolio/mf/{renamed['id']}/scheme", json={"amfi_code": "999999999"}
        ).status_code
        == 422
    )

    again = upload(client, "/import/groww-mf", "groww_mf_messy.csv").json()
    assert again["unresolved"] == 2


def test_manual_mf_add_carry_forward_and_remove(client: TestClient) -> None:
    upload(client, "/import/groww-mf", "groww_mf_holdings.xlsx")
    r = client.post("/import/mf-manual", json={"scheme": "118989", "units": 10, "invested": 2000})
    assert r.status_code == 200
    assert r.json()["snapshot"]["row_count"] == 6
    mf = client.get("/portfolio/holdings").json()["mf"]
    added = next(f for f in mf if f["origin"] == "manual")
    assert added["amfi_code"] == "118989"
    assert added["current_value"] == pytest.approx(10 * added["nav"], rel=1e-3)

    # A fresh Groww import keeps the manual fund.
    body = upload(client, "/import/groww-mf", "groww_mf_holdings.xlsx").json()
    assert body["snapshot"]["row_count"] == 6
    assert any("Kept 1 manually added" in w for w in body["warnings"])

    mf = client.get("/portfolio/holdings").json()["mf"]
    manual_row = next(f for f in mf if f["origin"] == "manual")
    imported_row = next(f for f in mf if f["origin"] == "import")
    assert client.delete(f"/portfolio/mf/{imported_row['id']}").status_code == 409
    gone = client.delete(f"/portfolio/mf/{manual_row['id']}")
    assert gone.status_code == 200 and gone.json()["snapshot"]["row_count"] == 5


def test_manual_mf_by_name_unresolved_is_kept(client: TestClient) -> None:
    r = client.post(
        "/import/mf-manual",
        json={"scheme": "Imaginary Fund Direct Growth", "units": 1, "invested": 10},
    )
    assert r.status_code == 200 and r.json()["unresolved"] == 1


def test_snapshots_listed_newest_first(client: TestClient) -> None:
    upload(client, "/import/groww-stocks", "groww_stocks_holdings.xlsx")
    upload(client, "/import/groww-mf", "groww_mf_holdings.xlsx")
    snaps = client.get("/portfolio/snapshots").json()
    assert [s["kind"] for s in snaps] == ["mf", "stocks"]


def test_clear_holdings_by_kind(client: TestClient) -> None:
    upload(client, "/import/groww-stocks", "groww_stocks_holdings.xlsx")
    upload(client, "/import/groww-mf", "groww_mf_holdings.xlsx")
    client.post("/import/mf-manual", json={"scheme": "118989", "units": 10, "invested": 2000})

    r = client.delete("/portfolio/mf")
    assert r.status_code == 200, r.text
    assert r.json() == {"kind": "mf", "snapshots": 2, "holdings": 11}
    h = client.get("/portfolio/holdings").json()
    assert h["mf"] == [] and h["mf_snapshot"] is None
    assert len(h["stocks"]) == 11
    assert [s["kind"] for s in client.get("/portfolio/snapshots").json()] == ["stocks"]

    assert client.delete("/portfolio/stocks").json()["holdings"] == 11
    assert client.get("/portfolio/holdings").json()["stocks"] == []
    assert client.delete("/portfolio/stocks").json()["snapshots"] == 0
    assert client.delete("/portfolio/bonds").status_code == 422


# --------------------------------------------------------------------------- CAS


def fake_cas() -> CASData:
    """What casparser returns for a CAMS detailed statement (built by hand, no real PDF)."""
    return CASData.model_validate(
        {
            "statement_period": {"from": "01-Jan-2024", "to": "08-Oct-2026"},
            "investor_info": {
                "name": "Demo",
                "email": "d@example.com",
                "address": "-",
                "mobile": "0",
            },
            "cas_type": "DETAILED",
            "file_type": "CAMS",
            "parse_warnings": ["Scheme X: unit balance mismatch"],
            "folios": [
                {
                    "folio": "12345678/90",
                    "amc": "PPFAS Mutual Fund",
                    "schemes": [
                        {
                            "scheme": "Parag Parikh Flexi Cap Fund - Direct Plan Growth",
                            "rta_code": "PP001",
                            "rta": "CAMS",
                            "isin": "INF879O01027",
                            "amfi": "122639",
                            "open": Decimal(0),
                            "close": Decimal("100.5"),
                            "close_calculated": Decimal("100.5"),
                            "valuation": {
                                "date": date(2026, 10, 8),
                                "nav": Decimal("87.6555"),
                                "value": Decimal("8809.38"),
                                "cost": Decimal("7000"),
                            },
                            "transactions": [
                                {
                                    "date": date(2024, 3, 5),
                                    "description": "SIP",
                                    "amount": Decimal(3500),
                                    "units": Decimal("60"),
                                    "nav": Decimal("58.3"),
                                    "type": "PURCHASE_SIP",
                                },
                                {
                                    "date": date(2025, 3, 5),
                                    "description": "SIP",
                                    "amount": Decimal(3500),
                                    "units": Decimal("40.5"),
                                    "nav": Decimal("86.4"),
                                    "type": "PURCHASE_SIP",
                                },
                                {
                                    "date": date(2025, 3, 5),
                                    "description": "Stamp",
                                    "amount": Decimal("0.18"),
                                    "type": "STAMP_DUTY_TAX",
                                },
                            ],
                        },
                        {
                            "scheme": "Some Redeemed Fund - Direct Growth",
                            "rta_code": "PP002",
                            "rta": "CAMS",
                            "open": Decimal(5),
                            "close": Decimal(0),
                            "close_calculated": Decimal(0),
                            "valuation": {
                                "date": date(2026, 10, 8),
                                "nav": Decimal(10),
                                "value": Decimal(0),
                            },
                            "transactions": [],
                        },
                    ],
                }
            ],
        }
    )


def test_cas_import(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_read(f: Any, password: str, **_: Any) -> CASData:
        seen["password"] = password
        return fake_cas()

    monkeypatch.setattr("casparser.read_cas_pdf", fake_read)
    r = client.post(
        "/import/cas", files={"file": ("cas.pdf", b"%PDF-fake")}, data={"password": "s3cret"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen["password"] == "s3cret"
    assert "s3cret" not in r.text
    assert body["snapshot"]["source"] == "cas_cams"
    assert body["snapshot"]["row_count"] == 1
    assert any("fully redeemed" in w for w in body["warnings"])
    assert any("unit balance mismatch" in w for w in body["warnings"])

    (f,) = client.get("/portfolio/holdings").json()["mf"]
    assert (f["amfi_code"], f["resolution"]) == ("122639", "amfi_code")
    assert f["units"] == 100.5 and f["invested"] == 7000 and f["current_value"] == 8809.38
    assert f["first_purchase_date"] == "2024-03-05"
    assert f["transaction_count"] == 3


def test_cas_wrong_password(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_read(*_: Any, **__: Any) -> CASData:
        raise IncorrectPasswordError("Incorrect PDF password!")

    monkeypatch.setattr("casparser.read_cas_pdf", fake_read)
    r = client.post(
        "/import/cas", files={"file": ("cas.pdf", b"%PDF")}, data={"password": "wrong-one"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Incorrect password for this CAS PDF."
    assert "wrong-one" not in r.text


def test_cas_garbage_pdf(client: TestClient) -> None:
    r = client.post(
        "/import/cas", files={"file": ("cas.pdf", b"not a pdf")}, data={"password": "x"}
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- reference search


def test_reference_search(client: TestClient) -> None:
    assert (
        client.get("/reference/securities", params={"q": "infosys"}).json()[0]["symbol"] == "INFY"
    )
    hits = client.get("/reference/schemes", params={"q": "parag parikh flexi direct growth"}).json()
    assert hits[0]["amfi_code"] == "122639"
