"""Command-line entrypoint for YinShield."""

from __future__ import annotations

import argparse
import os
import json
import sys
from typing import Optional

from .core import Shield
from .http_api import DEFAULT_HOST, DEFAULT_PORT, serve


def _add_common_mask_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=["placeholder", "alias"],
        default="placeholder",
        help="Replacement mode.",
    )
    parser.add_argument(
        "--strategy",
        choices=["loose", "balanced", "strict"],
        default="balanced",
        help="Detection strategy.",
    )
    parser.add_argument(
        "--session-file",
        help="Persist or reuse a session mapping file for multi-turn consistency.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mask or unmask sensitive text locally.")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Start the local YinShield HTTP bridge.")
    _add_common_mask_arguments(serve_parser)
    serve_parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host.")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port.")
    serve_parser.add_argument(
        "--auth-token",
        default=os.environ.get("YINSHIELD_AUTH_TOKEN"),
        help="Optional bearer token required by the local HTTP service.",
    )

    parser.add_argument(
        "text",
        nargs="?",
        help="Text to process. If omitted, YinShield reads from stdin.",
    )
    parser.add_argument(
        "--unmask",
        action="store_true",
        help="Restore placeholders using the JSON mapping from --mapping.",
    )
    parser.add_argument(
        "--mapping",
        help="JSON mapping used for unmasking or as a seed mapping for masking.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON object instead of plain text.",
    )
    _add_common_mask_arguments(parser)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        return serve(
            host=args.host,
            port=args.port,
            mode=args.mode,
            strategy=args.strategy,
            session_file=args.session_file,
            auth_token=args.auth_token,
        )

    text = args.text if args.text is not None else sys.stdin.read()
    shield = Shield(mode=args.mode, strategy=args.strategy)
    if args.session_file:
        try:
            shield.load_session(args.session_file)
        except FileNotFoundError:
            pass

    if args.unmask:
        if not args.mapping:
            parser.error("--mapping is required with --unmask")
        mapping = json.loads(args.mapping)
        restored = shield.unmask(text, mapping)
        if args.json:
            print(json.dumps({"text": restored}, ensure_ascii=False, indent=2))
        else:
            print(restored)
        return 0

    seed_mapping = json.loads(args.mapping) if args.mapping else None
    masked, mapping = shield.mask(text, seed_mapping)
    if args.session_file:
        shield.save_session(args.session_file)
    if args.json:
        print(json.dumps({"text": masked, "mapping": mapping}, ensure_ascii=False, indent=2))
    else:
        print(masked)
        print(json.dumps(mapping, ensure_ascii=False))
    return 0
