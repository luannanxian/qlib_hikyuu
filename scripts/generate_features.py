#!/usr/bin/env python3
"""Generate placeholder features based on indicator template configuration."""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Dict

from scripts.config_utils import _DEFAULT_TEMPLATE, load_yaml

OUTPUT_DIR = Path("features")
DEFAULT_OUTPUT = OUTPUT_DIR / "features.csv"
DEFAULT_TEMPLATE = Path("config/templates/default_indicators.yaml")


def emit_placeholder(template: Dict[str, object], output: Path) -> None:
    random.seed(1234)
    rows = ["indicator,value"]
    for indicator in template.get("indicators", []):
        if isinstance(indicator, dict):
            name = indicator.get("type", "UNKNOWN")
        else:
            name = str(indicator)
        rows.append(f"{name},{random.random():.4f}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(rows))
    print(f"[generate-features] wrote {len(rows) - 1} indicators to {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate placeholder features.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        template = load_yaml(args.template, fallback=_DEFAULT_TEMPLATE)
    except Exception as exc:  # pragma: no cover
        print(f"[generate-features] failed to load template: {exc}")
        template = dict(_DEFAULT_TEMPLATE)
    emit_placeholder(template, args.output)
    return 0


def run_from_config(template_path: Path, output_path: Path) -> None:
    try:
        template = load_yaml(template_path, fallback=_DEFAULT_TEMPLATE)
    except Exception as exc:  # pragma: no cover
        print(f"[generate-features] failed to load template: {exc}")
        template = dict(_DEFAULT_TEMPLATE)
    emit_placeholder(template, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
