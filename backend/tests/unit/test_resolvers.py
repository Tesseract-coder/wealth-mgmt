from datetime import date

from app.core.profiles import get_profiles
from app.data.amfi import Scheme, detect_option, detect_plan, parse_navall
from app.data.nse import Security, parse_equity_list, parse_etf_list
from app.importers.scheme_resolver import SchemeResolver, normalise_scheme, scheme_override_key
from app.importers.ticker_resolver import TickerResolver, normalise_company

CFG = get_profiles().importing

SECURITIES = (
    Security("RELIANCE", "Reliance Industries Limited", "INE002A01018", "EQ", "equity"),
    Security("HDFCBANK", "HDFC Bank Limited", "INE040A01034", "EQ", "equity"),
    Security("HDFCLIFE", "HDFC Life Insurance Company Limited", "INE795G01014", "EQ", "equity"),
    Security("LT", "Larsen & Toubro Limited", "INE018A01030", "EQ", "equity"),
    Security("NIFTYBEES", "Nifty 50", "INF204KB14I2", "ETF", "etf"),
)


def tr() -> TickerResolver:
    return TickerResolver(SECURITIES, CFG)


# --------------------------------------------------------------------------- tickers


def test_isin_wins() -> None:
    r = tr().resolve("Some Odd Name", "INE002A01018")
    assert (r.symbol, r.method) == ("RELIANCE", "isin")


def test_etf_resolves_by_isin() -> None:
    assert tr().resolve("Nippon India ETF Nifty 50 BeES", "INF204KB14I2").symbol == "NIFTYBEES"


def test_name_match_when_isin_missing() -> None:
    r = tr().resolve("Larsen and Toubro Ltd", None)
    assert (r.symbol, r.method) == ("LT", "name")


def test_symbol_column_used() -> None:
    r = tr().resolve("whatever", None, symbol_hint="hdfcbank.ns")
    assert (r.symbol, r.method) == ("HDFCBANK", "symbol")


def test_unknown_company_unresolved() -> None:
    r = tr().resolve("Acme Widgets Ltd", "INE000X01999")
    assert r.symbol is None
    assert r.method == "unresolved"


def test_ambiguous_name_not_auto_accepted() -> None:
    r = tr().resolve("HDFC", None)
    assert r.method == "unresolved"
    assert {s.symbol for s in r.suggestions} >= {"HDFCBANK"}


def test_override_beats_everything() -> None:
    r = tr().resolve(
        "Reliance Industries", "INE002A01018", overrides={"isin:INE002A01018": ("RIL", "BSE")}
    )
    assert (r.symbol, r.exchange, r.method) == ("RIL", "BSE", "override")


def test_search_by_symbol_and_name() -> None:
    assert tr().search("lt", 5)[0].symbol == "LT"
    assert tr().search("reliance", 5)[0].symbol == "RELIANCE"


def test_normalise_company() -> None:
    assert normalise_company("Larsen & Toubro Ltd.") == "larsen and toubro"


def test_real_bundled_list_resolves_core_names() -> None:
    from app.data.nse import load_securities

    real = TickerResolver(load_securities(), CFG)
    assert real.resolve("State Bank of India", None).symbol == "SBIN"
    assert real.resolve("Infosys Ltd", "INE009A01021").symbol == "INFY"


def test_parse_nse_lists() -> None:
    eq = parse_equity_list(
        "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
        "ITC,ITC Limited,EQ,23-AUG-1995,1,1,INE154A01025,1\n"
    )
    assert eq == [Security("ITC", "ITC Limited", "INE154A01025", "EQ", "equity")]
    etf = parse_etf_list(
        "Symbol,Underlying Asset,SecurityName,DateofListing,MarketLot,ISINNumber,FaceValue\n"
        "GOLDBEES,Gold,NIP GOLD BEES,01-Jan-07,1,INF204KB17I5,1\n"
    )
    assert etf[0].symbol == "GOLDBEES" and etf[0].kind == "etf"


# --------------------------------------------------------------------------- AMFI


NAVALL_8 = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

PPFAS Mutual Fund

