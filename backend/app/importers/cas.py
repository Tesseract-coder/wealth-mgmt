"""CAMS / KFintech (and NSDL/CDSL) Consolidated Account Statement PDFs, via casparser.

The PDF password is used only for this call: it is never stored, logged or returned.
"""

import io
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import casparser
from casparser.exceptions import IncorrectPasswordError, ParserException
from sqlmodel import Session

from app.importers.groww import Imported, build_mf_holding, carry_forward_manual
from app.importers.reference import scheme_overrides
from app.importers.snapshots import save_mf_snapshot
from app.importers.tabular import ImportFileError
from app.models.tables import MFHolding, MFTransaction

logger = logging.getLogger(__name__)

PURCHASE_TYPES = {"PURCHASE", "PURCHASE_SIP", "SWITCH_IN", "SWITCH_IN_MERGER", "GIFT_IN"}


def _f(v: Decimal | float | None) -> float | None:
    return None if v is None else float(v)


def _d(v: date | str | None) -> date | None:
    if v is None or isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _enum(v: Any) -> str:
    return str(getattr(v, "value", v) or "").upper()


def parse_cas(content: bytes, password: str) -> Any:
    try:
        return casparser.read_cas_pdf(io.BytesIO(content), password)
    except IncorrectPasswordError:
        raise ImportFileError("Incorrect password for this CAS PDF.") from None
    except ParserException as e:
        raise ImportFileError(f"Could not read this CAS PDF: {e}") from None
    except Exception as e:  # pdf libraries raise assorted errors on non-CAS files
        logger.warning("CAS parsing failed: %s", type(e).__name__)
        raise ImportFileError(
            "Could not read this PDF. Make sure it is a CAMS/KFintech or NSDL/CDSL CAS."
        ) from None


def import_cas(session: Session, content: bytes, password: str, filename: str) -> Imported:
    data = parse_cas(content, password)
    del password
    overrides = scheme_overrides(session)
    rows: list[tuple[MFHolding, list[MFTransaction]]] = []
    warnings: list[str] = []
    file_type = _enum(getattr(data, "file_type", "")) or "UNKNOWN"

    if hasattr(data, "folios"):  # CAMS / KFintech
        closed = 0
        for folio in data.folios:
            for sch in folio.schemes:
                if sch.close is None or sch.close <= 0:
                    closed += 1
                    continue
                v = sch.valuation
                holding, notes = build_mf_holding(
                    session,
                    name=sch.scheme,
                    units=_f(sch.close),
                    invested=_f(v.cost),
                    current_value=_f(v.value),
                    folio=folio.folio,
                    isin=sch.isin,
                    amfi_code=sch.amfi,
                    amc=folio.amc,
                    nav=_f(v.nav),
                    nav_date=_d(v.date),
                    overrides=overrides,
                )
                txns = [
                    MFTransaction(
                        holding_id=0,
                        date=d,
                        type=_enum(t.type),
                        description=t.description,
                        amount=_f(t.amount),
                        units=_f(t.units),
                        nav=_f(t.nav),
                    )
                    for t in sch.transactions
                    if (d := _d(t.date)) is not None
                ]
                buys = [t.date for t in txns if t.type in PURCHASE_TYPES]
                holding.first_purchase_date = min(buys) if buys else None
                warnings += notes
                rows.append((holding, txns))
        if closed:
            warnings.append(f"Skipped {closed} fully redeemed scheme(s) with zero units.")
        if _enum(getattr(data, "cas_type", "")) == "SUMMARY":
            warnings.append(
                "This is a summary CAS without transactions; your own XIRR and holding periods "
                "need a detailed CAS."
            )
    else:  # NSDL / CDSL depository CAS
        equities = 0
        for acct in data.accounts:
            equities += len(acct.equities)
            for mf in acct.mutual_funds:
                holding, notes = build_mf_holding(
                    session,
                    name=mf.name or mf.isin,
                    units=_f(mf.balance),
                    invested=_f(mf.total_cost),
                    current_value=_f(mf.value),
                    folio=mf.folio,
                    isin=mf.isin,
                    amfi_code=mf.amfi,
                    nav=_f(mf.nav),
                    overrides=overrides,
                )
                warnings += notes
                rows.append((holding, []))
        if equities:
            warnings.append(
                f"{equities} stock holding(s) in this CAS were not imported. "
                "Use the Groww holdings export for stocks."
            )

    warnings += [f"CAS parser warning: {w}" for w in getattr(data, "parse_warnings", [])]
    if not rows:
        raise ImportFileError("No mutual fund holdings with units were found in this CAS.")
    rows, kept = carry_forward_manual(session, rows)
    if kept:
        warnings.append(f"Kept {kept} manually added fund(s) from your previous snapshot.")
    snap = save_mf_snapshot(session, f"cas_{file_type.lower()}", filename, rows, None)
    logger.info("Imported %d MF holdings from CAS (%s), snapshot %s", len(rows), file_type, snap.id)
    return Imported(snap, [], warnings)
