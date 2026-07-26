"""Tests for persistent command form values."""

from __future__ import annotations

import json
import stat

import pytest

from commandbook.cache import FormValueCache


def test_cache_reads_valid_string_and_boolean_values(tmp_path):
    path = tmp_path / "cache"
    path.write_text(
        '{"build": {"tag": "demo", "push": true, "bad": 42}, "broken": []}',
        encoding="utf-8",
    )

    cache = FormValueCache(path)

    assert cache.values_for("build") == {"tag": "demo", "push": True}
    assert cache.values_for("broken") == {}
    assert cache.values_for("missing") == {}


@pytest.mark.parametrize("contents", ["", "{broken", "[]", "null"])
def test_cache_treats_missing_or_invalid_content_as_empty(tmp_path, contents):
    path = tmp_path / "cache"
    if contents:
        path.write_text(contents, encoding="utf-8")

    assert FormValueCache(path).values_for("build") == {}


def test_cache_update_preserves_other_commands_and_fields(tmp_path):
    path = tmp_path / "cache"
    path.write_text(
        '{"build": {"tag": "old", "push": true}, "deploy": {"host": "prod"}}',
        encoding="utf-8",
    )
    cache = FormValueCache(path)

    cache.update("build", {"tag": "new"})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "build": {"tag": "new", "push": True},
        "deploy": {"host": "prod"},
    }


def test_cache_new_file_has_owner_only_permissions(tmp_path):
    path = tmp_path / "cache"

    FormValueCache(path).update("build", {"tag": "demo"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".cache.*.tmp"))


def test_cache_write_failure_is_ignored(tmp_path):
    directory = tmp_path / "cache"
    directory.mkdir()

    FormValueCache(directory).update("build", {"tag": "demo"})
