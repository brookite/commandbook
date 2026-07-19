# Commandbook

A console registry of CLI/shell commands with placeholders and fuzzy search.

Store prepared commands in TOML, find them with a fuzzy query, fill in the
placeholders through a form — and Commandbook assembles and runs the command in the
right shell and working directory. The goal is to speed up command entry without
memorizing detailed arguments.

## Status

In development. See [PLAN.md](PLAN.md) for the phased roadmap.

## Install (dev)

```sh
uv sync
```

## Run

```sh
# Explicit config:
uv run python -m commandbook --config examples/commandbook.toml

# Or rely on the default locations (see below):
uv run python -m commandbook
```

When `--config` is omitted, Commandbook looks for `commandbook.toml` in this order:

1. the current directory (`./commandbook.toml`) — a project-local override;
2. your home directory (`~/commandbook.toml`) — your personal command book.

The first file found wins.

---

## Configuration

The application is configured with a single TOML file, edited by hand — Commandbook
only reads it. A minimal file looks like this:

```toml
[settings]
shell = "auto"

[[groups]]
name = "Docker"

[[groups.commands]]
id = "docker-build"
name = "Build image"
template = "docker build -t ${tag} ${context}"

[[groups.commands.placeholders]]
name = "tag"
label = "Image tag"
type = "string"

[[groups.commands.placeholders]]
name = "context"
label = "Build context"
type = "directory"
default = "."
```

See [examples/commandbook.toml](examples/commandbook.toml) for a fuller example.

### Structure

| Section | Meaning |
| --- | --- |
| `[settings]` | Global settings. `shell` = `auto` \| `bash` \| `cmd` \| `powershell`. |
| `[variables.groups.<name>]` | A named variable group: `var = ["value1", "value2"]`. Reusable value presets. |
| `[[groups]]` | A command group. Fields: `name` (required), `description`, `tags`, `cwd`, `search_dirs`, `variables`. |
| `[[groups.commands]]` | A command. Fields below. |
| `[[groups.commands.placeholders]]` | A placeholder of that command. Fields below. |

