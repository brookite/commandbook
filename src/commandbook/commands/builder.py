"""Assembly of the final command string from a template and placeholder values.

Template syntax:

* ``${name}`` — substitute a placeholder value. By default the value is escaped for
  the target shell; per-placeholder :class:`RenderSpec` controls how.
* ``[[ ... ${name} ... ]]`` — optional segment: included as a whole only if every
  placeholder referenced inside is "present" (a regular placeholder has a non-empty
  value, a checkbox is checked). Otherwise the segment is dropped entirely.
* ``$cwd`` / ``${cwd}`` — predefined variable: the current working directory.

Values are passed as ``dict[str, str | bool]``: ``bool`` for checkboxes (they carry
no value and substitute to an empty string), strings for everything else.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable, Mapping
from dataclasses import dataclass

_SEGMENT_RE = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}")
_BARE_CWD_RE = re.compile(r"\$cwd\b")

Value = str | bool

#: Quotes a value for a given style: ``quote_as(style, value) -> str``.
QuoteAs = Callable[[str, str], str]


@dataclass(frozen=True, slots=True)
class RenderSpec:
    """How to render a single placeholder value into the command."""

    escape: bool = True
    quote_style: str = "auto"
    strip_quotes: bool = False


DEFAULT_SPEC = RenderSpec()
"""Used for placeholders without an explicit spec (e.g. implicit/undeclared ones)."""


_BACKTICK_SPECIAL = re.compile(r"([\s`\"$&|;<>()\\])")


def _posix_single(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _posix_double(value: str) -> str:
    return '"' + re.sub(r"([$`\"\\])", r"\\\1", value) + '"'


def backtick_escape(value: str) -> str:
    """Escape shell-special characters by prefixing each with a backtick.

    This is PowerShell's escape convention; other shells accept it as a
    best-effort style when explicitly requested.
    """
    return _BACKTICK_SPECIAL.sub(r"`\1", value)


def default_quote_as(style: str, value: str) -> str:
    """POSIX/bash-style quoting used when no shell-specific quoter is supplied."""
    if style == "single":
        return _posix_single(value)
    if style == "double":
        return _posix_double(value)
    if style == "backtick":
        return backtick_escape(value)
    return shlex.quote(value)


def referenced_names(template: str) -> list[str]:
    """Return the ``${name}`` placeholder names referenced in ``template`` (ordered, unique)."""
    return list(dict.fromkeys(_PLACEHOLDER_RE.findall(template)))


def _is_present(value: Value | None) -> bool:
    if isinstance(value, bool):
        return value
    return value is not None and str(value) != ""


def _strip_one_quote_layer(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def build_command(
    template: str,
    values: Mapping[str, Value],
    *,
    quote_as: QuoteAs = default_quote_as,
    cwd: str | None = None,
    specs: Mapping[str, RenderSpec] | None = None,
) -> str:
    """Assemble a command from a template.

    :param values: placeholder name -> value (string, or bool for a checkbox).
    :param quote_as: shell-specific quoter (``(style, value) -> str``).
    :param cwd: the value for ``$cwd`` (defaults to the process working directory).
    :param specs: per-placeholder render specs; missing names use :data:`DEFAULT_SPEC`.
    """
    cwd_value = cwd if cwd is not None else os.getcwd()
    resolved: dict[str, Value] = {**values, "cwd": cwd_value}
    specs = specs or {}

    def render(name: str) -> str:
        value = resolved.get(name)
        if isinstance(value, bool) or value is None:
            return ""
        spec = specs.get(name, DEFAULT_SPEC)
        text = str(value)
        if spec.strip_quotes:
            text = _strip_one_quote_layer(text)
        if not spec.escape:
            return text
        return quote_as(spec.quote_style, text)

    def keep_segment(match: re.Match[str]) -> str:
        inner = match.group(1)
        names = _PLACEHOLDER_RE.findall(inner)
        if names and not all(_is_present(resolved.get(n)) for n in names):
            return ""
        return inner

    without_dropped = _SEGMENT_RE.sub(keep_segment, template)
    substituted = _PLACEHOLDER_RE.sub(lambda m: render(m.group(1)), without_dropped)
    substituted = _BARE_CWD_RE.sub(lambda _: quote_as("auto", cwd_value), substituted)
    return substituted.strip()
