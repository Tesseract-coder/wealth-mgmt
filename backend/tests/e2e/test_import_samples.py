"""End-to-end: every FAKE file in sample_data/ imports through the API.

Phase 6 extends this to assert that each holding gets a signal with reasons.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

SAMPLES = Path(__file__).resolve().parents[3] / "sample_data"


def test_all_samples_import(client: TestClient) -> None:
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
