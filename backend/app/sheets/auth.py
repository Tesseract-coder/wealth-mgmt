"""Service-account key handling. The key file stays in secrets/ (gitignored); only the
service account's e-mail address ever leaves this module, never the private key.

This is a Google Cloud *robot* account that you share one sheet with. It has nothing to do
with your broker, and the app never asks for any broker or Google password."""

import contextlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from google.auth import crypt, jwt

from app.core.settings import BACKEND_DIR, get_settings

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_KEY_PATH = BACKEND_DIR.parent / "secrets" / "service-account.json"
MAX_KEY_BYTES = 64 * 1024
_REQUIRED = ("type", "client_email", "private_key", "token_uri")


class ServiceAccountError(RuntimeError):
    """The key file is missing or unusable; the message is safe to show."""


def key_path() -> Path:
    p = get_settings().google_service_account_file
    if p is None:
        return DEFAULT_KEY_PATH
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


def parse_key(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_KEY_BYTES:
        raise ServiceAccountError("That file is too large to be a service-account key")
    try:
        info = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceAccountError("The key file isn't valid JSON") from None
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise ServiceAccountError(
            'This isn\'t a service-account key (its "type" should be "service_account"). '
            "Create one under IAM → Service accounts → Keys → Add key → JSON."
        )
    missing = [k for k in _REQUIRED if not info.get(k)]
    if missing:
        raise ServiceAccountError(f"The key file is missing: {', '.join(missing)}")
    token_host = urlsplit(str(info["token_uri"])).hostname or ""
    if not token_host.endswith(".googleapis.com"):
        raise ServiceAccountError("The key's token_uri isn't a googleapis.com address")
    try:
        crypt.RSASigner.from_service_account_info(info)  # type: ignore[no-untyped-call]
    except Exception:
        raise ServiceAccountError("The key's private_key can't be read") from None
    return info


def load_key() -> dict[str, Any]:
    p = key_path()
    if not p.is_file():
        raise ServiceAccountError(
            f"No service-account key found at {p}. Upload it in Settings → Google Sheets, "
            "or set GOOGLE_SERVICE_ACCOUNT_FILE in .env."
        )
    return parse_key(p.read_bytes())


def save_key(content: bytes) -> dict[str, Any]:
    """Validate and store an uploaded key at the configured path, readable only by you."""
    info = parse_key(content)
    p = key_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    tmp.replace(p)
    reset_tokens()
    return info


@dataclass(frozen=True)
class KeyStatus:
    configured: bool
    path: str
    client_email: str | None
    project_id: str | None
    error: str | None


def key_status() -> KeyStatus:
    p = key_path()
    if not p.is_file():
        return KeyStatus(False, str(p), None, None, None)
    try:
        info = load_key()
    except ServiceAccountError as e:
        return KeyStatus(False, str(p), None, None, str(e))
    return KeyStatus(True, str(p), info["client_email"], info.get("project_id"), None)


class TokenSource:
    """OAuth access tokens for the service account (signed JWT exchanged at Google's token
    endpoint), cached until a minute before they expire."""

    def __init__(self, info: dict[str, Any], http: httpx.Client, clock: Any = time.time) -> None:
        self._info = info
        self._http = http
        self._clock = clock
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    @property
    def email(self) -> str:
        return str(self._info["client_email"])

    def token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token and now < self._expires - 60:
                return self._token
            signer = crypt.RSASigner.from_service_account_info(self._info)  # type: ignore[no-untyped-call]
            iat = int(now)
            payload = {
                "iss": self.email,
                "scope": SCOPE,
                "aud": self._info["token_uri"],
                "iat": iat,
                "exp": iat + 3600,
            }
            assertion = jwt.encode(signer, payload).decode()  # type: ignore[no-untyped-call]
            try:
                r = self._http.post(
                    self._info["token_uri"],
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
            except httpx.HTTPError as e:
                raise ServiceAccountError(
                    f"Couldn't reach Google to sign in the service account ({e.__class__.__name__})"
                ) from None
            if r.status_code != 200:
                detail = ""
                with contextlib.suppress(ValueError):
                    detail = r.json().get("error_description") or r.json().get("error") or ""
                raise ServiceAccountError(
                    f"Google refused the service-account key (HTTP {r.status_code}"
                    f"{': ' + detail if detail else ''}). If you deleted or rotated the key in "
                    "Google Cloud, upload the new one."
                )
            body = r.json()
            self._token = str(body["access_token"])
            self._expires = now + float(body.get("expires_in", 3600))
            return self._token


_sources: dict[str, TokenSource] = {}
_sources_lock = threading.Lock()


def token_source(http: httpx.Client) -> TokenSource:
    info = load_key()
    with _sources_lock:
        src = _sources.get(info["client_email"])
        if src is None or src._http is not http:
            src = _sources[info["client_email"]] = TokenSource(info, http)
        return src


def reset_tokens() -> None:
    with _sources_lock:
        _sources.clear()
