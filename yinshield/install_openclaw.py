"""Helpers to scaffold YinShield's OpenClaw integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .http_api import DEFAULT_HOST, DEFAULT_PORT, generate_auth_token

DEFAULT_PLUGIN_ID = "openclaw-yinshield"
DEFAULT_PLUGIN_PACKAGE = "@serein-213/openclaw-yinshield"


def build_openclaw_plugin_entry(
    base_url: str,
    mode: str,
    auth_token: str,
    timeout_ms: int = 10000,
) -> Dict[str, Any]:
    return {
        "enabled": True,
        "config": {
            "baseUrl": base_url,
            "mode": mode,
            "authToken": auth_token,
            "timeoutMs": timeout_ms,
        },
    }


def default_openclaw_config_path() -> Path:
    return Path.home() / ".openclaw" / "openclaw.json"


def merge_openclaw_config(
    existing: Optional[Dict[str, Any]],
    plugin_id: str,
    plugin_entry: Dict[str, Any],
) -> Dict[str, Any]:
    config = dict(existing or {})
    plugins = dict(config.get("plugins") or {})
    entries = dict(plugins.get("entries") or {})
    current = dict(entries.get(plugin_id) or {})
    current_config = dict(current.get("config") or {})
    new_config = dict(plugin_entry["config"])
    current_config.update(new_config)
    current["enabled"] = plugin_entry["enabled"]
    current["config"] = current_config
    entries[plugin_id] = current
    plugins["entries"] = entries
    config["plugins"] = plugins
    return config


def write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def install_openclaw_config(
    config_path: Path,
    plugin_id: str,
    plugin_entry: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    snippet_path = config_path.with_name("yinshield-openclaw-plugin.snippet.json")

    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            write_json_file(snippet_path, {"plugins": {"entries": {plugin_id: plugin_entry}}})
            return {
                "config_path": str(config_path),
                "snippet_path": str(snippet_path),
                "updated": "false",
            }
    else:
        existing = {}

    merged = merge_openclaw_config(existing, plugin_id, plugin_entry)
    write_json_file(config_path, merged)
    return {
        "config_path": str(config_path),
        "snippet_path": None,
        "updated": "true",
    }


def make_summary(
    base_url: str,
    auth_token: str,
    config_path: Path,
    snippet_path: Optional[str],
    dry_run: bool = False,
) -> str:
    lines = [
        "YinShield OpenClaw scaffold is ready.",
        f"Plugin package: {DEFAULT_PLUGIN_PACKAGE}",
        f"Base URL: {base_url}",
        f"Auth token: {auth_token}",
        f"Config path: {config_path}",
    ]
    if dry_run:
        lines.append("Dry run only: no files were written.")
    if snippet_path:
        lines.append(f"Existing OpenClaw config was not modified safely. Apply snippet manually: {snippet_path}")
    elif not dry_run:
        lines.append("OpenClaw config was updated.")
    lines.extend(
        [
            "",
            "Next steps:",
            f"1. openclaw plugins install {DEFAULT_PLUGIN_PACKAGE}",
            f"2. openclaw plugins enable {DEFAULT_PLUGIN_ID}",
            f"3. yinshield serve --auth-token {auth_token}",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold OpenClaw config for YinShield.")
    parser.add_argument(
        "--config-path",
        default=str(default_openclaw_config_path()),
        help="OpenClaw config file path.",
    )
    parser.add_argument(
        "--base-url",
        default=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        help="YinShield local service URL.",
    )
    parser.add_argument(
        "--mode",
        choices=["placeholder", "alias"],
        default="placeholder",
        help="Default plugin mode.",
    )
    parser.add_argument(
        "--auth-token",
        help="Auth token to put in the plugin config. If omitted, one is generated.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=10000,
        help="Plugin request timeout in milliseconds.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Only print the generated config and next steps without writing files.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    auth_token = args.auth_token or generate_auth_token()
    config_path = Path(args.config_path).expanduser()
    plugin_entry = build_openclaw_plugin_entry(
        base_url=args.base_url,
        mode=args.mode,
        auth_token=auth_token,
        timeout_ms=args.timeout_ms,
    )

    if args.print_only:
        print(json.dumps({"plugins": {"entries": {DEFAULT_PLUGIN_ID: plugin_entry}}}, ensure_ascii=False, indent=2))
        print()
        print(make_summary(args.base_url, auth_token, config_path, None, dry_run=True))
        return 0

    result = install_openclaw_config(config_path, DEFAULT_PLUGIN_ID, plugin_entry)
    print(make_summary(args.base_url, auth_token, config_path, result["snippet_path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
