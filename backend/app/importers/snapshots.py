"""Persist holdings as a new dated snapshot; read the latest snapshot of each kind."""

import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlmodel import Session, col, select

from app.models.tables import MFHolding, MFTransaction, Snapshot, StockHolding


def suggestions_json(items: Sequence[Any]) -> str | None:
    if not items:
        return None
    return json.dumps(
        [asdict(s) if is_dataclass(s) and not isinstance(s, type) else s for s in items]
    )


def latest_snapshot(session: Session, kind: str) -> Snapshot | None:
    return session.exec(
        select(Snapshot)
        .where(Snapshot.kind == kind)
        .order_by(col(Snapshot.created_at).desc(), col(Snapshot.id).desc())
    ).first()


def _total(values: list[float | None]) -> float | None:
    """Sum only when every value is known; a partial total would be misleading."""
    if not values or any(v is None for v in values):
        return None
    return round(sum(v for v in values if v is not None), 2)


def save_stock_snapshot(
    session: Session, source: str, filename: str | None, rows: list[StockHolding], note: str | None
) -> Snapshot:
    snap = Snapshot(
        kind="stocks",
        source=source,
        filename=filename,
        row_count=len(rows),
        total_invested=_total([r.invested for r in rows]),
        total_value=_total([r.current_value for r in rows]),
        note=note,
    )
    session.add(snap)
    session.flush()
    for r in rows:
        r.snapshot_id = snap.id  # type: ignore[assignment]
        session.add(r)
    session.commit()
    session.refresh(snap)
    return snap


def save_mf_snapshot(
    session: Session,
    source: str,
    filename: str | None,
    rows: list[tuple[MFHolding, list[MFTransaction]]],
    note: str | None,
) -> Snapshot:
    snap = Snapshot(
        kind="mf",
        source=source,
        filename=filename,
        row_count=len(rows),
        total_invested=_total([h.invested for h, _ in rows]),
        total_value=_total([h.current_value for h, _ in rows]),
        note=note,
    )
    session.add(snap)
    session.flush()
    for holding, txns in rows:
        holding.snapshot_id = snap.id  # type: ignore[assignment]
        session.add(holding)
        session.flush()
        for t in txns:
            t.holding_id = holding.id  # type: ignore[assignment]
            session.add(t)
    session.commit()
    session.refresh(snap)
    return snap


def copy_mf_rows(
    session: Session,
    snapshot: Snapshot | None,
    origin: str | None = None,
    exclude_ids: frozenset[int] = frozenset(),
) -> list[tuple[MFHolding, list[MFTransaction]]]:
    """Detached copies of a snapshot's MF rows (and their transactions), for carrying forward."""
    if snapshot is None:
        return []
    q = select(MFHolding).where(MFHolding.snapshot_id == snapshot.id)
    if origin:
        q = q.where(MFHolding.origin == origin)
    out = []
    for h in session.exec(q):
        if h.id in exclude_ids:
            continue
        txns = session.exec(select(MFTransaction).where(MFTransaction.holding_id == h.id)).all()
        h_copy = MFHolding.model_validate(
            h.model_dump(exclude={"id", "snapshot_id"}) | {"snapshot_id": 0}
        )
        t_copies = [
            MFTransaction.model_validate(
                t.model_dump(exclude={"id", "holding_id"}) | {"holding_id": 0}
            )
            for t in txns
        ]
        out.append((h_copy, t_copies))
    return out


def clear_snapshots(session: Session, kind: str) -> tuple[int, int]:
    """Delete every snapshot of a kind with its holdings (and MF transactions).

    Ticker/scheme fixes and remembered column mappings are kept for the next import.
    Returns (snapshots, holdings) removed."""
    snaps = session.exec(select(Snapshot).where(Snapshot.kind == kind)).all()
    snap_ids = [s.id for s in snaps]
    holdings: Sequence[StockHolding | MFHolding]
    if kind == "stocks":
        holdings = session.exec(
            select(StockHolding).where(col(StockHolding.snapshot_id).in_(snap_ids))
        ).all()
    else:
        funds = session.exec(
            select(MFHolding).where(col(MFHolding.snapshot_id).in_(snap_ids))
        ).all()
        ids = [h.id for h in funds]
        for t in session.exec(select(MFTransaction).where(col(MFTransaction.holding_id).in_(ids))):
            session.delete(t)
        session.flush()
        holdings = funds
    for h in holdings:
        session.delete(h)
    session.flush()
    for s in snaps:
        session.delete(s)
    session.commit()
    return len(snaps), len(holdings)
