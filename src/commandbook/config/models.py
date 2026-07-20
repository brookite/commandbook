"""Commandbook configuration domain models.

The models are pure (no Textual) and do no parsing themselves — they are built by
:mod:`commandbook.config.loader`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_SHELLS = ("auto", "bash", "cmd", "powershell")
"""Allowed values for `settings.shell` and keys of `command.shells`."""


QUOTE_STYLES = ("auto", "single", "double", "backtick")
"""Allowed values for `placeholder.quote_style` (used when `escape` is on)."""


SEVERITIES = ("none", "medium", "high")
"""Allowed command risk levels."""


@dataclass(slots=True)
class Placeholder:
    """A single command placeholder."""

    name: str
    type: str
    label: str = ""
    description: str = ""
    optional: bool = False
    pattern: str | None = None
    default: str | None = None
    escape: bool = True
    """Shell-escape the value before substitution. Off for the `bare` type."""
    quote_style: str = "auto"
    """Quote style when escaping: `auto` (minimal), `single`, or `double`."""
    strip_quotes: bool = False
    """Strip one layer of surrounding quotes from the entered value first."""


@dataclass(slots=True)
class Command:
    """A prepared command with placeholders."""

    id: str
    name: str
    template: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    severity: str = "none"
    shells: dict[str, str] = field(default_factory=dict)
    placeholders: list[Placeholder] = field(default_factory=list)
    cwd: str | None = None
    cwd_from: str | None = None

    def template_for(self, shell: str) -> str:
        """Return the template for a specific shell.

        Priority: `shells[shell]` -> `shells['default']` -> `template`.
        """
        if shell in self.shells:
            return self.shells[shell]
        if "default" in self.shells:
            return self.shells["default"]
        if self.template is not None:
            return self.template
        raise KeyError(f"Command {self.id!r} has no template for shell {shell!r}")

    def placeholder(self, name: str) -> Placeholder | None:
        for ph in self.placeholders:
            if ph.name == name:
                return ph
        return None


@dataclass(slots=True)
class VarGroup:
    """A named variable group: variable name -> list of values."""

    name: str
    values: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class Group:
    """A group of commands sharing common settings."""

    name: str
    commands: list[Command] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cwd: str | None = None
    search_dirs: list[str] = field(default_factory=list)
    variables: str | None = None


@dataclass(slots=True)
class Settings:
    """Global application settings."""

    shell: str = "auto"


@dataclass(slots=True)
class Config:
    """Configuration root."""

    settings: Settings = field(default_factory=Settings)
    groups: list[Group] = field(default_factory=list)
    variable_groups: dict[str, VarGroup] = field(default_factory=dict)

    def iter_commands(self):
        """Iterate over all commands as (group, command)."""
        for group in self.groups:
            for command in group.commands:
                yield group, command
