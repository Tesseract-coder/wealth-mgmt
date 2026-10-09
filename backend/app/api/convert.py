"""Table rows → API response models."""

import json

from sqlmodel import Session, col, func, select

from app.importers.groww import Imported
from app.models.schemas import (
    ImportedOut,
    MFHoldingOut,
    SkippedRowOut,
    SnapshotOut,
    StockHoldingOut,
    Suggestion,
)
from app.models.tables import MFHolding, MFTransaction, Snapshot, StockHolding


def snapshot_out(s: Snapshot) -> SnapshotOut:
    return SnapshotOut.model_validate(s.model_dump())


def _suggestions(raw: str | None) -> list[Suggestion]:
    return [Suggestion.model_validate(x) for x in json.loads(raw)] if raw else []


def stock_out(h: StockHolding) -> StockHoldingOut:
    return StockHoldingOut.model_validate(
        h.model_dump() | {"suggestions": _suggestions(h.suggestions)}
    )


def mf_out(h: MFHolding, txn_count: int = 0) -> MFHoldingOut:
    return MFHoldingOut.model_validate(
        h.model_dump()
        | {"suggestions": _suggestions(h.suggestions), "transaction_count": txn_count}
    )


def imported_out(session: Session, result: Imported) -> ImportedOut:
    snap = result.snapshot
    table = StockHolding if snap.kind == "stocks" else MFHolding
    unresolved = session.exec(
        select(func.count())
        .select_from(table)
        .where(table.snapshot_id == snap.id, table.resolution == "unresolved")
    ).one()
    return ImportedOut(
        snapshot=snapshot_out(snap),
        skipped=[SkippedRowOut(row=s.row, reason=s.reason, text=s.text) for s in result.skipped],
        warnings=result.warnings,
        unresolved=unresolved,
    )


def txn_counts(session: Session, holding_ids: list[int]) -> dict[int, int]:
    if not holding_ids:
        return {}
    rows = session.exec(
        select(MFTransaction.holding_id, func.count())
        .where(col(MFTransaction.holding_id).in_(holding_ids))
        .group_by(col(MFTransaction.holding_id))
    ).all()
    return {hid: n for hid, n in rows}
