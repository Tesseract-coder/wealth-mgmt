"""Thresholds you edit in Settings, saved to a local YAML file layered over profiles.yaml.

Only the fields listed in EDITABLE can be changed here; everything else stays in
profiles.yaml. The merged config is validated before the file is written, so a bad value
never reaches the scoring code."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.profiles import (
    RISK_KEYS,
    STYLE_KEYS,
    ConfigError,
    Profiles,
    deep_merge,
    read_yaml,
    reload_profiles,
)
from app.core.settings import get_settings


@dataclass(frozen=True)
class Editable:
    path: str  # dotted, e.g. "risk_levels.medium.buy_threshold"
    group: str
    label: str
    unit: str  # "fraction" (shown as %), "score", "x", "cr", "ratio"
    nullable: bool = False


_RISK_FIELDS: list[tuple[str, str, str, bool]] = [
    ("max_weight_per_stock", "Max weight per stock", "fraction", False),
    ("max_weight_per_sector", "Max weight per sector", "fraction", False),
    ("buy_threshold", "Buy threshold (composite score)", "score", False),
    ("stop_loss_atr_multiple", "Stop-loss distance (× ATR)", "x", False),
    ("min_market_cap_cr", "Minimum market cap (₹ Cr)", "cr", False),
    ("max_debt_to_equity", "Max debt / equity (blank = no limit)", "ratio", True),
    ("max_beta", "Max beta (blank = no limit)", "ratio", True),
]

EDITABLE: list[Editable] = [
    *(
        Editable(f"risk_levels.{rk}.{f}", f"Risk: {rk}", label, unit, nullable)
        for rk in RISK_KEYS
        for f, label, unit, nullable in _RISK_FIELDS
    ),
    *(
        Editable(
            f"styles.{sk}.technical_weight", "Style weights", f"{sk}: technical weight", "fraction"
        )
        for sk in STYLE_KEYS
        if sk != "custom"  # custom uses the weight saved in your profile
    ),
    Editable(
        "signals.strong_buy_margin",
        "Signal bands",
        "Strong Buy margin above buy threshold",
        "score",
    ),
    Editable("signals.hold_floor", "Signal bands", "Hold floor (below = Reduce)", "score"),
    Editable("signals.reduce_floor", "Signal bands", "Reduce floor (below = Sell)", "score"),
]
BY_PATH = {e.path: e for e in EDITABLE}


def get_path(d: Any, path: str) -> Any:
    for part in path.split("."):
        d = d[part] if isinstance(d, dict) else getattr(d, part)
    return d


def _set(d: dict[str, Any], path: str, value: Any) -> None:
    *head, last = path.split(".")
    for part in head:
        d = d.setdefault(part, {})
    d[last] = value


def _override_path() -> Path:
    return get_settings().profiles_override_path


def current_overrides() -> dict[str, Any]:
    p = _override_path()
    return read_yaml(p) if p.exists() else {}


def flat_overrides() -> dict[str, Any]:
    o = current_overrides()
    out: dict[str, Any] = {}
    for e in EDITABLE:
        try:
            out[e.path] = get_path(o, e.path)
        except (KeyError, TypeError):
            continue
    return out


def base_value(path: str) -> Any:
    return get_path(read_yaml(get_settings().profiles_path), path)


def apply(values: dict[str, float | None]) -> Profiles:
    """Merge `values` into the override file, validate the result, write it, reload."""
    unknown = sorted(set(values) - set(BY_PATH))
    if unknown:
        raise ConfigError(f"These settings can't be edited here: {', '.join(unknown)}")
    over = current_overrides()
    for path, v in values.items():
        e = BY_PATH[path]
        if v is None and not e.nullable:
            raise ConfigError(f"{e.label} needs a value")
        _set(over, path, v)
        if path.startswith("styles.") and v is not None:
            # The two weights must add up to 1; keep them in step.
            _set(over, path.replace("technical_weight", "fundamental_weight"), round(1 - v, 6))
    _validate(over)
    _write(over)
    return reload_profiles()


def reset() -> Profiles:
    p = _override_path()
    if p.exists():
        p.unlink()
    return reload_profiles()


def _validate(over: dict[str, Any]) -> None:
    from pydantic import ValidationError

    merged = deep_merge(read_yaml(get_settings().profiles_path), over)
    try:
        Profiles.model_validate(merged)
    except ValidationError as e:
        msgs = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            label = BY_PATH[loc].label if loc in BY_PATH else loc
            msgs.append(f"{label}: {err['msg']}")
        raise ConfigError("; ".join(msgs)) from None


def _write(over: dict[str, Any]) -> None:
    p = _override_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Thresholds edited in Settings. Layered over config/profiles.yaml.\n"
        "# Delete this file (or use Reset in Settings) to go back to the defaults.\n"
    )
    p.write_text(header + yaml.safe_dump(over, sort_keys=True), encoding="utf-8")
