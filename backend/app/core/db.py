import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.core.settings import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _sqlite_pragmas)
        event.listen(_engine, "after_cursor_execute", _count_write)
    return _engine


# --------------------------------------------------------------------------- write version

# Tables the analysis writes as a by-product (history, job progress, sync logs): writing them
# doesn't change any analysis input, so it doesn't count as a data change.
_LOG_TABLES = frozenset({"signalrecord", "axisrecord", "job", "sheetsync", "screenerscan"})
_WRITE = re.compile(r'^\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM)\s+"?(\w+)', re.I)
_version = 0
_version_lock = threading.Lock()


def _count_write(_conn: Any, _cur: Any, statement: str, *_: Any) -> None:
    m = _WRITE.match(statement)
    if m and m.group(1).lower() not in _LOG_TABLES:
        global _version
        with _version_lock:
            _version += 1


def write_version() -> int:
    """Goes up on every write to an analysis input in this process (imports, refreshes,
    settings, overrides). Cached results built at an older version are out of date."""
    return _version


def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
    # WAL lets API reads proceed while a background refresh job is writing.
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def init_db() -> None:
    import app.models.tables  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
