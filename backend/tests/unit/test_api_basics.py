from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _isolate, _teardown


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["server_time_ist"].endswith("IST")


def test_meta_has_disclaimer(client: TestClient) -> None:
    assert "not investment advice" in client.get("/meta").json()["disclaimer"]


def test_profile_defaults_to_medium_and_not_onboarded(client: TestClient) -> None:
    body = client.get("/settings/profile").json()
    assert body["risk"] == "medium"
    assert body["style"] is None
    assert body["onboarded"] is False


def test_profile_roundtrip(client: TestClient) -> None:
    r = client.put("/settings/profile", json={"style": "swing"})
    assert r.status_code == 200
    assert r.json()["risk"] == "medium"
    body = client.get("/settings/profile").json()
    assert body["style"] == "swing"
    assert body["onboarded"] is True


def test_profile_rejects_unknown_style(client: TestClient) -> None:
    assert client.put("/settings/profile", json={"style": "yolo"}).status_code == 422


def test_openapi_docs_available(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_timestamps_returned_in_ist(client: TestClient) -> None:
    client.put("/settings/profile", json={"style": "swing"})
    assert client.get("/settings/profile").json()["updated_at"].endswith("+05:30")


def test_unexpected_errors_answer_in_plain_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import system
    from app.main import create_app

    # A throwaway database, like the client fixture: starting the app otherwise opened the real
    # one and ran the start-up price refresh against it.
    _isolate(tmp_path, monkeypatch)

    def boom() -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(system, "get_profiles", boom)
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/meta")
    finally:
        _teardown()
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "RuntimeError: disk on fire" in detail and "backend log" in detail
