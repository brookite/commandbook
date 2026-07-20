"""Reading and validating a TOML config into :mod:`commandbook.config.models`."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml

from commandbook.commands.builder import referenced_names
from commandbook.config.models import (
    QUOTE_STYLES,
    SEVERITIES,
    VALID_SHELLS,
    VALID_TEMPLATE_SHELLS,
    Command,
    Config,
    Connector,
    Group,
    Placeholder,
    Settings,
    VarGroup,
)
from commandbook.placeholders.types import is_known_type

_SHELL_KEYS = frozenset(VALID_TEMPLATE_SHELLS) | {"default"}
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})


class ConfigError(ValueError):
    """The config is invalid: a TOML syntax error or a schema violation."""


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML or TOML config file based on its suffix."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"Could not read config {path}: {exc}") from exc
    suffix = path.suffix.lower()
    try:
        text = raw.decode("utf-8")
        if suffix in _YAML_SUFFIXES:
            loaded = yaml.safe_load(text)
            data = {} if loaded is None else loaded
        elif suffix == ".toml":
            data = tomllib.loads(text)
        else:
            raise ConfigError(
                f"Unsupported config format {suffix or '<none>'!r}; use .yaml, .yml, or .toml"
            )
    except (tomllib.TOMLDecodeError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Failed to parse config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config {path} must contain a top-level mapping")
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> Config:
    """Build a :class:`Config` from an already-parsed YAML/TOML mapping."""
    settings = _parse_settings(data.get("settings", {}))
    variable_groups = _parse_variable_groups(data.get("variables", {}))
    connectors = _parse_connectors(data.get("connectors", {}))
    groups = _parse_groups(data.get("groups", []))

    config = Config(
        settings=settings,
        groups=groups,
        variable_groups=variable_groups,
        connectors=connectors,
    )
    _validate_cross_references(config)
    return config


def _parse_settings(raw: Any) -> Settings:
    if not isinstance(raw, dict):
        raise ConfigError("The [settings] section must be a table")
    shell = raw.get("shell", "auto")
    if shell not in VALID_SHELLS:
        raise ConfigError(f"settings.shell = {shell!r}: must be one of {', '.join(VALID_SHELLS)}")
    return Settings(shell=shell)


def _parse_variable_groups(raw: Any) -> dict[str, VarGroup]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("The [variables] section must be a table")
    groups_raw = raw.get("groups", {})
    if not isinstance(groups_raw, dict):
        raise ConfigError("[variables.groups] must be a table")

    result: dict[str, VarGroup] = {}
    for name, body in groups_raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"Variable group {name!r} must be a table")
        values: dict[str, list[str]] = {}
        for var_name, var_values in body.items():
            if isinstance(var_values, list):
                values[var_name] = [str(v) for v in var_values]
            else:
                values[var_name] = [str(var_values)]
        result[name] = VarGroup(name=name, values=values)
    return result


def _parse_connectors(raw: Any) -> dict[str, Connector]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("The 'connectors' section must be a mapping keyed by alias")

    connectors: dict[str, Connector] = {}
    for raw_alias, body in raw.items():
        alias = str(raw_alias).strip()
        if not alias:
            raise ConfigError("Connector aliases must not be empty")
        if not isinstance(body, dict):
            raise ConfigError(f"connector {alias!r} must be a mapping")
        command = _opt_str(body.get("command"))
        if command is None or not command.strip():
            raise ConfigError(f"connector {alias!r}: the 'command' field is required")
        persistent = body.get("persistent", False)
        if not isinstance(persistent, bool):
            raise ConfigError(f"connector {alias!r}: 'persistent' must be true or false")
        connectors[alias] = Connector(
            alias=alias,
            command=command,
            persistent=persistent,
            cwd=_opt_str(body.get("cwd")),
        )
    return connectors


def _parse_groups(raw: Any) -> list[Group]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ConfigError("The [[groups]] section must be an array of tables")

    groups: list[Group] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"groups[{index}] must be a table")
        name = item.get("name")
        if not name:
            raise ConfigError(f"groups[{index}]: the 'name' field is required")
        commands = _parse_commands(item.get("commands", []), group_name=name)
        groups.append(
            Group(
                name=str(name),
                commands=commands,
                description=_opt_str(item.get("description")) or "",
                tags=_parse_tags(item.get("tags"), where=f"group {name!r}"),
                cwd=_opt_str(item.get("cwd")),
                search_dirs=[str(d) for d in item.get("search_dirs", [])],
                variables=_opt_str(item.get("variables")),
            )
        )
    return groups


def _parse_commands(raw: Any, *, group_name: str) -> list[Command]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"Group {group_name!r}: 'commands' must be an array of tables")

    commands: list[Command] = []
    for index, item in enumerate(raw):
        where = f"group {group_name!r}, command #{index}"
        if not isinstance(item, dict):
            raise ConfigError(f"{where}: must be a table")

        cmd_id = item.get("id")
        cmd_name = item.get("name")
        if not cmd_id:
            raise ConfigError(f"{where}: the 'id' field is required")
        if not cmd_name:
            raise ConfigError(f"command {cmd_id!r}: the 'name' field is required")

        shells = _parse_shells(item.get("shells", {}), cmd_id=cmd_id)
        template = _opt_str(item.get("template"))
        if template is None and "default" not in shells and not shells:
            raise ConfigError(
                f"command {cmd_id!r}: needs a 'template' or 'shells' (at least 'default')"
            )

        placeholders = _parse_placeholders(item.get("placeholders", []), cmd_id=cmd_id)
        severity = _opt_str(item.get("severity")) or "none"
        if severity not in SEVERITIES:
            raise ConfigError(
                f"command {cmd_id!r}: severity {severity!r} must be one of {', '.join(SEVERITIES)}"
            )
        command = Command(
            id=str(cmd_id),
            name=str(cmd_name),
            template=template,
            description=_opt_str(item.get("description")) or "",
            tags=_parse_tags(item.get("tags"), where=f"command {cmd_id!r}"),
            severity=severity,
            shells=shells,
            placeholders=placeholders,
            cwd=_opt_str(item.get("cwd")),
            cwd_from=_opt_str(item.get("cwd_from")),
        )
        _add_implicit_placeholders(command)
        _validate_command_refs(command)
        commands.append(command)
    return commands


def _add_implicit_placeholders(command: Command) -> None:
    """Add a plain string placeholder for any ``${name}`` used but not declared.

    A placeholder referenced in a template but missing from the config is not an
    error — it is treated as a required text placeholder. The predefined ``cwd``
    is excluded.
    """
    declared = {placeholder.name for placeholder in command.placeholders}
    templates = [command.template, *command.shells.values()]
    for template in templates:
        if not template:
            continue
        for name in referenced_names(template):
            if name == "cwd" or name in declared:
                continue
            declared.add(name)
            command.placeholders.append(Placeholder(name=name, type="string", label=name))


def _parse_shells(raw: Any, *, cmd_id: str) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"command {cmd_id!r}: 'shells' must be a table")
    shells: dict[str, str] = {}
    for key, value in raw.items():
        if key not in _SHELL_KEYS:
            allowed = ", ".join(sorted(_SHELL_KEYS))
            raise ConfigError(f"command {cmd_id!r}: unknown shell {key!r} (allowed: {allowed})")
        shells[key] = str(value)
    return shells


def _parse_placeholders(raw: Any, *, cmd_id: str) -> list[Placeholder]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"command {cmd_id!r}: 'placeholders' must be an array of tables")

    placeholders: list[Placeholder] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        where = f"command {cmd_id!r}, placeholder #{index}"
        if not isinstance(item, dict):
            raise ConfigError(f"{where}: must be a table")

        name = item.get("name")
        p_type = item.get("type")
        if not name:
            raise ConfigError(f"{where}: the 'name' field is required")
        if name in seen:
            raise ConfigError(f"command {cmd_id!r}: duplicate placeholder {name!r}")
        seen.add(name)
        if not p_type:
            raise ConfigError(
                f"placeholder {name!r} of command {cmd_id!r}: the 'type' field is required"
            )
        if not is_known_type(str(p_type)):
            raise ConfigError(f"placeholder {name!r}: unknown type {p_type!r}")

        pattern = _opt_str(item.get("pattern"))
        if p_type == "regex" and not pattern:
            raise ConfigError(f"placeholder {name!r}: the 'regex' type needs a 'pattern'")

        optional = bool(item.get("optional", False))
        if p_type == "checkbox":
            optional = True  # a checkbox is always optional (it only carries optionality)

        quote_style = _opt_str(item.get("quote_style")) or "auto"
        if quote_style not in QUOTE_STYLES:
            raise ConfigError(
                f"placeholder {name!r}: quote_style {quote_style!r} must be one of "
                f"{', '.join(QUOTE_STYLES)}"
            )
        # The 'bare' type is sugar for a string that is never escaped.
        escape = bool(item.get("escape", p_type != "bare"))
        if p_type == "bare":
            escape = False

        placeholders.append(
            Placeholder(
                name=str(name),
                type=str(p_type),
                label=_opt_str(item.get("label")) or "",
                description=_opt_str(item.get("description")) or "",
                optional=optional,
                pattern=pattern,
                default=_opt_str(item.get("default")),
                escape=escape,
                quote_style=quote_style,
                strip_quotes=bool(item.get("strip_quotes", False)),
            )
        )
    return placeholders


def _validate_command_refs(command: Command) -> None:
    if command.cwd_from is not None:
        target = command.placeholder(command.cwd_from)
        if target is None:
            raise ConfigError(
                f"command {command.id!r}: cwd_from refers to unknown placeholder "
                f"{command.cwd_from!r}"
            )
        if target.type not in ("file", "directory"):
            raise ConfigError(
                f"command {command.id!r}: cwd_from must point to a file/directory "
                f"placeholder, not {target.type!r}"
            )


def _validate_cross_references(config: Config) -> None:
    known_var_groups = set(config.variable_groups)
    for group in config.groups:
        if group.variables is not None and group.variables not in known_var_groups:
            raise ConfigError(
                f"group {group.name!r}: reference to unknown variable group {group.variables!r}"
            )

    seen_ids: set[str] = set()
    for _group, command in config.iter_commands():
        if command.id in seen_ids:
            raise ConfigError(f"Duplicate command id: {command.id!r}")
        seen_ids.add(command.id)


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_tags(value: Any, *, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{where}: 'tags' must be an array of strings")
    return [str(tag) for tag in value]
