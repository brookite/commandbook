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
        help="Path to the TOML config (defaults to the standard search locations).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Import lazily so that --help does not pull in Textual.
    from commandbook.tui.app import CommandbookApp

    app = CommandbookApp(config_path=args.config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
