"""End-to-end: every FAKE file in sample_data/ imports through the API, then every stock and
fund gets a signal with reasons, and the portfolio summary builds (market data, NAVs and
fundamentals faked, no network)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs.runner import get_runner
from tests.unit.test_funds_api import _mfapi
from tests.unit.test_signals_api import _fake_sources

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data"


def test_all_samples_import_and_get_signals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def up(url: str, name: str, **form: str) -> dict[str, object]:
        with open(SAMPLES / name, "rb") as f:
            r = client.post(url, files={"file": (name, f)}, data=form)
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]

    assert up("/import/groww-stocks", "groww_stocks_holdings.xlsx")["status"] == "imported"
    assert up("/import/groww-stocks", "groww_stocks_messy.csv")["status"] == "imported"
    assert (
        up("/import/groww-stocks", "groww_stocks_unknown_headers.csv")["status"] == "needs_mapping"
    )
    mapping = {"header_row": 1, "columns": {"name": 0, "quantity": 2, "avg_price": 3}}
    assert (
        up("/import/groww-stocks", "groww_stocks_unknown_headers.csv", mapping=json.dumps(mapping))[
            "status"
        ]
        == "imported"
    )
    assert up("/import/groww-mf", "groww_mf_holdings.xlsx")["status"] == "imported"
    assert up("/import/groww-mf", "groww_mf_messy.csv")["status"] == "imported"

    snaps = client.get("/portfolio/snapshots").json()
    assert len(snaps) == 5
    holdings = client.get("/portfolio/holdings").json()
    assert holdings["stocks_snapshot"]["row_count"] == 4
    assert holdings["mf_snapshot"]["row_count"] == 4

    # Fetch prices and fundamentals for the holdings, then score them.
    _fake_sources(monkeypatch)
    _mfapi(monkeypatch)
    job = client.post("/market/refresh", json={"scope": "all"}).json()
    get_runner().wait(job["id"], timeout=120)
    assert client.get(f"/jobs/{job['id']}").json()["status"] == "done"
    client.put("/settings/profile", json={"style": "swing", "risk": "medium"})
    body = client.get("/analysis/signals/holdings").json()
    assert body["style"] == "swing" and len(body["holdings"]) == 4
    for h in body["holdings"]:
        assert h["signal"] != "no_signal", h
        assert h["composite"] is not None and h["confidence"] is not None
        assert h["top_bullish"] or h["top_bearish"]
        assert h["rule"] and h["stop"] is not None
    detail = client.get("/analysis/stock/RELIANCE.NS", params={"fetch": False}).json()
    assert detail["bullish"] or detail["bearish"]
    assert detail["levels"]["targets"] and detail["tax"] is not None
    assert "SEBI-registered" in detail["disclaimer"]

    # Every resolved fund gets a Continue / Review / Switch signal with reasons.
    funds = client.get("/analysis/mf/holdings").json()
    assert funds["funds"]
    for f in funds["funds"]:
        assert f["signal"] in ("continue", "review", "switch"), f
        assert f["reasons"] and f["rule"]
    summary = client.get("/portfolio/summary").json()
    assert summary["total_value"] > 0 and summary["by_asset_class"]
    assert "SEBI-registered" in summary["disclaimer"]
