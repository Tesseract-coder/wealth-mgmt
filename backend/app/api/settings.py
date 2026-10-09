from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.core.formatting import now_ist
from app.core.profiles import get_profiles
from app.models.schemas import ProfileIn, ProfileOut
from app.models.tables import UserProfile

router = APIRouter(prefix="/settings", tags=["settings"])


def _load(session: Session) -> UserProfile:
    profile = session.get(UserProfile, 1)
    if profile is None:
        defaults = get_profiles().defaults
        profile = UserProfile(id=1, style=defaults.style, risk=defaults.risk)
    return profile


def _out(p: UserProfile) -> ProfileOut:
    return ProfileOut(
        style=p.style,
        risk=p.risk,
        custom_technical_weight=p.custom_technical_weight,
        gsheet_url=p.gsheet_url,
        onboarded=p.style is not None,
        updated_at=p.updated_at,
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(session: Session = Depends(get_session)) -> ProfileOut:
    return _out(_load(session))


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, session: Session = Depends(get_session)) -> ProfileOut:
    profile = _load(session)
    profile.style = body.style
    profile.risk = body.risk
    profile.custom_technical_weight = body.custom_technical_weight
    profile.gsheet_url = body.gsheet_url
    profile.updated_at = now_ist()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return _out(profile)
