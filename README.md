# Commandbook

A console registry of CLI/shell commands with placeholders, fuzzy search, and
connectors for local shells, SSH hosts, and Docker containers.

Commandbook reads a hand-written YAML or TOML file, asks for placeholder values,
assembles a safely quoted command, and runs it in the local or selected connected
shell. YAML is the preferred configuration format.

## Install (development)

```sh
uv sync
```

Connector sessions require a POSIX PTY and are supported on Linux, macOS, and WSL.
Local execution remains available on Windows.

## Run

```sh
# Explicit YAML config
uv run python -m commandbook --config examples/commandbook.yaml

# Start with a configured connector alias
uv run python -m commandbook --connect production

# Start a persistent connector from a full command
uv run python -m commandbook --connect "ssh deploy@example.com" --persistent

# Use the default config search
uv run python -m commandbook
```

Without `--config`, each directory is searched in this order:

1. `./commandbook.yaml`, `./commandbook.yml`, `./commandbook.toml`;
2. `~/commandbook.yaml`, `~/commandbook.yml`, `~/commandbook.toml`.

The first file found wins. TOML remains supported for backward compatibility.

## Configuration

A minimal YAML configuration:

```yaml
settings:
  shell: auto

groups:
  - name: Docker
    commands:
      - id: docker-build
        name: Build image
        template: 'docker build -t ${tag} ${context}'
        placeholders:
          - name: tag
            label: Image tag
            type: string
          - name: context
            label: Build context
            type: directory
            default: .
```

See [examples/commandbook.yaml](examples/commandbook.yaml) for a full YAML example.
The previous [TOML example](examples/commandbook.toml) is kept as a compatibility
reference.

### Top-level sections

| Key | Meaning |
| --- | --- |
| `settings` | Global settings. `shell`: `auto`, `bash`, `cmd`, or `powershell`. |
| `variables.groups` | Named reusable value presets. |
| `connectors` | Named shell, SSH, or Docker connector aliases. |
| `groups` | Command groups with their commands and placeholders. |

### Command fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique command id across the configuration. |
| `name` | yes | Human-readable searchable name. |
| `description` | no | Longer searchable description. |
| `tags` | no | Searchable tags, e.g. `[build, image]`. |
| `severity` | no | `none` (default), `medium`, or `high`; `high` requires confirmation. |
| `template` | yes* | Default command template. |
| `shells` | no | Per-shell/dialect templates: `bash`, `sh`, `dash`, `zsh`, `ksh`, `powershell`, `cmd`, `posix`, `default`. |
| `cwd` | no | Local cwd without a connector; remote cwd with a connector. |
| `cwd_from` | no | A `file`/`directory` placeholder used as cwd. |

\* A command needs `template` or at least `shells.default`.

### Placeholder fields

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Referenced as `${name}` in a template. |
| `type` | yes | One of the supported placeholder types below. |
| `label` | no | Form label; defaults to `name`. |
| `description` | no | Hint shown below the field. |
| `optional` | no | Allow an empty value; defaults to `false`. |
| `pattern` | for `regex` | Full-match regular expression. |
| `default` | no | Pre-filled value. |
| `escape` | no | Shell-escape before substitution; defaults to `true`. |
| `quote_style` | no | `auto`, `single`, `double`, or `backtick`. |
| `strip_quotes` | no | Remove one typed layer of surrounding quotes. |

| Type | Accepts / validates |
| --- | --- |
| `string` | Any text. |
| `bare` | Trusted raw shell syntax without escaping. |
| `int`, `float` | Numeric values. |
| `date` | `YYYY-MM-DD`. |
| `json` | Valid JSON. |
| `regex` | Text fully matching `pattern`. |
| `email`, `phone` | Email address or phone number. |
| `file`, `directory` | Existing local paths; treated as remote paths under a connector. |
| `checkbox` | Optional yes/no gate for an optional segment. |

## Connectors

