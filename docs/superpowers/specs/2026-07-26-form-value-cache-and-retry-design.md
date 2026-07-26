# Form Value Cache and Failed Command Retry

## Goal

Persist placeholder values explicitly edited by the user across Commandbook restarts,
while allowing individual commands to opt out. When a command exits with a non-zero
status, reopen its placeholder form with the submitted values so the user can correct
and retry it.

## Configuration

Commands accept an optional boolean field:

```yaml
nocache: true
```

`nocache` defaults to `false`. The loader rejects non-boolean values.

When `nocache` is `true`, Commandbook neither reads nor writes persistent cached values
for that command. The setting does not affect the in-process values used to reopen a
form after a failed command.

## Persistent Cache

Commandbook stores form values in a single JSON file at `~/.commandbook_cache`. Entries
are keyed by the command's globally unique `id`; each entry maps placeholder names to
their cached string or boolean values.

The cache is best-effort state:

- A missing, unreadable, malformed, or structurally invalid cache is treated as empty
  and does not prevent Commandbook from starting.
- Writes replace the file atomically so an interrupted write does not leave a partial
  cache.
- A newly created cache file is accessible only to its owner.
- Values for placeholders that no longer exist are ignored when opening a form.
- A cached preset/select value is used only while it remains one of the configured
  choices. Otherwise the field uses its normal configured initial state.

The cache has no automatic pruning beyond replacing values for fields the user edits.

## Form Initial Values and Change Tracking

For cache-enabled commands, a field's initial value is chosen in this order:

1. A valid cached value.
2. The placeholder's configured `default`.
3. The field type's empty or false state.

The form tracks fields that the user actually edits during that opening. On a successful
form submission, only edited fields update the persistent cache. Merely displaying and
submitting a configured `default` does not write it to the cache.

Once a field has been edited, its submitted value is cacheable even if the user changes
it back to the configured `default`. That value remains in the cache; returning to the
default does not delete the entry.

Validation behavior remains unchanged. Invalid forms do not run a command and do not
update the cache.

## Failed Command Retry

After either a local or connected command returns a non-zero exit code, Commandbook
reopens the same placeholder form. The form is prefilled from the values submitted for
that execution, taking precedence over both persistent cache and configured defaults.
This retry state is in-memory and therefore also applies to commands with
`nocache: true`.

The form is reopened after Commandbook resumes from the suspended terminal and displays
the exit-code notification. Cancelling the reopened form returns to the command list.
Submitting it follows the existing severity-confirmation and execution flow.

Commands without placeholders continue to show the non-zero exit status without opening
a form, because they have no form to edit.

Connector errors are not command exit statuses and keep their existing error behavior;
they do not reopen the form.

## Components

- `config.models.Command` owns the `nocache` setting.
- `config.loader` validates and loads it.
- A small cache component owns JSON validation, cache lookup, and atomic persistence.
- `PlaceholderFormScreen` accepts explicit initial values and reports both normalized
  submitted values and the set of edited fields.
- `CommandbookApp` loads the cache, supplies initial values, persists edited fields, and
  reopens a form when execution returns a non-zero status.

## Testing

Tests will cover:

- `nocache` defaulting to `false`, accepting booleans, and rejecting other types.
- Missing, malformed, and structurally invalid cache files.
- Cache lookup and atomic updates without losing values from other commands or fields.
- Owner-only permissions for a newly created cache.
- Form initial-value priority for text, checkbox, and preset/select fields.
- Tracking edits independently of whether the final value equals `default`.
- Avoiding cache writes for untouched defaults and `nocache: true`.
- Reopening local and connected command forms after non-zero exit codes with submitted
  values.
- Not reopening after zero exit codes or connector errors.