122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;87.6555;08-Oct-2026
122640;INF879O01019;-;Parag Parikh Flexi Cap Fund;Regular Plan;Growth;79.8202;08-Oct-2026
122641;INF879O01035;INF879O01043;Parag Parikh Flexi Cap Fund;Direct Plan;IDCW;30.1;08-Oct-2026

Open Ended Schemes(Equity Scheme - Mid Cap Fund)

HDFC Mutual Fund

118989;INF179K01XQ0;-;HDFC Mid Cap Fund;Direct Plan;Growth Option;217.078;08-Oct-2026
105758;INF179K01CR2;-;HDFC Mid Cap Fund;Regular Plan;Growth Option;195.669;08-Oct-2026
"""

NAVALL_6 = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
Open Ended Schemes(Equity Scheme - Large Cap Fund)
Axis Mutual Fund
120465;INF846K01DP8;-;Axis Bluechip Fund - Direct Plan - Growth;58.12;08-Oct-2024
"""


def schemes() -> tuple[Scheme, ...]:
    return tuple(parse_navall(NAVALL_8))


def test_parse_navall_8_columns() -> None:
    s = schemes()
    assert len(s) == 5
    p = s[0]
    assert p.code == "122639"
    assert p.name == "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"
    assert (p.plan, p.option) == ("direct", "growth")
    assert p.nav == 87.6555 and p.nav_date == date(2026, 10, 8)
    assert p.category == "Equity Scheme - Flexi Cap Fund"
    assert p.amc == "PPFAS Mutual Fund"
    assert s[2].option == "idcw" and s[2].isin_reinvest == "INF879O01043"
    assert s[3].amc == "HDFC Mutual Fund"


def test_parse_navall_6_columns() -> None:
    (s,) = parse_navall(NAVALL_6)
    assert (s.code, s.plan, s.option, s.nav) == ("120465", "direct", "growth", 58.12)
    assert s.category == "Equity Scheme - Large Cap Fund"


def test_detect_plan_option() -> None:
    assert detect_plan("X Fund Regular Plan") == "regular"
    assert detect_option("X - IDCW Payout") == "idcw"
    assert detect_option("X - Cumulative") == "growth"
    assert detect_option("X Fund") is None


def sr() -> SchemeResolver:
    return SchemeResolver(schemes(), CFG)


def test_scheme_name_with_plan_and_option() -> None:
    r = sr().resolve("Parag Parikh Flexi Cap Fund Direct Growth")
    assert r.scheme is not None and r.scheme.code == "122639"
    r = sr().resolve("Parag Parikh Flexi Cap Fund Regular Growth")
    assert r.scheme is not None and r.scheme.code == "122640"
    r = sr().resolve("Parag Parikh Flexi Cap Fund - Direct Plan - IDCW")
    assert r.scheme is not None and r.scheme.code == "122641"


def test_scheme_without_plan_is_not_guessed() -> None:
    r = sr().resolve("Parag Parikh Flexi Cap Fund")
    assert r.scheme is None
    assert len(r.suggestions) >= 2


def test_renamed_scheme_suggested_not_accepted() -> None:
    r = sr().resolve("HDFC Mid-Cap Opportunities Fund Direct Growth")
    assert r.scheme is None
    assert r.suggestions[0].amfi_code == "118989"


def test_scheme_by_code_and_isin() -> None:
    assert sr().resolve("x", amfi_code="105758").method == "amfi_code"
    r = sr().resolve("x", isin="INF879O01043")
    assert r.method == "isin" and r.scheme is not None and r.scheme.code == "122641"


def test_scheme_override() -> None:
    name = "Old Name Fund Direct Growth"
    r = sr().resolve(name, overrides={scheme_override_key(name): "118989"})
    assert r.method == "override" and r.scheme is not None and r.scheme.code == "118989"


def test_normalise_scheme_aliases() -> None:
    assert normalise_scheme("Axis ELSS Tax Saver Fund Direct Growth") == "axis elss"
    assert normalise_scheme("HDFC Mid-Cap Fund") == normalise_scheme("HDFC Mid Cap Fund")


def test_scheme_search() -> None:
    assert sr().search("122639", 5)[0].amfi_code == "122639"
    assert sr().search("hdfc mid cap direct", 5)[0].amfi_code == "118989"
