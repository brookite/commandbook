"""CLI argument contract tests."""

from __future__ import annotations

import pytest

from commandbook.cli import build_parser


def test_connect_and_persistent_arguments():
    args = build_parser().parse_args(["--connect", "ssh prod", "--persistent"])
    assert args.connect == "ssh prod"
    assert args.persistent is True


def test_config_accepts_yaml_path():
    args = build_parser().parse_args(["--config", "commandbook.yaml"])
    assert args.config.name == "commandbook.yaml"


def test_parser_still_rejects_unknown_arguments():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--unknown"])
