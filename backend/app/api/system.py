from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import get_session
from app.core.formatting import format_freshness, now_ist
from app.core.profiles import Profiles, get_profiles
from app.models.schemas import HealthOut, MetaOut

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(session: Session = Depends(get_session)) -> HealthOut:
    try:
        session.exec(text("SELECT 1"))  # type: ignore[call-overload]
        db = "ok"
    except Exception as e:  # pragma: no cover - surfaced in response
        db = f"error: {e}"
    return HealthOut(
        status="ok" if db == "ok" else "degraded",
        database=db,
        config_version=get_profiles().version,
        server_time_ist=format_freshness(now_ist()),
    )


@router.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    return MetaOut(disclaimer=get_profiles().disclaimer, timezone="Asia/Kolkata", currency="INR")


@router.get("/config", response_model=Profiles)
def config() -> Profiles:
    """The validated contents of profiles.yaml (read-only for now; editable in Phase 8)."""
    return get_profiles()
