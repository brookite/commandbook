# Form Value Cache and Failed Command Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist explicitly edited command-form values across restarts and reopen the same prefilled form after a non-zero command exit.

**Architecture:** Add a pure `FormValueCache` component for best-effort JSON persistence, extend form submission with edited-field metadata, and let `CommandbookApp` coordinate configured defaults, cached values, transient retry values, and command exit handling. Keep command execution and validation behavior unchanged outside this flow.

**Tech Stack:** Python 3.11+, dataclasses, `json`, `pathlib`, Textual, pytest, Ruff.

## Global Constraints

- The persistent cache path is `~/.commandbook_cache`.
- `nocache` is a command-level boolean and defaults to `false`.
- Unchanged configured defaults are never written to persistent cache.
- A field edited and then restored to its configured default remains cacheable.
- Cache failures never prevent Commandbook from starting or running commands.
- Failed-command retry values are in-memory and apply even when `nocache: true`.
- Commands without placeholders and connector transport errors do not open a retry form.
- Add no third-party dependencies.

---

## File Structure

- Create `src/commandbook/cache.py`: validate, read, query, and atomically update the JSON cache.
- Create `tests/test_cache.py`: pure cache behavior and filesystem-safety tests.
- Modify `src/commandbook/config/models.py`: add `Command.nocache`.
- Modify `src/commandbook/config/loader.py`: strictly parse the command-level boolean.
- Modify `src/commandbook/tui/screens/placeholder_form.py`: accept explicit initial values and return edited-field metadata.
- Modify `src/commandbook/tui/app.py`: load cache, persist edited fields, and coordinate retry forms.
- Modify `tests/test_loader.py`: configuration contract tests.
- Modify `tests/test_app.py`: form initialization, persistence coordination, and retry tests.
- Modify `README.md`: document the command option and cache semantics.
- Modify `examples/commandbook.yaml` and `examples/commandbook.toml`: keep equivalent examples with an explicit `nocache` example.

### Task 1: Command-Level `nocache` Configuration

**Files:**
- Modify: `src/commandbook/config/models.py`
- Modify: `src/commandbook/config/loader.py`
- Modify: `tests/test_loader.py`

**Interfaces:**
- Consumes: `_parse_commands(raw: Any, *, group_name: str) -> list[Command]`.
- Produces: `Command.nocache: bool`, always populated by the loader.

- [ ] **Step 1: Write failing loader tests**

Add:

```python
def test_command_nocache_defaults_to_false_and_accepts_booleans():
    default = parse_config(_single_command({"id": "default", "name": "Default", "template": "x"}))
    disabled = parse_config(
        _single_command({"id": "private", "name": "Private", "template": "x", "nocache": True})
    )

    assert default.groups[0].commands[0].nocache is False
    assert disabled.groups[0].commands[0].nocache is True


def test_command_nocache_rejects_non_boolean_values():
    data = _single_command(
        {"id": "bad", "name": "Bad", "template": "x", "nocache": "true"}
    )

    with pytest.raises(ConfigError, match="nocache.*true or false"):
        parse_config(data)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/test_loader.py::test_command_nocache_defaults_to_false_and_accepts_booleans tests/test_loader.py::test_command_nocache_rejects_non_boolean_values -v
```

Expected: FAIL because `Command` has no `nocache` attribute and the string value is accepted.

- [ ] **Step 3: Add the model field and strict loader validation**

Add `nocache: bool = False` to `Command`. In `_parse_commands`, validate before constructing
the model:

```python
nocache = item.get("nocache", False)
if not isinstance(nocache, bool):
    raise ConfigError(f"command {cmd_id!r}: 'nocache' must be true or false")
```

Pass `nocache=nocache` to `Command(...)`.

- [ ] **Step 4: Run focused and loader tests**

Run:

```bash
uv run pytest tests/test_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/commandbook/config/models.py src/commandbook/config/loader.py tests/test_loader.py
git commit -m "feat: add command nocache setting"
```

### Task 2: Best-Effort Persistent Form Cache

**Files:**
- Create: `src/commandbook/cache.py`
- Create: `tests/test_cache.py`

