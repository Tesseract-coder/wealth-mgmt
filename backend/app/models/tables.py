"""SQLModel tables. Later phases add holdings, snapshots, price cache, jobs, etc."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.formatting import now_ist


class UserProfile(SQLModel, table=True):
    """Single-row table (id=1) holding the investor's chosen style and risk."""

    id: int = Field(default=1, primary_key=True)
    style: str | None = None  # None until onboarding is complete
    risk: str = "medium"
    custom_technical_weight: float = 0.5
    gsheet_url: str | None = None
    updated_at: datetime = Field(default_factory=now_ist)
