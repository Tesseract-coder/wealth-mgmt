from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import db, profiles
from app.core.settings import get_settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App wired to a throwaway SQLite file."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()
    db._engine = None
    profiles._profiles = None
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    db._engine = None
    get_settings.cache_clear()