**Interfaces:**
- Consumes: a filesystem `Path` supplied by the application or a test.
- Produces:
  - `DEFAULT_CACHE_PATH = Path.home() / ".commandbook_cache"`
  - `FormValue = str | bool`
  - `FormValueCache(path: Path = DEFAULT_CACHE_PATH)`
  - `FormValueCache.values_for(command_id: str) -> dict[str, FormValue]`
  - `FormValueCache.update(command_id: str, values: Mapping[str, FormValue]) -> None`

- [ ] **Step 1: Write failing cache read tests**

Create tests covering a missing file, malformed JSON, invalid top-level/list data, invalid
command entries, invalid value types, and a valid entry:

```python
def test_cache_reads_valid_string_and_boolean_values(tmp_path):
    path = tmp_path / "cache"
    path.write_text(
        '{"build": {"tag": "demo", "push": true, "bad": 42}, "broken": []}',
        encoding="utf-8",
    )

    cache = FormValueCache(path)

    assert cache.values_for("build") == {"tag": "demo", "push": True}
    assert cache.values_for("broken") == {}
    assert cache.values_for("missing") == {}


@pytest.mark.parametrize("contents", ["", "{broken", "[]", "null"])
def test_cache_treats_missing_or_invalid_content_as_empty(tmp_path, contents):
    path = tmp_path / "cache"
    if contents:
        path.write_text(contents, encoding="utf-8")

    assert FormValueCache(path).values_for("build") == {}
```

- [ ] **Step 2: Run read tests and verify RED**

Run:

```bash
uv run pytest tests/test_cache.py -v
```

Expected: collection FAIL because `commandbook.cache` does not exist.

- [ ] **Step 3: Implement minimal validated reads**

Implement a private `_load() -> dict[str, dict[str, FormValue]]` that catches
`OSError`, `UnicodeDecodeError`, and `json.JSONDecodeError`, accepts only dict-shaped
entries, and filters values with `isinstance(value, (str, bool))`.

- [ ] **Step 4: Run read tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_cache.py -v
```

Expected: PASS for the read tests.

- [ ] **Step 5: Write failing update, preservation, atomicity, and permission tests**

Add:

```python
def test_cache_update_preserves_other_commands_and_fields(tmp_path):
    path = tmp_path / "cache"
    path.write_text(
        '{"build": {"tag": "old", "push": true}, "deploy": {"host": "prod"}}',
        encoding="utf-8",
    )
    cache = FormValueCache(path)

    cache.update("build", {"tag": "new"})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "build": {"tag": "new", "push": True},
        "deploy": {"host": "prod"},
    }


def test_cache_new_file_has_owner_only_permissions(tmp_path):
    path = tmp_path / "cache"

    FormValueCache(path).update("build", {"tag": "demo"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".cache.*.tmp"))


def test_cache_write_failure_is_ignored(tmp_path):
    directory = tmp_path / "cache"
    directory.mkdir()

    FormValueCache(directory).update("build", {"tag": "demo"})
```

- [ ] **Step 6: Run update tests and verify RED**

Run:

```bash
uv run pytest tests/test_cache.py -v
```

Expected: FAIL because `update` is absent.

- [ ] **Step 7: Implement atomic best-effort updates**

Merge only supplied fields into the loaded command entry. Create a same-directory
temporary file with `tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False)`, serialize JSON,
flush and `os.fsync`, apply `os.chmod(temp_path, 0o600)`, then `os.replace(temp_path,
path)`. Catch `OSError` and remove a created temporary file with `Path.unlink(missing_ok=True)`
inside another guarded `try`.

- [ ] **Step 8: Run cache tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_cache.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/commandbook/cache.py tests/test_cache.py
git commit -m "feat: persist edited form values"
```

### Task 3: Form Initial Values and Edited-Field Result

