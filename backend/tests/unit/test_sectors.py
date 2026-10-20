import csv

from app.analysis.fundamental import sector_of
from app.core.settings import get_settings
from app.data.sectors import YAHOO_INDUSTRY, YAHOO_SECTOR, nse_sector

NSE_SECTORS = {
    "Automobile and Auto Components", "Capital Goods", "Chemicals", "Construction",
    "Construction Materials", "Consumer Durables", "Consumer Services", "Diversified",
    "Fast Moving Consumer Goods", "Financial Services", "Forest Materials", "Healthcare",
    "Information Technology", "Media Entertainment & Publication", "Metals & Mining",
    "Oil Gas & Consumable Fuels", "Power", "Realty", "Services", "Telecommunication",
    "Textiles", "Utilities",
}  # fmt: skip


def test_every_mapping_lands_on_an_nse_sector() -> None:
    assert set(YAHOO_INDUSTRY.values()) <= NSE_SECTORS
    assert set(YAHOO_SECTOR.values()) <= NSE_SECTORS


def test_the_nifty_500_list_uses_the_same_names() -> None:
    path = get_settings().fallback_data_dir / "ind_nifty500list.csv"
    assert {r["Industry"] for r in csv.DictReader(path.open())} <= NSE_SECTORS


def test_industry_first_then_sector() -> None:
    assert nse_sector("Technology", "Information Technology Services") == "Information Technology"
    assert nse_sector("Basic Materials", "Steel") == "Metals & Mining"
    assert nse_sector("Industrials", "A New Yahoo Industry") == "Capital Goods"
    assert nse_sector("Something Else", None) == "Something Else"
    assert nse_sector(None, None) is None


def test_yahoo_sourced_sector_shows_nse_name_but_keeps_its_peer_group() -> None:
    info = {"sector": "Technology", "industry": "Software - Application"}
    assert sector_of("NOTINNIFTY500XYZ", info) == ("Information Technology", "yahoo:Technology")