**Command fields**

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique command id (across the whole config). |
| `name` | yes | Human-readable name, shown in the list and searched. |
| `description` | no | Longer description; also searched. |
| `tags` | no | Array of tags, e.g. `["build", "image"]`; also searched and shown in the list. |
| `template` | yes* | The command template (see [Template syntax](#template-syntax)). |
| `shells` | no | Per-shell templates, e.g. `shells.bash`, `shells.powershell`, `shells.cmd`, `shells.default`. |
| `cwd` | no | Working directory for this command. |
| `cwd_from` | no | Name of a `file`/`directory` placeholder whose value becomes the working directory. |

\* A command needs either `template` or a `shells` table containing at least
`default`.

**Placeholder fields**

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Referenced in the template as `${name}`. |
| `type` | yes | One of the [types](#placeholder-types) below. |
| `label` | no | Shown in the form (falls back to `name`). |
| `description` | no | Hint shown under the field. |
| `optional` | no | If `true`, the field may be left empty. Defaults to `false`. |
| `pattern` | for `regex` | Regular expression the value must fully match. |
| `default` | no | Pre-filled value in the form. |
| `escape` | no | Shell-escape the value before substitution. Defaults to `true` (always `false` for `bare`). |
| `quote_style` | no | When escaping: `auto` (minimal, default), `single`, `double`, or `backtick`. |
| `strip_quotes` | no | Remove one layer of surrounding quotes the user typed before escaping. Defaults to `false`. |

### Placeholder types

| Type | Accepts / validates |
| --- | --- |
| `string` | Any text. |
| `bare` | Any text, inserted **without** shell escaping (raw). Use with care. Equivalent to `string` + `escape = false`. |
| `int` | An integer. |
| `float` | A real number. |
| `date` | A date in `YYYY-MM-DD` format. |
| `json` | Valid JSON. |
| `regex` | Text fully matching `pattern`. |
| `email` | An email address. |
| `phone` | A phone number. |
| `file` | A path to an existing file (resolved against the group's `search_dirs`). |
| `directory` | A path to an existing directory. |
| `checkbox` | A yes/no toggle. Carries no value — it only gates an optional segment. Always optional. |

---

## Template syntax

A template is the shell command with placeholders. Three constructs are supported.

### 1. Substitution — `${name}`

`${name}` is replaced with the placeholder's value. Values are **escaped for the
target shell**, so spaces and special characters are safe:

```toml
template = "echo ${message}"
```

Entering `hello world` produces `echo 'hello world'` (under bash).

### 2. Optional segment — `[[ … ]]`

Everything inside `[[ … ]]` is included **only if every placeholder referenced
inside it is present** (a regular placeholder has a non-empty value; a checkbox is
checked). Otherwise the whole segment is dropped. Put the surrounding spaces
*inside* the brackets so the spacing stays correct either way:

```toml
template = "docker build -t ${tag}[[ -f ${dockerfile}]] ${context}"
```

- With a `dockerfile` value: `docker build -t img -f Dockerfile .`
- Without it: `docker build -t img .`

A checkbox gates a segment the same way — reference it inside the brackets:

```toml
template = "git log[[ --oneline${short}]]"
# checkbox "short" checked   -> git log --oneline
# checkbox "short" unchecked -> git log
```

### 3. Working directory — `$cwd` / `${cwd}`

The predefined variable `$cwd` (or `${cwd}`) expands to the current working
directory:

```toml
template = "ls ${cwd}/logs"
```

### Per-shell templates

Provide different templates per shell with a `shells` table. Commandbook picks
`shells[<detected shell>]`, then `shells.default`, then the top-level `template`:

```toml
[[groups.commands]]
id = "list"
name = "List files"
[groups.commands.shells]
bash = "ls -la"
powershell = "Get-ChildItem"
cmd = "dir"
```

### Working directory resolution

When a command runs, its working directory is chosen in this order:

1. the `cwd_from` placeholder's value (for a `file`, its parent directory; for a
   `directory`, the directory itself);
2. the command's `cwd`;
3. the group's `cwd`;
4. otherwise the current directory is inherited.

---

## Escaping & quoting

By default every substituted value is **shell-escaped**, so spaces and special
characters are safe. You can tune this per placeholder:

- `escape` (default `true`) — turn escaping off to insert the value verbatim.
- `quote_style` (default `auto`) — when escaping, force `single` or `double`
  quotes, `backtick` (prefix each special character with a backtick, PowerShell's
  convention), or let `auto` pick minimal safe quoting. The concrete quoting
  follows the target shell (bash, PowerShell, or cmd).
- `strip_quotes` (default `false`) — if the user pastes a value that already has
  surrounding quotes, remove one layer before escaping. When enabled, the form
  shows a note so the user knows their quotes will be stripped.

```toml
[[groups.commands.placeholders]]
name = "message"
type = "string"
quote_style = "double"   # -> "your message"
strip_quotes = true      # pasting "already quoted" becomes already quoted
```

### The `bare` type (no escaping)

Use `type = "bare"` (or `escape = false` on any text placeholder) when the value is
a fragment of shell syntax that must be inserted **as-is** — flags, globs, pipes:

```toml
[[groups.commands.placeholders]]
name = "extra_args"
label = "Extra arguments (inserted raw)"
type = "bare"
optional = true
```

> ⚠️ A `bare` value is not escaped, so only use it for input you trust.

## Variable presets

If a placeholder's `name` matches a variable in the group's variable group, the
form offers those values as a **dropdown** instead of a free-text field:

```toml
[variables.groups.aws]
region = ["us-east-1", "eu-west-1"]

[[groups]]
name = "AWS"
variables = "aws"          # activate this variable group for the commands

[[groups.commands]]
id = "aws-ec2-list"
name = "List EC2 instances"
template = "aws ec2 describe-instances --region ${region}"

[[groups.commands.placeholders]]
name = "region"            # matches variables.groups.aws.region -> dropdown
type = "string"
```

## Undeclared placeholders

A `${name}` used in a template but **not** declared in `placeholders` is not an
error — it is treated as a required `string` placeholder and prompted for in the
form. Declare it only when you need a specific type, label, or options.

---

## Tutorial: adding a command

Suppose you often run a Docker build and never remember the exact flags. Add it to
your `~/commandbook.toml`.

1. **Create a group** to hold related commands:

   ```toml
   [[groups]]
   name = "Docker"
   search_dirs = ["~/projects"]   # where file/directory placeholders are looked up
   ```

2. **Add the command** with a template. Mark the parts that vary as `${...}`
   placeholders, and wrap anything optional in `[[ … ]]`:

   ```toml
   [[groups.commands]]
   id = "docker-build"
   name = "Build image"
   template = "docker build -t ${tag}[[ -f ${dockerfile}]] ${context}"
   ```

3. **Describe each placeholder** — its type, a friendly label, whether it is
   optional, and an optional default:

   ```toml
   [[groups.commands.placeholders]]
   name = "tag"
   label = "Image tag"
   type = "string"

   [[groups.commands.placeholders]]
   name = "dockerfile"
   label = "Dockerfile"
   type = "file"
   optional = true       # if left empty, the "-f ..." segment is dropped

   [[groups.commands.placeholders]]
   name = "context"
   label = "Build context"
   type = "directory"
   default = "."
   ```

4. **Run Commandbook** and use it:

   ```sh
   uv run python -m commandbook
   ```

   - The main view lists **all commands**. Type to fuzzy-find **Build image**
     (matches the command name, id, description, tags, and its group) or arrow to
     it, then press <kbd>Enter</kbd> to open the form.
   - Prefer to browse by group? Press <kbd>Ctrl</kbd>+<kbd>G</kbd> to switch to the
     **groups** view, open a group with <kbd>Enter</kbd>, and search within it.
     <kbd>Esc</kbd> goes back to the groups; <kbd>Ctrl</kbd>+<kbd>G</kbd> returns to
     all commands.
   - Fill the fields. Required fields are marked with `*`; each value is validated
     against its type as you submit — a missing file or a non-integer is rejected
     with a message.
   - Press **Run**. Commandbook drops to the real terminal, runs the assembled
     command interactively, waits for you to press <kbd>Enter</kbd>, and returns to
     the list showing the exit code.

That's it — no more memorizing `docker build` flags.

---

## Navigation & keyboard shortcuts

The main view is a flat list of **all commands**. Press <kbd>Ctrl</kbd>+<kbd>G</kbd>
to switch to the **groups** view; opening a group shows its **commands**. Search is
scoped to whatever the current view shows.

| Key | Action |
| --- | --- |
| type in the search box | Fuzzy-filter the current view (all commands, groups, or a group's commands). |
| <kbd>Ctrl</kbd>+<kbd>G</kbd> | Toggle between the all-commands view and the groups view. |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> or <kbd>/</kbd> | Focus the search box. |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Move through the results. |
| <kbd>Enter</kbd> | Open the selected group / command (or, from the search box, the top match). |
| <kbd>Esc</kbd> | From search, move to the list; from a group's commands, go back to the groups. |
| <kbd>Enter</kbd> (in a form field) | Submit the placeholder form. |
| <kbd>Esc</kbd> (in a form) | Cancel and close the form. |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit. |

---

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
