#!/usr/bin/env python
"""Verify release versions are aligned across package manifests."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON_INIT = ROOT / "yinshield" / "__init__.py"
NPM_PACKAGE = ROOT / "openclaw-plugin" / "package.json"


def read_python_version() -> str:
    content = PYTHON_INIT.read_text(encoding="utf-8")
    matched = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not matched:
        raise ValueError(f"Could not find __version__ in {PYTHON_INIT}")
    return matched.group(1)


def read_npm_version() -> str:
    payload = json.loads(NPM_PACKAGE.read_text(encoding="utf-8"))
    version = payload.get("version")
    if not isinstance(version, str):
        raise ValueError(f"Could not find string version in {NPM_PACKAGE}")
    return version


def main() -> int:
    python_version = read_python_version()
    npm_version = read_npm_version()

    if python_version != npm_version:
        print(
            json.dumps(
                {
                    "ok": False,
                    "python_version": python_version,
                    "npm_version": npm_version,
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "version": python_version,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
