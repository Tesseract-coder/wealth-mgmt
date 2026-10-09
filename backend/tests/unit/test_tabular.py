from datetime import date

import pytest

from app.importers.tabular import ImportFileError, parse_date, parse_isin, parse_number, read_grid


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("₹1,23,456.78", 123456.78),
        ("1,234", 1234.0),
        ("(1,234.50)", -1234.5),
        ("-512.3", -512.3),
        ("−512.3", -512.3),
        ("Rs. 99", 99.0),
        ("12.5%", 12.5),
        (" 42 ", 42.0),
        (7, 7.0),
        (3.25, 3.25),
        ("", None),
        ("-", None),
        ("N/A", None),
        ("abc", None),
        (None, None),
        (date(2026, 1, 1), None),
    ],
)
def test_parse_number(raw: object, expected: float | None) -> None:
    assert parse_number(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("08-10-2026", date(2026, 10, 8)),
        ("08/10/2026", date(2026, 10, 8)),
        ("2026-10-08", date(2026, 10, 8)),
        ("08-Oct-2026", date(2026, 10, 8)),
        ("08 Oct 2026", date(2026, 10, 8)),
        ("not a date", None),
        (None, None),
    ],
)
def test_parse_date(raw: str | None, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_parse_isin() -> None:
    assert parse_isin(" ine002a01018 ") == "INE002A01018"
    assert parse_isin("INE002A0101") is None
    assert parse_isin("") is None


def test_csv_with_bom_and_ragged_rows() -> None:
    content = "﻿Title\n\nA,B,C\n1,2,3\n".encode()
    grid = read_grid(content, "x.csv")
    assert grid[0] == ["Title"]
    assert grid[2] == ["A", "B", "C"]


def test_semicolon_csv_detected() -> None:
    grid = read_grid(b"Name;Qty;Price\nX;1;2\nY;3;4\n", "x.csv")
    assert grid[1] == ["X", "1", "2"]


def test_cp1252_csv_decoded() -> None:
    grid = read_grid("Name,Value\nCaf\xe9,1\n".encode("cp1252"), "x.csv")
    assert grid[1][0] == "Café"


def test_old_xls_rejected_with_help() -> None:
    with pytest.raises(ImportFileError, match="Save As"):
        read_grid(b"...", "holdings.xls")


def test_unknown_extension_rejected() -> None:
    with pytest.raises(ImportFileError, match="Unsupported"):
        read_grid(b"...", "holdings.pdf")


def test_corrupt_xlsx_rejected() -> None:
    with pytest.raises(ImportFileError, match="Could not open"):
        read_grid(b"not a zip", "holdings.xlsx")
