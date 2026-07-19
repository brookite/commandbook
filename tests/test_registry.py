"""Tests for the command registry and fuzzy scoring."""

from __future__ import annotations

from commandbook.commands.registry import CommandRegistry, fuzzy_score
from commandbook.config.models import Command, Config, Group


def _config() -> Config:
    return Config(
        groups=[
            Group(
                name="Docker",
                commands=[
                    Command(
                        id="docker-build",
                        name="Build image",
                        description="Assemble a container",
                        tags=["ci", "packaging"],
                    )
                ],
            ),
            Group(name="Git", commands=[Command(id="git-log", name="Commit history")]),
        ]
    )


def test_fuzzy_score_non_subsequence():
    assert fuzzy_score("xyz", "docker build") is None


def test_fuzzy_score_prefers_word_boundary():
    at_boundary = fuzzy_score("cb", "commit build")
    mid_word = fuzzy_score("cb", "accbuild")
    assert at_boundary is not None and mid_word is not None
    assert at_boundary > mid_word


def test_registry_empty_query_returns_all():
    registry = CommandRegistry(_config())
    assert [e.command.id for e in registry.search("")] == ["docker-build", "git-log"]


def test_registry_search_ranks_match():
    registry = CommandRegistry(_config())
    results = registry.search("docker")
    assert [e.command.id for e in results] == ["docker-build"]


def test_registry_search_matches_group_name():
    registry = CommandRegistry(_config())
    results = registry.search("git")
    assert results[0].command.id == "git-log"


def test_registry_search_matches_tag():
    registry = CommandRegistry(_config())
    results = registry.search("packaging")
    assert [e.command.id for e in results] == ["docker-build"]


def test_registry_search_matches_description():
    registry = CommandRegistry(_config())
    results = registry.search("container")
    assert results[0].command.id == "docker-build"
