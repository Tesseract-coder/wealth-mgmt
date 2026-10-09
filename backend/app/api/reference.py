from fastapi import APIRouter, Query

from app.core.profiles import get_profiles
from app.importers.reference import scheme_resolver, ticker_resolver
from app.models.schemas import Suggestion

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/securities", response_model=list[Suggestion])
def search_securities(q: str = Query(..., min_length=1)) -> list[Suggestion]:
    """Search the NSE list by symbol or company name (for the ticker fixer)."""
    limit = get_profiles().importing.max_suggestions * 2
    return [
        Suggestion(symbol=s.symbol, name=s.name, score=s.score)
        for s in ticker_resolver().search(q, limit)
    ]


@router.get("/schemes", response_model=list[Suggestion])
def search_schemes(q: str = Query(..., min_length=1)) -> list[Suggestion]:
    """Search AMFI schemes by code or name (for the MF fixer and manual entry)."""
    limit = get_profiles().importing.max_suggestions * 2
    return [
        Suggestion(amfi_code=s.amfi_code, name=s.name, score=s.score)
        for s in scheme_resolver().search(q, limit)
    ]
