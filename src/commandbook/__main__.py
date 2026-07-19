"""Enables running via `python -m commandbook`."""

from __future__ import annotations

import sys

from commandbook.cli import main

if __name__ == "__main__":
    sys.exit(main())
