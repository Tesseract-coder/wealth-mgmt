"""Environment-driven settings (.env). Thresholds belong in profiles.yaml, not here."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'var' / 'app.db'}"
    profiles_path: Path = BACKEND_DIR / "config" / "profiles.yaml"
    # Thresholds edited in Settings, layered over profiles.yaml (gitignored, under var/).
    profiles_override_path: Path = BACKEND_DIR / "var" / "profiles.local.yaml"
    fallback_data_dir: Path = BACKEND_DIR / "data" / "fallback"
    # Refreshed copies of the NSE/AMFI lists; preferred over the bundled fallback when present.
    reference_data_dir: Path = BACKEND_DIR / "var" / "reference"
    scheduler_enabled: bool = True  # daily refresh jobs (tests turn this off)
    google_service_account_file: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"
    timezone: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
