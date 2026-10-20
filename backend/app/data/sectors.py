"""Yahoo Finance's industry → NSE's sector names, so stocks outside the Nifty 500 (whose sector
comes from Yahoo) are grouped with the rest instead of under a second set of names
("Technology" next to "Information Technology").

Only the sector shown and used for portfolio weights. Peer medians keep Yahoo's own grouping.
"""

YAHOO_INDUSTRY: dict[str, str] = {
    # Basic Materials
    "Agricultural Inputs": "Chemicals",
    "Aluminum": "Metals & Mining",
    "Building Materials": "Construction Materials",
    "Chemicals": "Chemicals",
    "Coking Coal": "Oil Gas & Consumable Fuels",
    "Copper": "Metals & Mining",
    "Gold": "Metals & Mining",
    "Lumber & Wood Production": "Forest Materials",
    "Other Industrial Metals & Mining": "Metals & Mining",
    "Other Precious Metals & Mining": "Metals & Mining",
    "Paper & Paper Products": "Forest Materials",
    "Silver": "Metals & Mining",
    "Specialty Chemicals": "Chemicals",
    "Steel": "Metals & Mining",
    # Communication Services
    "Advertising Agencies": "Media Entertainment & Publication",
    "Broadcasting": "Media Entertainment & Publication",
    "Electronic Gaming & Multimedia": "Media Entertainment & Publication",
    "Entertainment": "Media Entertainment & Publication",
    "Internet Content & Information": "Consumer Services",
    "Publishing": "Media Entertainment & Publication",
    "Telecom Services": "Telecommunication",
    # Consumer Cyclical
    "Apparel Manufacturing": "Textiles",
    "Apparel Retail": "Consumer Services",
    "Auto & Truck Dealerships": "Automobile and Auto Components",
    "Auto Manufacturers": "Automobile and Auto Components",
    "Auto Parts": "Automobile and Auto Components",
    "Department Stores": "Consumer Services",
    "Footwear & Accessories": "Consumer Durables",
    "Furnishings, Fixtures & Appliances": "Consumer Durables",
    "Gambling": "Consumer Services",
    "Home Improvement Retail": "Consumer Services",
    "Internet Retail": "Consumer Services",
    "Leisure": "Consumer Services",
    "Lodging": "Consumer Services",
    "Luxury Goods": "Consumer Durables",
    "Packaging & Containers": "Capital Goods",
    "Personal Services": "Consumer Services",
    "Recreational Vehicles": "Automobile and Auto Components",
    "Residential Construction": "Realty",
    "Resorts & Casinos": "Consumer Services",
    "Restaurants": "Consumer Services",
    "Specialty Retail": "Consumer Services",
    "Textile Manufacturing": "Textiles",
    "Travel Services": "Consumer Services",
    # Consumer Defensive
    "Beverages - Brewers": "Fast Moving Consumer Goods",
    "Beverages - Non-Alcoholic": "Fast Moving Consumer Goods",
    "Beverages - Wineries & Distilleries": "Fast Moving Consumer Goods",
    "Confectioners": "Fast Moving Consumer Goods",
    "Discount Stores": "Consumer Services",
    "Education & Training Services": "Consumer Services",
    "Farm Products": "Fast Moving Consumer Goods",
    "Food Distribution": "Fast Moving Consumer Goods",
    "Grocery Stores": "Consumer Services",
    "Household & Personal Products": "Fast Moving Consumer Goods",
    "Packaged Foods": "Fast Moving Consumer Goods",
    "Tobacco": "Fast Moving Consumer Goods",
    # Energy
    "Oil & Gas Drilling": "Oil Gas & Consumable Fuels",
    "Oil & Gas E&P": "Oil Gas & Consumable Fuels",
    "Oil & Gas Equipment & Services": "Oil Gas & Consumable Fuels",
    "Oil & Gas Integrated": "Oil Gas & Consumable Fuels",
    "Oil & Gas Midstream": "Oil Gas & Consumable Fuels",
    "Oil & Gas Refining & Marketing": "Oil Gas & Consumable Fuels",
    "Thermal Coal": "Oil Gas & Consumable Fuels",
    "Uranium": "Metals & Mining",
    # Industrials
    "Aerospace & Defense": "Capital Goods",
    "Airlines": "Services",
    "Airports & Air Services": "Services",
    "Building Products & Equipment": "Capital Goods",
    "Business Equipment & Supplies": "Capital Goods",
    "Conglomerates": "Diversified",
    "Consulting Services": "Services",
    "Electrical Equipment & Parts": "Capital Goods",
    "Engineering & Construction": "Construction",
    "Farm & Heavy Construction Machinery": "Capital Goods",
    "Industrial Distribution": "Services",
    "Infrastructure Operations": "Construction",
    "Integrated Freight & Logistics": "Services",
    "Marine Shipping": "Services",
    "Metal Fabrication": "Capital Goods",
    "Pollution & Treatment Controls": "Capital Goods",
    "Railroads": "Services",
    "Rental & Leasing Services": "Services",
    "Security & Protection Services": "Services",
    "Specialty Business Services": "Services",
    "Specialty Industrial Machinery": "Capital Goods",
    "Staffing & Employment Services": "Services",
    "Tools & Accessories": "Capital Goods",
    "Trucking": "Services",
    "Waste Management": "Utilities",
    # Technology
    "Communication Equipment": "Telecommunication",
    "Computer Hardware": "Information Technology",
    "Consumer Electronics": "Consumer Durables",
    "Electronic Components": "Capital Goods",
    "Electronics & Computer Distribution": "Information Technology",
    "Information Technology Services": "Information Technology",
    "Scientific & Technical Instruments": "Capital Goods",
    "Semiconductor Equipment & Materials": "Information Technology",
    "Semiconductors": "Information Technology",
    "Software - Application": "Information Technology",
    "Software - Infrastructure": "Information Technology",
    "Solar": "Capital Goods",
    # Utilities
    "Utilities - Diversified": "Power",
    "Utilities - Independent Power Producers": "Power",
    "Utilities - Regulated Electric": "Power",
    "Utilities - Regulated Gas": "Oil Gas & Consumable Fuels",
    "Utilities - Regulated Water": "Utilities",
    "Utilities - Renewable": "Power",
}

# For an industry not listed above (Yahoo adds some now and then).
YAHOO_SECTOR: dict[str, str] = {
    "Basic Materials": "Chemicals",
    "Communication Services": "Telecommunication",
    "Consumer Cyclical": "Consumer Services",
    "Consumer Defensive": "Fast Moving Consumer Goods",
    "Energy": "Oil Gas & Consumable Fuels",
    "Financial Services": "Financial Services",
    "Healthcare": "Healthcare",
    "Industrials": "Capital Goods",
    "Real Estate": "Realty",
    "Technology": "Information Technology",
    "Utilities": "Power",
}


def nse_sector(yahoo_sector: str | None, yahoo_industry: str | None) -> str | None:
    """NSE's sector name for a stock Yahoo files under this sector and industry."""
    if yahoo_industry and yahoo_industry in YAHOO_INDUSTRY:
        return YAHOO_INDUSTRY[yahoo_industry]
    if yahoo_sector in YAHOO_SECTOR:
        return YAHOO_SECTOR[yahoo_sector]
    return yahoo_sector  # unknown to us: still better shown than dropped
