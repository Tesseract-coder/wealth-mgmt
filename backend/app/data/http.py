"""Shared HTTP client for NSE / AMFI / mfapi: rate-limited, with retries and backoff."""

import logging
import threading
import time

import httpx

from app.core.profiles import SourceKey, get_profiles
from app.data.rate_limit import limiter

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) PortfolioAnalyzer/0.1 (personal, non-commercial)"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """A download failed after all retries. The message is safe to show to the user."""


_client: httpx.Client | None = None
_client_lock = threading.Lock()


def client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                timeout=get_profiles().data.http_timeout_seconds,
                follow_redirects=True,
            )
        return _client


def set_client(c: httpx.Client | None) -> None:
    """Swap the client (tests use an httpx.MockTransport)."""
    global _client
    with _client_lock:
        _client = c


def get_bytes(source: SourceKey, url: str) -> bytes:
    cfg = get_profiles().data
    backoff = cfg.http_backoff_seconds
    last = ""
    for attempt in range(cfg.http_retries + 1):
        limiter(source).acquire()
        try:
            r = client().get(url)
        except httpx.HTTPError as e:
            last = f"network error: {e.__class__.__name__}"
        else:
            if r.status_code == 200:
                return r.content
            last = f"HTTP {r.status_code}"
            if r.status_code not in RETRY_STATUSES:
                break
            if r.status_code == 429:
                limiter(source).penalise(backoff * 2**attempt)
        if attempt < cfg.http_retries:
            delay = backoff * 2**attempt
            logger.info("%s: %s (%s); retrying in %.1fs", source, url, last, delay)
            time.sleep(delay)
    raise FetchError(f"{source}: could not download {url} ({last})")
