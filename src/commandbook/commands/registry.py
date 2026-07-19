"""Command/group index with a simple, self-contained fuzzy search."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

from commandbook.config.models import Command, Config, Group

_BOUNDARY = " -_/.:"

_T = TypeVar("_T")


def fuzzy_score(query: str, text: str) -> float | None:
    """Score a subsequence match of ``query`` in ``text``.

    Returns ``None`` when ``query`` is not a subsequence of ``text``. Higher is
    better: consecutive characters and word-boundary hits are rewarded.
    """
    if not query:
        return 0.0
    lowered = text.lower()
    score = 0.0
    cursor = 0
    previous = -2
    for char in query.lower():
        index = lowered.find(char, cursor)
        if index == -1:
            return None
        score += 2.0 if index == previous + 1 else 1.0
        if index == 0 or lowered[index - 1] in _BOUNDARY:
            score += 1.0
        previous = index
        cursor = index + 1
    return score


def _ranked(items: Iterable[_T], query: str, text_of: Callable[[_T], str]) -> list[_T]:
    """Return ``items`` ranked by fuzzy match against ``query`` (all if empty)."""
    items = list(items)
    if not query.strip():
        return items
    scored: list[tuple[float, int, _T]] = []
    for order, item in enumerate(items):
        score = fuzzy_score(query, text_of(item))
        if score is not None:
            scored.append((score, order, item))
    scored.sort(key=lambda triple: (-triple[0], triple[1]))
    return [item for _, _, item in scored]


def _group_text(group: Group) -> str:
    parts = [group.name, group.description, " ".join(group.tags)]
    return " ".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class CommandEntry:
    """A command together with the group it belongs to."""

    group: Group
    command: Command

    @property
    def search_text(self) -> str:
        parts = [
            self.command.name,
            self.command.id,
            self.command.description,
            " ".join(self.command.tags),
            self.group.name,
            self.group.description,
            " ".join(self.group.tags),
        ]
        return " ".join(part for part in parts if part)


class CommandRegistry:
    """Holds groups and commands from a config and searches them fuzzily."""

    def __init__(self, config: Config) -> None:
        self._groups: list[Group] = list(config.groups)
        self._entries: list[CommandEntry] = [
            CommandEntry(group=group, command=command) for group, command in config.iter_commands()
        ]

    def all(self) -> list[CommandEntry]:
        return list(self._entries)

    def groups(self) -> list[Group]:
        return list(self._groups)

    def search(self, query: str) -> list[CommandEntry]:
        """Return command entries matching ``query``, best first (all if empty)."""
        return _ranked(self._entries, query, lambda entry: entry.search_text)

    def search_groups(self, query: str) -> list[Group]:
        """Return groups matching ``query``, best first (all if empty)."""
        return _ranked(self._groups, query, _group_text)

    def entries_in(self, group: Group) -> list[CommandEntry]:
        return [entry for entry in self._entries if entry.group is group]

    def search_commands_in(self, group: Group, query: str) -> list[CommandEntry]:
        """Return the group's command entries matching ``query`` (all if empty)."""
        return _ranked(self.entries_in(group), query, lambda entry: entry.search_text)
