#!/usr/bin/env python3
"""
Environment readiness checker for the Hikyuu × Qlib personal workstation.

The script verifies:
    1. Python runtime version
    2. Required third-party packages availability
    3. Key environment variables
    4. Essential directory accessibility

Usage:
    python scripts/check_env.py --verbose
"""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import sys
from pathlib import Path
from typing import Iterable, Tuple

MIN_PYTHON_VERSION = (3, 10)
REQUIRED_PACKAGES = [
    "pyqlib",
    "hikyuu",
    "lightgbm",
    "pandas",
    "numpy",
    "yaml",
]

REQUIRED_ENV_VARS = [
    "QLIB_DATA_SOURCE",
    "QLIB_HIKYUU_INSTRUMENTS",
]


def check_python_version() -> Tuple[bool, str]:
    current = sys.version_info[:3]
    if current >= MIN_PYTHON_VERSION:
        return True, f"Python version OK: {platform.python_version()}"
    return (
        False,
        f"Python version {platform.python_version()} is below the required "
        f"{'.'.join(map(str, MIN_PYTHON_VERSION))}",
    )


def check_packages(verbose: bool = False) -> Tuple[bool, str]:
    missing: Iterable[str] = []
    messages = []
    ok = True
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            if verbose:
                messages.append(f"Package OK: {pkg}")
        except Exception as exc:  # pragma: no cover
            ok = False
            messages.append(f"Package missing: {pkg} ({exc})")
    return ok, "\n".join(messages) if messages else "All packages loaded."


def check_env_vars() -> Tuple[bool, str]:
    ok = True
    messages = []
    for key in REQUIRED_ENV_VARS:
        value = os.environ.get(key)
        if value:
            messages.append(f"{key}={value}")
        else:
            ok = False
            messages.append(f"{key} is not set")
    return ok, "\n".join(messages)


def check_paths() -> Tuple[bool, str]:
    ok = True
    messages = []
    potential_paths = [
        os.environ.get("QLIB_HIKYUU_DATA_PATH", ""),
        os.environ.get("QLIB_HIKYUU_HOME", ""),
    ]
    for path in potential_paths:
        if not path:
            continue
        p = Path(path).expanduser()
        if p.exists():
            messages.append(f"Path exists: {p}")
        else:
            ok = False
            messages.append(f"Path missing: {p}")
    if not messages:
        messages.append("No specific data paths configured.")
    return ok, "\n".join(messages)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check runtime environment.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed package information.",
    )
    args = parser.parse_args()

    checks = [
        ("Python", check_python_version()),
        ("Packages", check_packages(verbose=args.verbose)),
        ("Environment Variables", check_env_vars()),
        ("Paths", check_paths()),
    ]

    has_error = False
    for label, (ok, message) in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status:<4}] {label}")
        print(message.strip() or "-")
        print()
        has_error |= not ok

    if has_error:
        print("Environment check failed. Please resolve the issues above.")
        return 1
    print("Environment check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

