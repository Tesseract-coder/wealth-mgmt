import httpx
import pytest

from app.data import http, rate_limit
from app.data.http import FetchError, get_bytes
from app.data.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def test_rate_limiter_spaces_calls() -> None:
    clk = FakeClock()
    lim = RateLimiter(60, clock=clk, sleep=clk.sleep)  # one per second
    assert lim.acquire() == 0
    assert lim.acquire() == pytest.approx(1.0)
    clk.t += 5  # idle time isn't banked into bursts beyond one slot
    assert lim.acquire() == 0
    assert lim.acquire() == pytest.approx(1.0)


def test_rate_limiter_penalty_pushes_next_slot() -> None:
    clk = FakeClock()
    lim = RateLimiter(60, clock=clk, sleep=clk.sleep)
    lim.acquire()
    lim.penalise(10)
    assert lim.acquire() == pytest.approx(10.0)


def test_limiter_registry_uses_config() -> None:
    rate_limit.reset_limiters()
    assert rate_limit.limiter("nse").interval == pytest.approx(6.0)  # 10/min in profiles.yaml


def _mock(handler):  # type: ignore[no-untyped-def]
    http.set_client(httpx.Client(transport=httpx.MockTransport(handler)))


def test_get_bytes_retries_server_errors() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, content=b"ok")

    _mock(handler)
    assert get_bytes("nse", "https://example.test/x") == b"ok"
    assert len(calls) == 3


def test_get_bytes_does_not_retry_404() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    _mock(handler)
    with pytest.raises(FetchError, match="HTTP 404"):
        get_bytes("nse", "https://example.test/x")
    assert len(calls) == 1


def test_get_bytes_gives_up_on_network_errors() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    _mock(handler)
    with pytest.raises(FetchError, match="network error"):
        get_bytes("amfi", "https://example.test/x")


def test_http_429_penalises_the_source() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    _mock(handler)
    before = rate_limit._limiters["mfapi"]._next
    with pytest.raises(FetchError, match="429"):
        get_bytes("mfapi", "https://example.test/x")
    assert rate_limit._limiters["mfapi"]._next > before
