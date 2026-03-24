#!/usr/bin/env python
"""Sync Python and npm package versions for a release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PYTHON_INIT = ROOT / "yinshield" / "__init__.py"
NPM_PACKAGE = ROOT / "openclaw-plugin" / "package.json"


def update_python_version(version: str) -> None:
    content = PYTHON_INIT.read_text(encoding="utf-8")
    updated = re.sub(r'__version__\s*=\s*"([^"]+)"', f'__version__ = "{version}"', content, count=1)
    if updated == content:
        raise ValueError(f"Could not update __version__ in {PYTHON_INIT}")
    PYTHON_INIT.write_text(updated, encoding="utf-8")


def update_npm_version(version: str) -> None:
    payload = json.loads(NPM_PACKAGE.read_text(encoding="utf-8"))
    payload["version"] = version
    NPM_PACKAGE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help="Version to apply, for example 0.1.0")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    update_python_version(args.version)
    update_npm_version(args.version)
    print(args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
