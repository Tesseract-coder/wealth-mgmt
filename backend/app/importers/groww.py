"""Groww holdings exports (stocks and mutual funds), XLSX or CSV."""

import json
import logging
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.core.profiles import get_profiles
from app.data.amfi import detect_option, detect_plan
from app.importers import column_mapper
from app.importers.column_mapper import FIELDS, MappingResult, header_signature
from app.importers.reference import (
    scheme_overrides,
    scheme_resolver,
    ticker_overrides,
    ticker_resolver,
)
from app.importers.snapshots import (
    copy_mf_rows,
    latest_snapshot,
    save_mf_snapshot,
    save_stock_snapshot,
    suggestions_json,
)
from app.importers.tabular import (
    Cell,
    Grid,
    cell_text,
    parse_date,
    parse_isin,
    parse_number,
    read_grid,
)
from app.models.tables import ColumnMapping, MFHolding, MFTransaction, Snapshot, StockHolding

logger = logging.getLogger(__name__)


@dataclass
class SkippedRow:
    row: int  # 1-based row number as seen in Excel
    reason: str
    text: str


@dataclass
class NeedsMapping:
    mapping: MappingResult
    preview: list[list[str]]
    signature: str


@dataclass
class Imported:
    snapshot: Snapshot
    skipped: list[SkippedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class UserMapping:
    header_row: int  # 0-based
    columns: dict[str, int]
    remember: bool = True


def _saved_mapping(session: Session, grid: Grid, kind: str) -> MappingResult | None:
    """A mapping the user confirmed earlier for a file with identical headers."""
    scan = get_profiles().importing.header_scan_rows
    for idx, row in enumerate(grid[:scan]):
        sig = header_signature(kind, [cell_text(c) for c in row])
        saved = session.exec(select(ColumnMapping).where(ColumnMapping.signature == sig)).first()
        if saved:
            try:
                return column_mapper.manual(grid, kind, idx, json.loads(saved.mapping_json))
            except ValueError:
                logger.warning("Saved column mapping %s no longer fits; ignoring it", sig[:8])
    return None


def resolve_mapping(
    session: Session, grid: Grid, kind: str, user: UserMapping | None
) -> MappingResult | NeedsMapping:
    if user is not None:
        result = column_mapper.manual(grid, kind, user.header_row, user.columns)
        if result.complete and user.remember:
            sig = header_signature(kind, result.headers)
            existing = session.exec(
                select(ColumnMapping).where(ColumnMapping.signature == sig)
            ).first()
            row = existing or ColumnMapping(kind=kind, signature=sig, mapping_json="")
            row.mapping_json = json.dumps(result.mapping)
            session.add(row)
            session.commit()
    else:
        result = _saved_mapping(session, grid, kind) or column_mapper.detect(
            grid, kind, get_profiles().importing
        )
    if kind == "mf" and "units" not in result.mapping and "current_value" not in result.mapping:
        result.missing_required = sorted({*result.missing_required, "units"})
    if not result.complete:
        preview = [
            [cell_text(c) for c in r] for r in grid[result.header_row + 1 : result.header_row + 6]
        ]
        return NeedsMapping(result, preview, header_signature(kind, result.headers))
    return result


def _records(grid: Grid, m: MappingResult) -> list[tuple[int, dict[str, Cell], str]]:
    out = []
    for i in range(m.header_row + 1, len(grid)):
        row = grid[i]
        if not any(cell_text(c) for c in row):
            continue
        rec = {k: (row[c] if c < len(row) else None) for k, c in m.mapping.items()}
        text = " | ".join(cell_text(c) for c in row if cell_text(c))[:200]
        out.append((i + 1, rec, text))
    return out


def _is_total(name: str) -> bool:
    n = name.strip().lower()
    return n.startswith(("total", "grand total", "net total")) or n in ("sum", "summary")


def _source(filename: str) -> str:
    return "groww_xlsx" if filename.lower().endswith((".xlsx", ".xlsm")) else "groww_csv"


# --------------------------------------------------------------------------- stocks


def import_stocks(
    session: Session, content: bytes, filename: str, user: UserMapping | None = None
) -> Imported | NeedsMapping:
    return import_stocks_grid(
        session, read_grid(content, filename), filename, _source(filename), user
    )


def import_stocks_grid(
    session: Session, grid: Grid, filename: str, source: str, user: UserMapping | None = None
) -> Imported | NeedsMapping:
    """Stocks from a grid of cells (an uploaded file, or a Google Sheet tab)."""
    mapping = resolve_mapping(session, grid, "stocks", user)
    if isinstance(mapping, NeedsMapping):
        return mapping

    skipped: list[SkippedRow] = []
    warnings: list[str] = []
    merged: dict[str, StockHolding] = {}
    resolver, overrides = ticker_resolver(), ticker_overrides(session)

    for rownum, rec, text in _records(grid, mapping):
        name = cell_text(rec.get("name"))
        if not name:
            skipped.append(SkippedRow(rownum, "No stock name", text))
            continue
        if _is_total(name):
            skipped.append(SkippedRow(rownum, "Total row", text))
            continue
        qty = parse_number(rec.get("quantity"))
        if qty is None:
            skipped.append(SkippedRow(rownum, "No quantity (not a holding row)", text))
            continue
        if qty <= 0:
            skipped.append(SkippedRow(rownum, "Quantity is zero", text))
            continue
        avg = parse_number(rec.get("avg_price"))
        invested = parse_number(rec.get("invested"))
        if avg is None and invested is not None:
            avg = invested / qty
        if avg is None or avg < 0:
            skipped.append(SkippedRow(rownum, "Average buy price missing", text))
            continue
        if invested is None:
            invested = qty * avg
        close = parse_number(rec.get("close_price"))
        value = parse_number(rec.get("current_value"))
        if value is None and close is not None:
            value = qty * close
        pnl = parse_number(rec.get("unrealised_pnl"))
        if pnl is None and value is not None:
            pnl = value - invested
        isin = parse_isin(rec.get("isin"))

        key = isin or name.lower()
        if key in merged:
            # Same stock on two rows (e.g. pledged + free quantity): combine.
            h = merged[key]
            h.quantity += qty
            h.invested += invested
            h.avg_price = h.invested / h.quantity
            h.current_value = (
                None if h.current_value is None or value is None else h.current_value + value
            )
            h.unrealised_pnl = (
                None if h.unrealised_pnl is None or pnl is None else h.unrealised_pnl + pnl
            )
            warnings.append(f"Combined two rows for {name} (row {rownum}).")
            continue

        res = resolver.resolve(name, isin, cell_text(rec.get("symbol")) or None, overrides)
        merged[key] = StockHolding(
            snapshot_id=0,
            name=name,
            isin=isin,
            symbol=res.symbol,
            exchange=res.exchange,
            resolution=res.method,
            resolution_score=res.score,
            suggestions=suggestions_json(res.suggestions),
            quantity=qty,
            avg_price=round(avg, 4),
            close_price=close,
            invested=round(invested, 2),
            current_value=None if value is None else round(value, 2),
            unrealised_pnl=None if pnl is None else round(pnl, 2),
            purchase_date=parse_date(rec.get("purchase_date")),
        )

    rows = list(merged.values())
    if not rows:
        raise column_mapper_error(skipped)
    if "purchase_date" not in mapping.mapping:
        warnings.append(
            "No purchase dates in this file, so STCG/LTCG can't be determined yet. "
            "You can add dates later."
        )
    snap = save_stock_snapshot(session, source, filename, rows, None)
    logger.info("Imported %d stock holdings from %s (snapshot %s)", len(rows), filename, snap.id)
    return Imported(snap, skipped, warnings)


def column_mapper_error(skipped: list[SkippedRow]) -> ValueError:
    reasons = sorted({s.reason for s in skipped})
    return ValueError(
        "No holdings could be read from this file"
        + (f" (rows skipped: {', '.join(reasons)})." if reasons else ".")
        + " Check the column mapping."
    )


# --------------------------------------------------------------------------- mutual funds


def build_mf_holding(
    session: Session,
    *,
    name: str,
    units: float | None,
    invested: float | None,
    current_value: float | None,
    folio: str | None = None,
    isin: str | None = None,
    amfi_code: str | None = None,
    amc: str | None = None,
    category: str | None = None,
    nav: float | None = None,
    nav_date: object = None,
    origin: str = "import",
    overrides: dict[str, str] | None = None,
) -> tuple[MFHolding, list[str]]:
    """Resolve the scheme and fill gaps (NAV, value, units) from the AMFI master."""
    notes: list[str] = []
    res = scheme_resolver().resolve(name, isin, amfi_code, overrides)
    s = res.scheme
    if s is not None:
        nav = nav if nav is not None else s.nav
        nav_date = nav_date if nav_date is not None else s.nav_date
    if units is None and current_value is not None and nav:
        units = round(current_value / nav, 4)
        notes.append(f"Units for {name} estimated from value ÷ NAV.")
    if current_value is None and units is not None and nav is not None:
        current_value = round(units * nav, 2)
    holding = MFHolding(
        snapshot_id=0,
        scheme_name=name,
        amc=amc or (s.amc if s else None),
        category=(s.category if s and s.category else category),
        folio=folio,
        isin=isin or (s.isin_growth if s else None),
        amfi_code=s.code if s else (amfi_code or None),
        plan=s.plan if s and s.plan else detect_plan(name),
        option=s.option if s and s.option else detect_option(name),
        resolution=res.method,
        resolution_score=res.score,
        suggestions=suggestions_json(res.suggestions),
        units=units or 0.0,
        invested=None if invested is None else round(invested, 2),
        current_value=current_value,
        nav=nav,
        nav_date=nav_date,  # type: ignore[arg-type]
        origin=origin,
    )
    return holding, notes


def carry_forward_manual(
    session: Session, imported: list[tuple[MFHolding, list[MFTransaction]]]
) -> tuple[list[tuple[MFHolding, list[MFTransaction]]], int]:
    """Keep manually-added funds that the new import doesn't already contain."""
    codes = {h.amfi_code for h, _ in imported if h.amfi_code}
    kept = [
        (h, t)
        for h, t in copy_mf_rows(session, latest_snapshot(session, "mf"), origin="manual")
        if not (h.amfi_code and h.amfi_code in codes)
    ]
    return imported + kept, len(kept)


def import_mf(
    session: Session, content: bytes, filename: str, user: UserMapping | None = None
) -> Imported | NeedsMapping:
    return import_mf_grid(session, read_grid(content, filename), filename, _source(filename), user)


def import_mf_grid(
    session: Session, grid: Grid, filename: str, source: str, user: UserMapping | None = None
) -> Imported | NeedsMapping:
    """Mutual funds from a grid of cells (an uploaded file, or a Google Sheet tab)."""
    mapping = resolve_mapping(session, grid, "mf", user)
    if isinstance(mapping, NeedsMapping):
        return mapping

    skipped: list[SkippedRow] = []
    warnings: list[str] = []
    rows: list[tuple[MFHolding, list[MFTransaction]]] = []
    overrides = scheme_overrides(session)
    for rownum, rec, text in _records(grid, mapping):
        name = cell_text(rec.get("scheme_name"))
        if not name:
            skipped.append(SkippedRow(rownum, "No scheme name", text))
            continue
        if _is_total(name):
            skipped.append(SkippedRow(rownum, "Total row", text))
            continue
        units = parse_number(rec.get("units"))
        value = parse_number(rec.get("current_value"))
        if (units is None or units <= 0) and (value is None or value <= 0):
            skipped.append(SkippedRow(rownum, "Units and value missing or zero", text))
            continue
        holding, notes = build_mf_holding(
            session,
            name=name,
            units=units if units and units > 0 else None,
            invested=parse_number(rec.get("invested")),
            current_value=value,
            folio=cell_text(rec.get("folio")) or None,
            isin=parse_isin(rec.get("isin")),
            amfi_code=cell_text(rec.get("amfi_code")) or None,
            amc=cell_text(rec.get("amc")) or None,
            category=cell_text(rec.get("category")) or None,
            nav=parse_number(rec.get("nav")),
            overrides=overrides,
        )
        holding.first_purchase_date = parse_date(rec.get("purchase_date"))
        warnings += notes
        rows.append((holding, []))

    if not rows:
        raise column_mapper_error(skipped)
    rows, kept = carry_forward_manual(session, rows)
    if kept:
        warnings.append(f"Kept {kept} manually added fund(s) from your previous snapshot.")
    snap = save_mf_snapshot(session, source, filename, rows, None)
    logger.info("Imported %d MF holdings from %s (snapshot %s)", len(rows), filename, snap.id)
    return Imported(snap, skipped, warnings)


def field_specs(kind: str) -> list[dict[str, object]]:
    return [{"key": s.key, "label": s.label, "required": s.required} for s in FIELDS[kind]]
