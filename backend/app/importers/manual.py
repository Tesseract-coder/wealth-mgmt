"""Manual MF entries. Each change creates a new MF snapshot, carrying over the previous rows."""

from datetime import date

from sqlmodel import Session

from app.importers.groww import Imported, build_mf_holding
from app.importers.reference import scheme_overrides, scheme_resolver
from app.importers.snapshots import copy_mf_rows, latest_snapshot, save_mf_snapshot
from app.models.tables import MFHolding


def add_manual_mf(
    session: Session,
    *,
    scheme: str,
    units: float,
    invested: float,
    folio: str | None = None,
    purchase_date: date | None = None,
) -> Imported:
    scheme = scheme.strip()
    code = scheme if scheme.isdigit() else None
    name = scheme
    if code and (s := scheme_resolver().by_code.get(code)):
        name = s.name
    holding, notes = build_mf_holding(
        session,
        name=name,
        units=units,
        invested=invested,
        current_value=None,
        folio=folio,
        amfi_code=code,
        origin="manual",
        overrides=scheme_overrides(session),
    )
    holding.first_purchase_date = purchase_date
    rows = copy_mf_rows(session, latest_snapshot(session, "mf"))
    rows.append((holding, []))
    snap = save_mf_snapshot(session, "manual", None, rows, f"Added {name}")
    if holding.resolution == "unresolved":
        notes.append(f"Could not match '{scheme}' to an AMFI scheme; pick one in the fixer.")
    return Imported(snap, [], notes)


def remove_mf(session: Session, holding: MFHolding) -> Imported:
    """New snapshot without this holding."""
    assert holding.id is not None
    rows = copy_mf_rows(
        session, latest_snapshot(session, "mf"), exclude_ids=frozenset({holding.id})
    )
    new = save_mf_snapshot(session, "manual", None, rows, f"Removed {holding.scheme_name}")
    return Imported(new, [], [])