**Files:**
- Modify: `src/commandbook/tui/screens/placeholder_form.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes:
  - `initial_values: Mapping[str, str | bool] | None`
  - existing preset lists and placeholder definitions.
- Produces:
  - `@dataclass(frozen=True, slots=True) FormSubmission`
  - `FormSubmission.values: dict[str, str | bool]`
  - `FormSubmission.edited: frozenset[str]`
  - `PlaceholderFormScreen(ModalScreen[FormSubmission | None])`

- [ ] **Step 1: Write failing form initialization tests**

Add a test that launches the Docker form with explicit initial values and asserts text
inputs use them. Add a small parsed configuration containing a checkbox and a preset
select, then assert a valid initial value overrides the configured default while a stale
preset value is ignored:

```python
screen = PlaceholderFormScreen(
    entry,
    presets={"region": ["us-east-1", "eu-west-1"]},
    initial_values={"name": "cached", "enabled": True, "region": "eu-west-1"},
)
```

Expected assertions:

```python
assert screen._inputs["name"].value == "cached"
assert screen._inputs["enabled"].value is True
assert screen._inputs["region"].value == "eu-west-1"
```

For `initial_values={"region": "removed-region"}`, assert the select uses its configured
default or `Select.BLANK`, matching the existing `_make_select` rules.

- [ ] **Step 2: Run initialization tests and verify RED**

Run:

```bash
uv run pytest tests/test_app.py -k "form_initial" -v
```

Expected: FAIL because `initial_values` is not accepted.

- [ ] **Step 3: Implement explicit initial-value priority**

Store `self.initial_values`. For text inputs, checkbox defaults, and select defaults,
use a type-compatible explicit value when present; otherwise retain the current
placeholder-default behavior. A select accepts an initial string only when it exists in
`options`.

- [ ] **Step 4: Run initialization tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_app.py -k "form_initial" -v
```

Expected: PASS.

- [ ] **Step 5: Write failing edited-field submission tests**

Create a form with a text default, change the input away from and back to that default,
submit it, and assert:

```python
assert captured == [
    FormSubmission(values={"name": "configured"}, edited=frozenset({"name"}))
]
```

Create another form, submit without changing any controls, and assert
`edited == frozenset()`. Keep the existing normalized-value assertions by reading
`submission.values`.

- [ ] **Step 6: Run submission tests and verify RED**

Run:

```bash
uv run pytest tests/test_app.py -k "form_tracks_edited or remote_form" -v
```

Expected: FAIL because dismissal still returns a plain dictionary.

- [ ] **Step 7: Implement `FormSubmission` and event-based edit tracking**

Add the dataclass and `self._edited: set[str]`. Set a tracking flag in `on_mount` after
the controls have their initial values. Handle `Input.Changed`, `Checkbox.Changed`, and
`Select.Changed`; identify the field by object identity in `self._inputs` and add its
name when tracking is active. `_submit` dismisses:

```python
FormSubmission(values=values, edited=frozenset(self._edited))
```

Programmatic changes made after mount count as edits, which keeps headless tests aligned
with real user edits.

- [ ] **Step 8: Run form and app tests**

Run:

```bash
uv run pytest tests/test_app.py -v
```

Expected: PASS after updating existing callbacks to unwrap `submission.values`.

- [ ] **Step 9: Commit**

```bash
git add src/commandbook/tui/screens/placeholder_form.py tests/test_app.py
git commit -m "feat: track edited form fields"
```

### Task 4: Application Cache and Failed-Exit Retry Integration

**Files:**
- Modify: `src/commandbook/tui/app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes:
  - `FormValueCache.values_for(command_id)`.
  - `FormValueCache.update(command_id, edited_values)`.
  - `FormSubmission`.
- Produces:
  - `CommandbookApp(..., cache_path: Path | None = None)`.
  - `_launch(entry, initial_values: Mapping[str, str | bool] | None = None)`.
  - `_handle_submission(entry, submission: FormSubmission | None) -> None`.
  - `_handle_exit(entry, values, code: int) -> None`.

- [ ] **Step 1: Write failing cache-coordination tests**

Use `cache_path=tmp_path / "cache"` and test:

1. Cached values prefill a cache-enabled command.
2. `nocache=True` ignores an existing cache entry.
3. Submitting an untouched default leaves the cache file absent.
4. Editing only one field updates only that field.
5. `nocache=True` never creates or updates the file.

The edited-field assertion should use:

```python
submission = FormSubmission(
    values={"tag": "demo", "dockerfile": "", "context": "."},
    edited=frozenset({"tag"}),
)
app._handle_submission(entry, submission)
assert FormValueCache(cache_path).values_for(entry.command.id) == {"tag": "demo"}
```

Monkeypatch `_confirm_or_run` where needed so the tests assert cache behavior without
executing a shell command.

- [ ] **Step 2: Run cache-coordination tests and verify RED**

Run:

```bash
uv run pytest tests/test_app.py -k "cache" -v
```

Expected: FAIL because the app has no cache coordination.

- [ ] **Step 3: Implement application cache coordination**

Construct `FormValueCache(cache_path or DEFAULT_CACHE_PATH)`. `_launch` chooses:

```python
form_values = (
    dict(initial_values)
    if initial_values is not None
    else ({} if entry.command.nocache else self.cache.values_for(entry.command.id))
)
```

Pass `form_values` into the screen. `_handle_submission` returns on `None`; otherwise it
filters `submission.values` to `submission.edited`, updates the cache only when the
command is cache-enabled and the filtered mapping is non-empty, then calls
`_confirm_or_run(entry, submission.values)`.

- [ ] **Step 4: Run cache-coordination tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_app.py -k "cache" -v
```

