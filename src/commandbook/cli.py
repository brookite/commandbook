"""CLI entry point: argument parsing and TUI launch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="commandbook",
        description="Registry of CLI/shell commands with placeholders and fuzzy search.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to a YAML/TOML config (defaults to the standard search locations).",
    )
    parser.add_argument(
        "--connect",
        default=None,
        metavar="ALIAS_OR_COMMAND",
        help="Start with a configured connector alias or a full connector command.",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="Keep a raw --connect session open between commands.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.persistent and not args.connect:
        build_parser().error("--persistent requires --connect")

    # Import lazily so that --help does not pull in Textual.
    from commandbook.tui.app import CommandbookApp

    app = CommandbookApp(
        config_path=args.config,
        initial_connector=args.connect,
        initial_persistent=args.persistent,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
