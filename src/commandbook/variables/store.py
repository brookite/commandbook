"""Variable store: predefined variables plus user-defined named groups.

Predefined variables (e.g. ``cwd``) are always available. Named groups come from
the config and provide preset value suggestions for placeholders. A command or
group selects which variable group is active.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from commandbook.config.models import VarGroup


class VariableStore:
    """Holds predefined variables and named variable groups from the config."""

    def __init__(self, variable_groups: Mapping[str, VarGroup], *, cwd: str | None = None) -> None:
        self._groups: dict[str, VarGroup] = dict(variable_groups)
        self._cwd = cwd if cwd is not None else os.getcwd()

    @property
    def predefined(self) -> dict[str, str]:
        """Predefined variables available to every command."""
        return {"cwd": self._cwd}

    def group(self, name: str | None) -> VarGroup | None:
        if name is None:
            return None
        return self._groups.get(name)

    def values_for(self, group_name: str | None, var_name: str) -> list[str]:
        """Preset values for ``var_name`` in the named group, or an empty list."""
        group = self.group(group_name)
        if group is None:
            return []
        return list(group.values.get(var_name, []))
