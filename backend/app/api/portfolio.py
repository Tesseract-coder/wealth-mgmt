from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.api.convert import imported_out, mf_out, snapshot_out, stock_out, txn_counts
from app.core.db import get_session
from app.importers import manual
from app.importers.reference import scheme_resolver, ticker_resolver
from app.importers.scheme_resolver import scheme_override_key
from app.importers.snapshots import clear_snapshots, latest_snapshot
from app.importers.ticker_resolver import override_keys
from app.models.schemas import (
    ClearedOut,
    HoldingsOut,
    ImportedOut,
    MFHoldingOut,
    SchemeFixIn,
    SnapshotOut,
    StockHoldingOut,
    TickerFixIn,
)
from app.models.tables import MFHolding, SchemeOverride, Snapshot, StockHolding, TickerOverride

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/holdings", response_model=HoldingsOut)
def holdings(session: Session = Depends(get_session)) -> HoldingsOut:
    """Raw holdings from the latest stock and MF snapshots (analysis is added in later phases)."""
    s_snap, m_snap = latest_snapshot(session, "stocks"), latest_snapshot(session, "mf")
    stocks = (
        session.exec(select(StockHolding).where(StockHolding.snapshot_id == s_snap.id)).all()
        if s_snap
        else []
    )
    mfs = (
        session.exec(select(MFHolding).where(MFHolding.snapshot_id == m_snap.id)).all()
        if m_snap
        else []
    )
    counts = txn_counts(session, [h.id for h in mfs if h.id is not None])
    return HoldingsOut(
        stocks_snapshot=snapshot_out(s_snap) if s_snap else None,
        stocks=[stock_out(h) for h in stocks],
        mf_snapshot=snapshot_out(m_snap) if m_snap else None,
        mf=[mf_out(h, counts.get(h.id or 0, 0)) for h in mfs],
    )


@router.get("/snapshots", response_model=list[SnapshotOut])
def snapshots(session: Session = Depends(get_session)) -> list[SnapshotOut]:
    rows = session.exec(
        select(Snapshot).order_by(col(Snapshot.created_at).desc(), col(Snapshot.id).desc())
    ).all()
    return [snapshot_out(s) for s in rows]


@router.patch("/stocks/{holding_id}/ticker", response_model=StockHoldingOut)
def fix_ticker(
    holding_id: int, body: TickerFixIn, session: Session = Depends(get_session)
) -> StockHoldingOut:
    h = session.get(StockHolding, holding_id)
    if h is None:
        raise HTTPException(404, "Holding not found")
    symbol = body.symbol.strip().upper().removesuffix(".NS").removesuffix(".BO")
    # BSE symbols aren't checked: the BSE list only has shares that traded in the last month.
    if body.exchange == "NSE" and symbol not in ticker_resolver().by_symbol:
        raise HTTPException(422, f"'{symbol}' is not in the NSE securities list")
    h.symbol, h.exchange, h.resolution, h.resolution_score = symbol, body.exchange, "manual", 100.0
    session.add(h)
    if body.remember:
        for key in override_keys(h.name, h.isin):
            o = session.exec(select(TickerOverride).where(TickerOverride.key == key)).first()
            o = o or TickerOverride(key=key, symbol=symbol)
            o.symbol, o.exchange = symbol, body.exchange
            session.add(o)
    session.commit()
    session.refresh(h)
    return stock_out(h)


@router.patch("/mf/{holding_id}/scheme", response_model=MFHoldingOut)
def fix_scheme(
    holding_id: int, body: SchemeFixIn, session: Session = Depends(get_session)
) -> MFHoldingOut:
    h = session.get(MFHolding, holding_id)
    if h is None:
        raise HTTPException(404, "Holding not found")
    s = scheme_resolver().by_code.get(body.amfi_code.strip())
    if s is None:
        raise HTTPException(422, f"AMFI scheme code '{body.amfi_code}' not found")
    h.amfi_code, h.resolution, h.resolution_score = s.code, "manual", 100.0
    h.plan, h.option = s.plan or h.plan, s.option or h.option
    h.category, h.amc = s.category or h.category, h.amc or s.amc
    h.isin = h.isin or s.isin_growth
    if h.nav is None:
        h.nav, h.nav_date = s.nav, s.nav_date
    if h.current_value is None and h.nav is not None:
        h.current_value = round(h.units * h.nav, 2)
    session.add(h)
    if body.remember:
        key = scheme_override_key(h.scheme_name)
        o = session.exec(select(SchemeOverride).where(SchemeOverride.key == key)).first()
        o = o or SchemeOverride(key=key, amfi_code=s.code)
        o.amfi_code = s.code
        session.add(o)
    session.commit()
    session.refresh(h)
    return mf_out(h)


@router.delete("/mf/{holding_id}", response_model=ImportedOut)
def delete_manual_mf(holding_id: int, session: Session = Depends(get_session)) -> ImportedOut:
    """Remove a manually added fund (creates a new MF snapshot without it)."""
    h = session.get(MFHolding, holding_id)
    if h is None:
        raise HTTPException(404, "Holding not found")
    latest = latest_snapshot(session, "mf")
    if latest is None or h.snapshot_id != latest.id:
        raise HTTPException(409, "Only holdings in the latest snapshot can be removed")
    if h.origin != "manual":
        raise HTTPException(
            409, "Only manually added funds can be removed; re-import to change others"
        )
    return imported_out(session, manual.remove_mf(session, h))


@router.delete("/{kind}", response_model=ClearedOut)
def clear_holdings(
    kind: Literal["stocks", "mf"], session: Session = Depends(get_session)
) -> ClearedOut:
    """Remove all imported stocks or mutual funds, with their snapshot history.

    Ticker/scheme fixes and remembered column mappings are kept."""
    snapshots, removed = clear_snapshots(session, kind)
    return ClearedOut(kind=kind, snapshots=snapshots, holdings=removed)
