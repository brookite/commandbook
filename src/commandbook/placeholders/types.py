"""Placeholder types and their validators.

Each validator takes a raw string and returns a normalized value (a string to
substitute, or a `bool` for a checkbox), or raises :class:`ValidationError`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

KNOWN_TYPES = frozenset(
    {
        "string",
        "bare",
        "int",
        "float",
        "date",
        "json",
        "regex",
        "email",
        "phone",
        "file",
        "directory",
        "checkbox",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,}$")
_TRUE = {"true", "1", "yes", "on", "y"}
_FALSE = {"false", "0", "no", "off", "n", ""}


class ValidationError(ValueError):
    """A value failed its placeholder type check."""


def is_known_type(type_name: str) -> bool:
    return type_name in KNOWN_TYPES


def validate_value(
    type_name: str,
    raw: object,
    *,
    pattern: str | None = None,
    search_dirs: Sequence[str] | None = None,
) -> str | bool:
    """Validate and normalize a value against a placeholder type."""
    if type_name not in KNOWN_TYPES:
        raise ValidationError(f"Unknown placeholder type: {type_name!r}")

    if type_name == "checkbox":
        return _validate_checkbox(raw)

    text = raw if isinstance(raw, str) else str(raw)
    text = text.strip()

    match type_name:
        case "string" | "bare":
            return text
        case "int":
            return _validate_int(text)
        case "float":
            return _validate_float(text)
        case "date":
            return _validate_date(text)
        case "json":
            return _validate_json(text)
        case "regex":
            return _validate_regex(text, pattern)
        case "email":
            return _match(text, _EMAIL_RE, "an email")
        case "phone":
            return _validate_phone(text)
        case "file":
            return _validate_path(text, search_dirs, want="file")
        case "directory":
            return _validate_path(text, search_dirs, want="directory")

    # Unreachable: covered by the KNOWN_TYPES check above.
    raise ValidationError(f"Type {type_name!r} is not handled by the validator")


def _validate_checkbox(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValidationError(f"Expected yes/no, got {raw!r}")


def _validate_int(text: str) -> str:
    try:
        return str(int(text))
    except ValueError as exc:
        raise ValidationError(f"Not an integer: {text!r}") from exc


def _validate_float(text: str) -> str:
    try:
        float(text)
    except ValueError as exc:
        raise ValidationError(f"Not a real number: {text!r}") from exc
    return text


def _validate_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValidationError(f"Date is not in YYYY-MM-DD format: {text!r}") from exc


def _validate_json(text: str) -> str:
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f"Invalid JSON: {exc}") from exc
    return text


def _validate_regex(text: str, pattern: str | None) -> str:
    if not pattern:
        raise ValidationError("The 'regex' type requires a 'pattern'")
    if re.fullmatch(pattern, text) is None:
        raise ValidationError(f"Value {text!r} does not match pattern {pattern!r}")
    return text


def _validate_phone(text: str) -> str:
    digits = sum(ch.isdigit() for ch in text)
    if digits < 7 or _PHONE_RE.fullmatch(text) is None:
        raise ValidationError(f"Does not look like a phone number: {text!r}")
    return text


def _match(text: str, regex: re.Pattern[str], label: str) -> str:
    if regex.fullmatch(text) is None:
        raise ValidationError(f"Does not look like {label}: {text!r}")
    return text


def _validate_path(text: str, search_dirs: Sequence[str] | None, *, want: str) -> str:
    if not text:
        raise ValidationError("Path must not be empty")

    candidate = Path(text).expanduser()
    tried: list[Path] = []
    if candidate.is_absolute():
        tried.append(candidate)
    else:
        tried.append(Path.cwd() / candidate)
        for base in search_dirs or ():
            tried.append(Path(base).expanduser() / candidate)

    check = Path.is_file if want == "file" else Path.is_dir
    for path in tried:
        if check(path):
            return str(path.resolve())

    kind = "File" if want == "file" else "Directory"
    raise ValidationError(f"{kind} not found: {text!r}")
