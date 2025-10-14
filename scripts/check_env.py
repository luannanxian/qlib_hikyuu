#!/usr/bin/env python3
"""Environment readiness checker for the workstation."""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import sys
from pathlib import Path
from typing import Iterable, Tuple

MIN_PYTHON_VERSION = (3, 10)
REQUIRED_PACKAGES = ["pyqlib", "hikyuu", "lightgbm", "pandas", "numpy", "yaml"]
REQUIRED_ENV_VARS = ["QLIB_DATA_SOURCE", "QLIB_HIKYUU_INSTRUMENTS"]


def check_python() -> Tuple[bool, str]:
    current = sys.version_info[:3]
    if current >= MIN_PYTHON_VERSION:
        return True, f"Python version OK: {platform.python_version()}"
    return False, (
        "Python version "
        f"{platform.python_version()} < {'.'.join(map(str, MIN_PYTHON_VERSION))}"
    )


def check_packages(verbose: bool = False) -> Tuple[bool, str]:
    ok = True
    messages = []
    for name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(name)
            if verbose:
                messages.append(f"Package OK: {name}")
        except Exception as exc:
            ok = False
            messages.append(f"Package missing: {name} ({exc})")
    return ok, "\n".join(messages) if messages else "All packages present"


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
    return ok, "\n".join(messages) if messages else "No environment variables checked"


def check_paths() -> Tuple[bool, str]:
    candidates = [os.environ.get("QLIB_HIKYUU_DATA_PATH"), os.environ.get("HKU_HOME"), os.environ.get("HKU_LOG_DIR")]
    ok = True
    messages = []
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.exists():
            messages.append(f"Path OK: {path}")
        else:
            ok = False
            messages.append(f"Path missing: {path}")
    if not messages:
        messages.append("No special data paths configured")
    return ok, "\n".join(messages)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check runtime environment")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    checks = [
        ("Python", check_python()),
        ("Packages", check_packages(args.verbose)),
        ("Env Vars", check_env_vars()),
        ("Paths", check_paths()),
    ]

    failed = False
    for label, (ok, message) in checks:
        status = "OK" if ok else "FAIL"
        print(f"[{status:<4}] {label}")
        print(message)
        print()
        failed |= not ok
    if failed:
        print("Environment check failed. See messages above.")
        return 1
    print("Environment check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
