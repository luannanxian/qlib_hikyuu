"""Utility helpers for loading configuration templates and runtime settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_DEFAULT_TEMPLATE: Dict[str, Any] = {
    "name": "basic_indicators",
    "frequency": "day",
    "indicators": [
        {"type": "EMA", "window": 5, "source": "CLOSE"},
        {"type": "EMA", "window": 10, "source": "CLOSE"},
        {"type": "RSI", "window": 14, "source": "CLOSE"},
        {"type": "VOLUME_RATIO", "window": 5},
    ],
}


def load_yaml(path: Path, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Load a YAML file if possible; otherwise return the provided fallback."""
    if not path.exists():
        if fallback is not None:
            print(f"[config] template missing ({path}), using fallback.")
            return dict(fallback)
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        if fallback is not None:
            print("[config] PyYAML not installed, using fallback template.")
            return dict(fallback)
        return {}

    with path.open() as fp:
        data = yaml.safe_load(fp) or {}
        if not isinstance(data, dict):
            raise ValueError("Template root must be a mapping")
        return data


def load_json(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    with path.open() as fp:
        return json.load(fp)


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dicts(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def load_runtime_config(paths: list[Path]) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    for path in paths:
        if path.suffix in {".json", ".JSON"}:
            data = load_json(path)
        else:
            data = load_yaml(path)
        config = merge_dicts(config, data)
    return config
