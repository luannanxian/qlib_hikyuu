#!/usr/bin/env python3
"""Cross-platform environment checks for GA 4.3 compatibility validation."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


CHECK_ITEMS: List[Tuple[str, callable]] = []


def _register(name: str):
    def decorator(func):
        CHECK_ITEMS.append((name, func))
        return func

    return decorator


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


@_register("python_version")
def _check_python() -> Dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
    }


@_register("platform")
def _check_platform() -> Dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }


@_register("dependencies")
def _check_dependencies() -> Dict[str, bool]:
    modules = ["hikyuu", "qlib", "lightgbm", "streamlit"]
    status = {}
    for module in modules:
        try:
            __import__(module)
            status[module] = True
        except Exception:
            status[module] = False
    return status


@_register("cli_tools")
def _check_cli_tools() -> Dict[str, bool]:
    tools = ["git", "conda", "python"]
    return {tool: _command_exists(tool) for tool in tools}


@_register("streamlit_smoke")
def _check_streamlit() -> Dict[str, bool]:
    streamlit_file = Path("prototypes/streamlit_dashboard.py")
    return {
        "prototype_exists": streamlit_file.exists(),
    }


def run_checks() -> Dict[str, Dict[str, object]]:
    results: Dict[str, Dict[str, object]] = {}
    for name, func in CHECK_ITEMS:
        try:
            results[name] = func()
        except Exception as exc:  # pragma: no cover
            results[name] = {"error": str(exc)}
    return results


def main() -> int:
    results = run_checks()
    for section, data in results.items():
        print(f"[{section}]")
        for key, value in data.items():
            print(f"{key}: {value}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

