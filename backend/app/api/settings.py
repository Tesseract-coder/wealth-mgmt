from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core import overrides
from app.core.db import get_session
from app.core.formatting import now_ist
from app.core.profiles import ConfigError, get_profiles
from app.core.settings import get_settings
from app.models.schemas import ProfileIn, ProfileOut, ThresholdOut, ThresholdsIn, ThresholdsOut
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


def _thresholds() -> ThresholdsOut:
    p = get_profiles().model_dump()
    edited = overrides.flat_overrides()
    items = [
        ThresholdOut(
            path=e.path,
            group=e.group,
            label=e.label,
            unit=e.unit,
            nullable=e.nullable,
            value=overrides.get_path(p, e.path),
            default=overrides.base_value(e.path),
            edited=e.path in edited and edited[e.path] != overrides.base_value(e.path),
        )
        for e in overrides.EDITABLE
    ]
    return ThresholdsOut(
        items=items,
        override_file=str(get_settings().profiles_override_path),
        edited=sum(i.edited for i in items),
        note="Other settings (indicator periods, scoring weights, tax rates) live in "
        "backend/config/profiles.yaml. Edit that file and restart to change them.",
    )


@router.get("/thresholds", response_model=ThresholdsOut)
def get_thresholds() -> ThresholdsOut:
    return _thresholds()


@router.put("/thresholds", response_model=ThresholdsOut)
def put_thresholds(body: ThresholdsIn) -> ThresholdsOut:
    """Change editable thresholds. Validated against the whole config before saving."""
    try:
        overrides.apply(body.values)
    except ConfigError as e:
        raise HTTPException(400, str(e)) from None
    return _thresholds()


@router.delete("/thresholds", response_model=ThresholdsOut)
def reset_thresholds() -> ThresholdsOut:
    """Go back to the values in profiles.yaml."""
    overrides.reset()
    return _thresholds()
