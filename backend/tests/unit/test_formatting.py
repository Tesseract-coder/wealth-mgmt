from datetime import UTC, datetime

import pytest

from app.core.formatting import format_freshness, format_inr, to_ist


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "₹0.00"),
        (999, "₹999.00"),
        (1000, "₹1,000.00"),
        (123456.78, "₹1,23,456.78"),
        (12345678.9, "₹1,23,45,678.90"),
        (-1234567, "-₹12,34,567.00"),
        (None, "—"),
    ],
)
def test_format_inr(amount: float | None, expected: str) -> None:
    assert format_inr(amount) == expected


def test_format_inr_no_decimals() -> None:
    assert format_inr(1234567.89, decimals=0) == "₹12,34,568"


def test_format_freshness_converts_to_ist() -> None:
    assert format_freshness(datetime(2026, 10, 9, 10, 0, tzinfo=UTC)) == "09 Oct 2026, 3:30 PM IST"


def test_to_ist_treats_naive_as_utc() -> None:
    assert to_ist(datetime(2026, 10, 9, 10, 0)).hour == 15
