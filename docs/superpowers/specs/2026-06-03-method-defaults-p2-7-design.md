# Method Defaults P2.7 Design

## Goal

P2.7 makes the P2 method-guided coding turn configurable without changing the default experience.

P2 already supports explicit `--method <id-or-name>`. P2.5 adds `--no-method`. P2.7 adds a small settings-backed default so a project or user can opt into a method by default for non-interactive coding turns.

Success criteria:

- No settings and no flags still means no method guidance.
- `--method <id-or-name>` still selects a method for one turn.
- `--no-method` still disables method guidance for one turn.
- Global/project/session settings can set a default method policy.
- CLI flags override settings.
- Only prompt/text/print/json coding turns are affected.

## Scope

### In Scope

- Add a small `MethodSettings` config slice to `loushang.coding.control`.
- Persist settings as:

```json
{
  "method": {
    "mode": "explicit",
    "selected_method": "review"
  }
}
```

- Support P2.7 settings modes:
  - `explicit`
  - `off`
- Add settings getters/setters for method policy defaults.
- Make CLI derive `MethodPolicy` from flags plus settings.
- Preserve P2.5/P2.6 behavior for explicit flags and work-log method metadata.
- Add focused tests for settings composition, persistence, and CLI precedence.

### Out Of Scope

- Automatic method selection.
- TUI/RPC method defaults.
- Method picker UI.
- Persisting a selected method from an individual CLI invocation.
- TaskFlow, fixed MethodPlan, or multi-step execution.
- Multi-agent / conductor behavior.
- `METHOD.md` / `SOUR.md` standards.
- Changing `loushang.method` schemas.
- Changing `CodingDomainApp` prompt assembly.

## Configuration Shape

Add:

```python
@dataclass(frozen=True)
class MethodSettings:
    mode: str = "explicit"
    selected_method: str | None = None
```

Add to `ControlConfig`:

```python
method: MethodSettings = field(default_factory=MethodSettings)
```

The type intentionally uses `str` for `mode` to avoid a future schema break when P3+ adds modes such as `fixed` or `auto`. P2.7 runtime validation only accepts:

- `explicit`
- `off`

Invalid configured modes should fail clearly when a coding turn tries to use them:

```text
Error: unsupported method policy mode: auto
```

That behavior matches `CodingDomainApp`'s existing policy validation and avoids silently ignoring a project setting.

## Settings Composition

Existing `SettingsManager` already composes:

```text
defaults -> global patch -> project patch -> session patch
```

P2.7 should use the same merge semantics for `method` as other nested settings slices. Example:

```json
// global
{"method": {"mode": "explicit", "selected_method": "review"}}

// project
{"method": {"selected_method": "debug"}}
```

Effective result:

```json
{"method": {"mode": "explicit", "selected_method": "debug"}}
```

This is consistent with existing shallow nested patch merging.

## Precedence

Per-turn CLI policy resolution:

```text
--no-method
  -> MethodPolicy.off()

--method <id-or-name>
  -> MethodPolicy.explicit(<id-or-name>)

settings.method.mode == "off"
  -> MethodPolicy.off()

settings.method.mode == "explicit"
  -> MethodPolicy.explicit(settings.method.selected_method)

no settings / inaccessible settings manager
  -> MethodPolicy.explicit(None)
```

Conflict behavior is unchanged:

```text
--method review --no-method -> exit 2
```

The settings default is intentionally lower precedence than any explicit CLI flag.

## CLI Integration

`run_cli(...)` already resolves `settings_manager` before prompt preparation.

Change only the policy mapping helper:

```python
def _method_policy_from_args(
    args: CliArgs,
    *,
    settings_manager: object | None = None,
) -> MethodPolicy:
    ...
```

Then pass the resolved services settings manager:

```python
method_policy=_method_policy_from_args(args, settings_manager=settings_manager)
```

Keep the method policy as a `CodingDomainRequest` value. CLI should not directly load or compile methods.

## Why This Belongs In `coding.control`

`loushang.method` owns method resources and projections.

`loushang.coding.domain` owns per-turn method usage policy.

`loushang.coding.control` owns persisted user/project settings.

P2.7 is a control-plane default for the coding app, not a new method resource type.

## Testing

### Settings Tests

- `ControlConfig().method` defaults to `MethodSettings(mode="explicit", selected_method=None)`.
- Global/project patches compose a method default.
- `SettingsManager.update_settings(method=MethodSettings(...))` persists and reloads.
- `SettingsManager.get_method_settings()` returns the effective method settings.
- `SettingsManager.set_method_settings(...)` updates the selected scope.

### CLI Tests

- No settings and no flags still dispatches the original prompt with `method_id is None`.
- Settings default method applies to `-p`.
- Settings default method applies to `--mode print`.
- Settings `mode="off"` suppresses method guidance.
- `--method` overrides settings.
- `--no-method` overrides settings.
- Missing configured method reports the existing method-list hint.
- Unsupported configured mode reports a clear error.

## Implementation Notes

- Keep `CodingDomainApp` unchanged unless tests reveal a missing edge case.
- Keep work-log behavior unchanged; method metadata flows from `prepared_turn.method_id`.
- Do not add new CLI flags in P2.7.
- Do not add config subcommands in P2.7; settings APIs and JSON files are enough for the first version.
