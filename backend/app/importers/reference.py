"""Shared, cached resolver instances and DB-backed overrides."""

from functools import lru_cache

from sqlmodel import Session, select

from app.core.profiles import get_profiles
from app.data.amfi import load_schemes
from app.data.nse import load_securities
from app.importers.scheme_resolver import SchemeResolver
from app.importers.ticker_resolver import TickerResolver
from app.models.tables import SchemeOverride, TickerOverride


@lru_cache
def ticker_resolver() -> TickerResolver:
    return TickerResolver(load_securities(), get_profiles().importing)


@lru_cache
def scheme_resolver() -> SchemeResolver:
    return SchemeResolver(load_schemes(), get_profiles().importing)


def ticker_overrides(session: Session) -> dict[str, tuple[str, str]]:
    return {o.key: (o.symbol, o.exchange) for o in session.exec(select(TickerOverride))}


def scheme_overrides(session: Session) -> dict[str, str]:
    return {o.key: o.amfi_code for o in session.exec(select(SchemeOverride))}
