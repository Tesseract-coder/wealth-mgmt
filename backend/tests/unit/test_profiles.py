from pathlib import Path

import pytest
import yaml

from app.core.profiles import ConfigError, load_profiles
from app.core.settings import get_settings

REAL = get_settings().profiles_path


def _write(tmp_path: Path, data: object) -> Path:
    p = tmp_path / "profiles.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_bundled_config_is_valid() -> None:
    cfg = load_profiles(REAL)
    assert cfg.defaults.risk == "medium"
    assert cfg.defaults.style is None


def test_medium_risk_matches_spec() -> None:
    m = load_profiles(REAL).risk_levels["medium"]
    assert (m.max_weight_per_stock, m.max_weight_per_sector) == (0.12, 0.30)
    assert m.stop_loss_atr_multiple == 2.0
    assert m.min_market_cap_cr == 5000
    assert (m.max_debt_to_equity, m.max_beta, m.buy_threshold) == (1.0, 1.3, 70)


def test_style_weights_match_spec() -> None:
    s = load_profiles(REAL).styles
    assert [s[k].technical_weight for k in ("intraday", "swing", "positional", "long_term")] == [
        0.9,
        0.7,
        0.5,
        0.2,
    ]


def test_weights_not_summing_to_one_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(REAL.read_text())
    data["styles"]["swing"]["technical_weight"] = 0.9
    with pytest.raises(ConfigError, match="must equal 1.0"):
        load_profiles(_write(tmp_path, data))


def test_missing_risk_level_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(REAL.read_text())
    del data["risk_levels"]["high"]
    with pytest.raises(ConfigError, match="high"):
        load_profiles(_write(tmp_path, data))


def test_invalid_yaml_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("styles: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_profiles(p)


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_profiles(tmp_path / "nope.yaml")


def _data_variant(tmp_path: Path, **changes: object) -> Path:
    raw = yaml.safe_load(REAL.read_text())
    raw["data"].update(changes)
    return _write(tmp_path, raw)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"rate_limits_per_minute": {"yahoo": 60}}, "rate_limits_per_minute is missing"),
        ({"rate_limits_per_minute": {"yahoo": 0, "mfapi": 1, "nse": 1, "amfi": 1}}, "positive"),
        ({"refresh_time_ist": "15:00"}, "after market_close_ist"),
        ({"nav_refresh_time_ist": "25:00"}, "nav_refresh_time_ist"),
        ({"reference_min_rows": {"nse_equity": 1}}, "reference_min_rows is missing"),
    ],
)
def test_data_section_validation(tmp_path: Path, changes: dict[str, object], match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_profiles(_data_variant(tmp_path, **changes))


def test_data_cutoff_times() -> None:
    d = load_profiles(REAL).data
    assert (d.price_ready.hour, d.price_ready.minute) == (16, 0)
    assert (d.nav_ready.hour, d.nav_ready.minute) == (23, 30)


def _variant(tmp_path: Path, section: str, path: list[str], value: object) -> Path:
    raw = yaml.safe_load(REAL.read_text())
    node = raw[section]
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return _write(tmp_path, raw)


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (["periods", "sma"], [20, 50], "must include 50 and 200"),
        (["periods", "ema"], [21, 9], r"\[fast, slow\]"),
        (["periods", "macd"], {"fast": 26, "slow": 12, "signal": 9}, "fast must be below"),
        (["thresholds", "rsi_neutral_band"], [25, 55], "rsi_oversold < rsi_neutral_band"),
        (["thresholds", "adx_weak"], 30, "adx_weak must not exceed adx_trending"),
        (["thresholds", "volume_surge"], 0.5, "greater than 1"),
    ],
)
def test_technical_section_validation(
    tmp_path: Path, path: list[str], value: object, match: str
) -> None:
    with pytest.raises(ConfigError, match=match):
        load_profiles(_variant(tmp_path, "technical", path, value))


def test_benchmarks_need_nifty50(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nifty50"):
        load_profiles(_variant(tmp_path, "data", ["benchmarks"], {"nifty500": "^CRSLDX"}))


def test_delivery_lookback_covers_average(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="delivery_avg \\+ 1"):
        load_profiles(_variant(tmp_path, "technical", ["delivery_lookback_sessions"], 20))
