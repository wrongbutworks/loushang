# MethodPolicy And Method Observability P2.5/P2.6 Design

## Goal

P2.5/P2.6 extends the P2 method-guided coding turn without entering P3 TaskFlow.

P2 already supports explicit `--method <id-or-name>` for one prompt / print / json coding turn. This design adds two small missing pieces:

- P2.5: make method usage an explicit per-turn policy so it can be turned off deliberately.
- P2.6: make method usage visible in work-log inspection and make missing-method errors actionable.

The default coding experience must remain unchanged.

## Scope

### In Scope

- Add a small `MethodPolicy` value object in `loushang.coding.domain`.
- Support P2.5 modes:
  - `off`
  - `explicit`
- Keep `auto` out of runtime behavior for this phase.
- Make `CodingDomainApp.prepare_turn(...)` consume `MethodPolicy`.
- Keep backward-compatible request construction from `method: str | None`.
- Add CLI `--no-method`.
- Reject `--method <id-or-name>` together with `--no-method`.
- Add `method_id` to `work-log inspect` text output when present.
- Add `method_id` to `work-log inspect` JSON output when present.
- Improve missing method errors with a hint to run `loushang method list`.

### Out Of Scope

- Automatic method selection.
- Global / project / session method settings.
- TUI / RPC method toggles.
- Persisted selected method.
- TaskFlow / multi-step MethodPlan.
- Multi-agent execution.
- METHOD.md / SOUR.md standards.

## Architecture

### MethodPolicy

`MethodPolicy` belongs in `loushang.coding.domain`, not `loushang.method`.

Reasoning:

- `loushang.method` owns resources, selection, compile, and projection.
- Whether a coding turn should use a method is a domain/run decision.
- CLI is only an input channel and should not encode method semantics directly.

Suggested shape:

```python
@dataclass(frozen=True)
class MethodPolicy:
    mode: str = "explicit"
    selected_method: str | None = None

    @classmethod
    def off(cls) -> "MethodPolicy": ...

    @classmethod
    def explicit(cls, selected_method: str | None) -> "MethodPolicy": ...
```

P2.5 behavior:

- `mode="off"`: return the original prompt unchanged and no `method_id`.
- `mode="explicit", selected_method=None`: return the original prompt unchanged and no `method_id`.
- `mode="explicit", selected_method="review"`: current P2 behavior.
- Unknown mode: raise `ValueError("unsupported method policy mode: <mode>")`.

This intentionally does not implement `auto`. The type can use `str` instead of a narrow `Literal` to avoid a future schema break, but runtime validation should only accept P2.5 modes.

### Request Compatibility

Existing `CodingDomainRequest(method=...)` should keep working.

Recommended migration path:

```python
@dataclass(frozen=True)
class CodingDomainRequest:
    user_input: str
    cwd: Path
    method: str | None = None
    method_policy: MethodPolicy | None = None
```

Resolution rule:

- If `method_policy` is present, use it.
- Else derive `MethodPolicy.explicit(method)` from the existing `method` field.

This keeps P2 callers stable while making the policy explicit for P2.5+.

### CLI Policy Mapping

CLI maps user intent into a per-turn policy:

```text
no flags                 -> MethodPolicy.explicit(None)
--method review          -> MethodPolicy.explicit("review")
--no-method              -> MethodPolicy.off()
--method review --no-method -> static CLI error, exit code 2
```

P2 unsupported paths remain unsupported:

- `--method` with TUI: error
- `--method` with RPC: error
- `--no-method` with TUI/RPC is harmless but unnecessary; P2.5 should reject it in the same unsupported-method validation path only if it would otherwise affect a turn. The simplest behavior is to allow `--no-method` because it is a no-op for unsupported method paths.

## Work-Log Observability

P2 already writes `method_id` into operation payloads and run lifecycle event payloads when work logging is active.

P2.6 should make this visible in inspect output.

### Text Output

Current columns:

```text
sequence kind run_id session_id delivery_hint
```

Add a trailing `method_id` column:

```text
sequence kind run_id session_id delivery_hint method_id
```

Rules:

- If an entry has `payload.method_id`, print it.
- If an operation has `payload.payload.method_id`, print it.
- Otherwise print an empty field.

Adding a trailing column is acceptable because inspect output is diagnostic and not a stable machine API. JSON remains the preferred structured format.

### JSON Output

Add `method_id` to each entry summary only when present.

This keeps non-method entries stable and avoids noisy `null` fields.

## Error Handling

Missing method should remain exit code `1` because it is a runtime lookup failure, not a parser conflict.

Message:

```text
Error: method not found: review
Run 'loushang method list' to inspect available methods.
```

`--method` and `--no-method` together should return exit code `2`:

```text
Error: --method cannot be used with --no-method.
```

## Testing

### Unit Tests

- `MethodPolicy` defaults.
- `MethodPolicy.off()`.
- `MethodPolicy.explicit(...)`.
- `CodingDomainApp.prepare_turn(...)` with:
  - default policy and no method.
  - explicit selected method.
  - off policy suppressing a method.
  - unsupported mode.

### CLI Tests

- Parser supports `--no-method`.
- `--method review --no-method` exits 2.
- `--no-method -p "hello"` dispatches original prompt and no `method_id`.
- Missing method includes the method-list hint.

### Work Tests

- Text `work-log inspect` includes method_id when present.
- JSON `work-log inspect` includes method_id when present.
- Non-method inspect entries remain readable.

## Implementation Notes

- Keep `AgentSession` unchanged.
- Keep `loushang.method` unchanged unless tests reveal a direct type/export need.
- Do not add settings files or config persistence in this phase.
- Keep prompt guidance template unchanged.
- Keep current `method_id` work metadata plumbing unchanged.
