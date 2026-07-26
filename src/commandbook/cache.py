"""Best-effort persistence for explicitly edited command form values."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

DEFAULT_CACHE_PATH = Path.home() / ".commandbook_cache"

FormValue = str | bool
CacheData = dict[str, dict[str, FormValue]]


class FormValueCache:
    """Read and update per-command form values without blocking the application."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH) -> None:
        self.path = path

    def values_for(self, command_id: str) -> dict[str, FormValue]:
        """Return validated cached values for one command."""
        return dict(self._load().get(command_id, {}))

    def update(self, command_id: str, values: Mapping[str, FormValue]) -> None:
        """Merge edited values and atomically replace the cache when possible."""
        cache = self._load()
        command_values = cache.setdefault(command_id, {})
        command_values.update(values)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(cache, temporary, ensure_ascii=False, indent=2, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

    def _load(self) -> CacheData:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}

        cache: CacheData = {}
        for command_id, values in raw.items():
            if not isinstance(command_id, str) or not isinstance(values, dict):
                continue
            valid = {
                name: value
                for name, value in values.items()
                if isinstance(name, str) and isinstance(value, (str, bool))
            }
            cache[command_id] = valid
        return cache
