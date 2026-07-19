"""Tests for the variable store."""

from __future__ import annotations

from commandbook.config.models import VarGroup
from commandbook.variables.store import VariableStore


def _store() -> VariableStore:
    groups = {"aws": VarGroup(name="aws", values={"region": ["us-east-1", "eu-west-1"]})}
    return VariableStore(groups, cwd="/work")


def test_predefined_cwd():
    assert _store().predefined == {"cwd": "/work"}


def test_values_for_known_group():
    assert _store().values_for("aws", "region") == ["us-east-1", "eu-west-1"]


def test_values_for_unknown_returns_empty():
    store = _store()
    assert store.values_for("aws", "missing") == []
    assert store.values_for("nope", "region") == []
    assert store.values_for(None, "region") == []


def test_group_lookup():
    store = _store()
    assert store.group("aws").name == "aws"
    assert store.group("nope") is None
    assert store.group(None) is None