Connectors may be selected at startup with `--connect` or from the TUI with
<kbd>Ctrl</kbd>+<kbd>S</kbd>. The CLI value is resolved as an exact configured alias
first, then as a full connector command.

```yaml
connectors:
  workstation-shell:
    command: /usr/bin/bash
    persistent: true

  production:
    command: ssh production
    persistent: true

  backend:
    command: docker compose exec backend
    persistent: false
    cwd: ~/projects/service

  worker:
    command: docker exec worker /bin/sh
    persistent: false
```

Connector fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `command` | yes | Shell path, full `ssh`, `docker exec`, or `docker compose exec` command. |
| `persistent` | no | Keep one shell and its state between commands; defaults to `false`. |
| `cwd` | no | Local directory used to start the connector command. |

Commandbook handles Docker interactive/TTY flags itself. A Docker shell is optional;
when omitted it probes `bash`, `zsh`, `sh`, then `pwsh`. SSH host aliases work through
the user's normal OpenSSH configuration.

Supported connected shell dialects are POSIX (`bash`, `sh`/`dash`, `zsh`, `ksh`)
and PowerShell. Shell detection controls placeholder quoting and template selection:

```yaml
groups:
  - name: Files
    commands:
      - id: list
        name: List files
        shells:
          posix: ls -la
          powershell: Get-ChildItem
          default: ls
```

An ephemeral connector selected in the TUI is used for the next command only. A
persistent connector preserves cwd, exported environment variables, and other shell
state. Its status appears in the bottom bar; press <kbd>Ctrl</kbd>+<kbd>D</kbd> to
disconnect. Connection errors never fall back to local execution automatically.

`command.cwd` and group `cwd` are remote paths while connected. `connector.cwd` is
always local and is useful for locating a Compose project.

## Template syntax

### Substitution — `${name}`

Values are escaped for the detected target shell:

```yaml
template: 'echo ${message}'
```

Entering `hello world` produces `echo 'hello world'` in a POSIX shell.

### Optional segments — `[[ … ]]`

An optional segment is retained only when every placeholder inside is present:

```yaml
template: 'docker build -t ${tag}[[ -f ${dockerfile}]] ${context}'
```

- With `dockerfile`: `docker build -t img -f Dockerfile .`
- Without it: `docker build -t img .`

A checkbox can gate a segment:

```yaml
template: 'git log[[ --oneline${short}]]'
```

### Current working directory — `$cwd` / `${cwd}`

```yaml
template: 'ls ${cwd}/logs'
```

Working directory precedence is `cwd_from`, command `cwd`, group `cwd`, then the
inherited local/connected shell directory.

## Escaping and presets

Use `bare` only for trusted shell fragments such as flags, globs, and pipes:

```yaml
placeholders:
  - name: extra_args
    label: Extra arguments (inserted raw)
    type: bare
    optional: true
```

Named variables turn matching placeholders into dropdowns:

```yaml
variables:
  groups:
    aws:
      region: [us-east-1, eu-west-1]

groups:
  - name: AWS
    variables: aws
    commands:
      - id: aws-ec2-list
        name: List EC2 instances
        template: 'aws ec2 describe-instances --region ${region}'
        placeholders:
          - name: region
            type: string
```

Undeclared `${name}` references become required `string` placeholders automatically.

## Navigation

| Key | Action |
| --- | --- |
| type in search | Fuzzy-filter the current commands/groups. |
| <kbd>Ctrl</kbd>+<kbd>G</kbd> | Toggle all-commands and groups views. |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> or <kbd>/</kbd> | Focus search. |
| <kbd>Ctrl</kbd>+<kbd>S</kbd> | Select Local, an alias, or a custom connector. |
| <kbd>Ctrl</kbd>+<kbd>D</kbd> | Disconnect a persistent connector. |
| <kbd>↑</kbd> / <kbd>↓</kbd> | Move through results or form fields. |
| <kbd>Enter</kbd> | Open/submit the selected item or form. |
| <kbd>Esc</kbd> | Cancel a form or navigate back. |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit. |

## Development

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright src
uv run pytest
```