Expected: PASS.

- [ ] **Step 5: Write failing exit-handler tests**

Test `_handle_exit` directly inside `app.run_test()`:

```python
app._handle_exit(entry, {"tag": "failed", "dockerfile": "", "context": "."}, 7)
await pilot.pause()
assert isinstance(app.screen, PlaceholderFormScreen)
assert app.screen._inputs["tag"].value == "failed"
```

Also assert code `0` does not push a form and a no-placeholder entry does not push a
form. Set `entry.command.nocache = True` in one non-zero case to prove transient retry
values bypass persistent-cache policy.

- [ ] **Step 6: Run exit-handler tests and verify RED**

Run:

```bash
uv run pytest tests/test_app.py -k "handle_exit" -v
```

Expected: FAIL because `_handle_exit` does not exist.

- [ ] **Step 7: Implement common exit handling**

Add:

```python
def _handle_exit(
    self,
    entry: CommandEntry,
    values: dict[str, str | bool],
    code: int,
) -> None:
    self.notify(f"Exited with code {code}")
    if code != 0 and entry.command.placeholders:
        self._launch(entry, initial_values=values)
```

Call it at the successful end of both `_run` and `_run_connected`. Keep connector
exceptions returning before this method so transport errors do not open the form.

- [ ] **Step 8: Run integration and full tests**

Run:

```bash
uv run pytest tests/test_app.py -v
uv run pytest -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/commandbook/tui/app.py tests/test_app.py
git commit -m "feat: restore forms after failed commands"
```

### Task 5: User Documentation, Examples, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `examples/commandbook.yaml`
- Modify: `examples/commandbook.toml`
- Modify: `tests/test_loader.py`

**Interfaces:**
- Consumes: the completed `nocache` and cache behavior.
- Produces: documented YAML/TOML examples that remain behaviorally equivalent.

- [ ] **Step 1: Write a failing example-parity assertion**

Extend `test_load_example_config` and the YAML/TOML equivalence test:

```python
assert commands["git-log"].nocache is True
assert [
    (command.id, command.nocache)
    for _, command in yaml_config.iter_commands()
] == [
    (command.id, command.nocache)
    for _, command in toml_config.iter_commands()
]
```

- [ ] **Step 2: Run the example tests and verify RED**

Run:

```bash
uv run pytest tests/test_loader.py::test_load_example_config tests/test_loader.py::test_yaml_and_toml_examples_define_the_same_commands -v
```

Expected: FAIL because the examples do not yet set `git-log.nocache`.

- [ ] **Step 3: Update examples and README**

Set `nocache: true` on `git-log` in YAML and `nocache = true` on the equivalent TOML
command. Add `nocache` to the README command-fields table and document:

- the default is `false`;
- edited values persist in `~/.commandbook_cache`;
- untouched configured defaults are not written;
- `nocache: true` disables persistent reads and writes;
- a non-zero command exit reopens a prefilled form for correction.

- [ ] **Step 4: Run all quality checks**

Run:

```bash
uv run pytest -v
uv run ruff check .
git diff --check
```

Expected: all tests PASS, Ruff reports no issues, and Git reports no whitespace errors.

- [ ] **Step 5: Review the final diff and commit**

Run:

```bash
git diff --stat
git diff
git status --short
git add README.md examples/commandbook.yaml examples/commandbook.toml tests/test_loader.py
git commit -m "docs: describe form value caching"
```

Confirm that no unrelated files or user changes are included.
