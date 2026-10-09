import pytest

from app.core.profiles import get_profiles
from app.importers import column_mapper
from app.importers.column_mapper import detect, header_signature, manual
from app.importers.tabular import Grid

CFG = get_profiles().importing

GROWW_STOCKS: Grid = [
    ["Name", "Demo Investor"],
    ["Unique Client Code", "0000000000"],
    [],
    ["Holdings statement as on 08-10-2026"],
    ["Summary"],
    ["Invested Value", 1000],
    ["Closing Value", 1200],
    ["Unrealised P&L", 200],
    [],
    [
        "Stock Name",
        "ISIN",
        "Quantity",
        "Average buy price",
        "Buy value",
        "Closing price",
        "Closing value",
        "Unrealised P&L",
    ],
    ["Reliance Industries Ltd", "INE002A01018", 10, 2400, 24000, 2800, 28000, 4000],
]


def test_finds_header_below_title_and_summary_rows() -> None:
    r = detect(GROWW_STOCKS, "stocks", CFG)
    assert r.header_row == 9
    assert r.complete
    assert r.mapping == {
        "name": 0,
        "isin": 1,
        "quantity": 2,
        "avg_price": 3,
        "invested": 4,
        "close_price": 5,
        "current_value": 6,
        "unrealised_pnl": 7,
    }


def test_renamed_headers_still_map() -> None:
    grid: Grid = [
        ["Report"],
        ["Company", "ISIN Code", "Qty.", "Avg. Cost (₹)", "LTP", "Current Value (₹)", "P&L"],
        ["X", "INE002A01018", "1", "2", "3", "3", "1"],
    ]
    r = detect(grid, "stocks", CFG)
    assert r.header_row == 1
    assert r.mapping["name"] == 0
    assert r.mapping["quantity"] == 2
    assert r.mapping["avg_price"] == 3
    assert r.mapping["close_price"] == 4
    assert r.mapping["current_value"] == 5
    assert r.mapping["unrealised_pnl"] == 6


def test_buy_value_not_confused_with_closing_value() -> None:
    r = detect(GROWW_STOCKS, "stocks", CFG)
    assert r.mapping["invested"] != r.mapping["current_value"]


def test_unrecognisable_headers_report_missing_fields() -> None:
    grid: Grid = [["Security", "Identifier", "Holding", "Rate"], ["X", "Y", "1", "2"]]
    r = detect(grid, "stocks", CFG)
    assert not r.complete
    assert set(r.missing_required) == {"name", "quantity", "avg_price"}
    assert r.header_row == 0
    assert r.headers == ["Security", "Identifier", "Holding", "Rate"]


def test_mf_headers() -> None:
    grid: Grid = [
        ["Personal Details"],
        [
            "Scheme Name",
            "AMC",
            "Category",
            "Sub-category",
            "Folio No.",
            "Source",
            "Units",
            "Invested Value",
            "Current Value",
            "Returns",
            "XIRR",
        ],
    ]
    r = detect(grid, "mf", CFG)
    assert r.header_row == 1
    assert r.mapping["scheme_name"] == 0
    assert r.mapping["folio"] == 4
    assert r.mapping["units"] == 6
    assert r.mapping["invested"] == 7
    assert r.mapping["current_value"] == 8


def test_manual_mapping_validates() -> None:
    grid: Grid = [["A", "B", "C"], ["x", "1", "2"]]
    r = manual(grid, "stocks", 0, {"name": 0, "quantity": 1, "avg_price": 2})
    assert r.complete
    with pytest.raises(ValueError, match="outside"):
        manual(grid, "stocks", 0, {"name": 5})
    with pytest.raises(ValueError, match="same column"):
        manual(grid, "stocks", 0, {"name": 0, "quantity": 0})
    with pytest.raises(ValueError, match="Unknown"):
        manual(grid, "stocks", 0, {"colour": 0})
    with pytest.raises(ValueError, match="outside the file"):
        manual(grid, "stocks", 9, {"name": 0})


def test_manual_mapping_reports_missing_required() -> None:
    r = manual([["A", "B"]], "stocks", 0, {"name": 0})
    assert set(r.missing_required) == {"quantity", "avg_price"}


def test_signature_ignores_case_and_punctuation_but_not_kind() -> None:
    a = header_signature("stocks", ["Stock Name", "Qty."])
    assert a == header_signature("stocks", ["stock name", "qty"])
    assert a != header_signature("mf", ["Stock Name", "Qty."])


def test_normalise_header() -> None:
    assert column_mapper.normalise_header("Avg. Cost (₹)") == "avg cost"
