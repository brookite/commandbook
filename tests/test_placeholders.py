"""Tests for placeholder type validators."""

from __future__ import annotations

import pytest

from commandbook.placeholders.types import ValidationError, is_known_type, validate_value


def test_known_types():
    assert is_known_type("email")
    assert not is_known_type("uuid")


@pytest.mark.parametrize(
    ("type_name", "raw", "expected"),
    [
        ("string", "  hi ", "hi"),
        ("int", " 42 ", "42"),
        ("float", "3.14", "3.14"),
        ("date", "2026-07-19", "2026-07-19"),
        ("json", '{"a": 1}', '{"a": 1}'),
        ("email", "a@b.co", "a@b.co"),
        ("phone", "+7 (999) 123-45-67", "+7 (999) 123-45-67"),
    ],
)
def test_valid_scalars(type_name, raw, expected):
    assert validate_value(type_name, raw) == expected


@pytest.mark.parametrize(
    ("type_name", "raw"),
    [
        ("int", "4.5"),
        ("float", "abc"),
        ("date", "19-07-2026"),
        ("json", "{not json}"),
        ("email", "no-at-sign"),
        ("phone", "12"),
    ],
)
def test_invalid_scalars(type_name, raw):
    with pytest.raises(ValidationError):
        validate_value(type_name, raw)


def test_regex_requires_pattern():
    with pytest.raises(ValidationError):
        validate_value("regex", "abc")


def test_regex_match():
    assert validate_value("regex", "ab12", pattern=r"[a-z]+\d+") == "ab12"
    with pytest.raises(ValidationError):
        validate_value("regex", "ABC", pattern=r"[a-z]+")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, True), (False, False), ("yes", True), ("off", False), ("", False)],
)
def test_checkbox(raw, expected):
    assert validate_value("checkbox", raw) is expected


def test_checkbox_invalid():
    with pytest.raises(ValidationError):
        validate_value("checkbox", "maybe")


def test_unknown_type():
    with pytest.raises(ValidationError):
        validate_value("uuid", "x")


def test_file_and_directory(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("x", encoding="utf-8")

    # Absolute paths.
    assert validate_value("file", str(target)) == str(target.resolve())
    assert validate_value("directory", str(tmp_path)) == str(tmp_path.resolve())

    # Relative path resolved via search_dirs.
    assert validate_value("file", "data.txt", search_dirs=[str(tmp_path)]) == str(target.resolve())

    with pytest.raises(ValidationError):
        validate_value("file", str(tmp_path))  # a directory, not a file
    with pytest.raises(ValidationError):
        validate_value("file", "no-such.txt", search_dirs=[str(tmp_path)])
