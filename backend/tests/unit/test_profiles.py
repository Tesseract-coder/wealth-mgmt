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
