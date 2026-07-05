# TUI Model Selection And Method Routing Design

## Status

Ready for user review.

## Context

Issue #242 asks the native TUI to remember the last model selected through
`/model`. The immediate user-facing problem is small: after choosing a model
interactively, the next TUI session should start with that model when it is
still valid.

The design has to leave room for a larger direction: methodology-driven work
may later use different models for different plan steps. A method run may use a
planning model, a code model, a review model, a cheap summarization model, or a
long-context model in one logical task.

The current code already has useful boundaries:

- `ModelSelection` identifies a model by `provider`, `model_id`, and optional
  `endpoint_id`.
- `SettingsManager` can persist `default_model` in session, global, or project
  settings.
- `/model` currently changes the active session model through
  `session.set_model()`.
- `MethodPlan`, `MethodStep`, `MethodProjection`, `WorkStepRun`, and
  `WorkEvent` already carry metadata where future model routing facts can be
  recorded.
- `ModelRegistry` resolves `ModelSelection` against the active AI model
  registry and current layered model resources.

The key design problem is not just where to save `/model`. It is what `/model`
means once methods can route work across multiple models.

## Goals

Current #242 goals:

- Make `/model` persistence useful for current TUI sessions.
- Keep manual model choice, session history, project policy, and method routing
  as separate runtime facts.
- Avoid writing personal model choices into project settings by default.
- Preserve explicit user overrides.
- Ensure startup revalidates the persisted default model against the current
  registry and endpoint facts before using it.

Future compatibility goals:

- Allow future method steps to request model roles or capabilities without
  forcing users to hard-code provider/model IDs into every method.
- Ensure future method steps revalidate routed models against current registry,
  auth, endpoint, policy, and environment facts.
- Record enough routing information in work/session events for debugging,
  replay, export, and cost analysis.

## Non-Goals

- Do not implement multi-model routing in the #242 slice.
- Do not introduce automatic method selection.
- Do not make `/model` rewrite method definitions.
- Do not make `AgentSession.set_model()` implicitly write persisted settings.
- Do not make project `.loushang/settings.json` a sink for interactive personal
  preferences.
- Do not infer provider or endpoint facts from model names when the registry is
  ambiguous.
- Do not add budget optimization, live benchmarking, or quality scoring in the
  first persistence slice.

## Decisions

### Current Slice Decisions

`/model` sets the active session model and persists the user's default model
preference to global user settings.

The persisted target is:

```text
~/.loushang/coding/settings.json
```

The persisted field is the existing structured `default_model`:

```json
{
  "default_model": {
    "provider": "openai",
    "model_id": "gpt-5.5",
    "endpoint_id": "openai-responses"
  }
}
```

`endpoint_id` should be preserved when the selected model came from a concrete
endpoint. This avoids the common ambiguity where the same provider/model ID is
available through multiple endpoints.

`/model` must not write project settings by default. Project settings are team
or repository policy; `/model` is a user's interactive preference. A future
explicit command may save a project default, but that should be opt-in and
visibly different from ordinary model switching.

If a project already declares an explicit `default_model`, that project default
continues to win on the next startup in that project. Ordinary `/model` still
changes the current running session and saves the user's global preference, but
it does not silently override a team/project default.

`session.set_model()` remains a runtime operation. It should update the current
agent/session state and append session history, but persistence should be owned
by the TUI command path or another explicit control-plane command. This keeps
RPC, extensions, tests, retry flows, and temporary switches from unexpectedly
modifying user settings.

Startup should treat persisted `default_model` as a candidate, not a guarantee.
The bootstrap path must resolve it through the current `ModelRegistry`. If the
model is missing, ambiguous, or points at an unavailable endpoint, startup
should fall back to the existing registry fallback behavior and surface a
recoverable diagnostic.

Missing auth is not a #242 fallback trigger. Current session startup can keep a
selected model active and surface auth guidance later through the auth bridge.
Changing that behavior belongs with the future router/policy layer, not the
first persistence slice.

### Long-Term Decisions

`/model` is not the long-term multi-model scheduler. It is the user's default
model preference and fallback.

Future method execution should route through a dedicated `ModelRouter` that
accepts a model request context and returns a resolved model decision. The
router should understand:

- explicit CLI/session model overrides;
- pinned session model choices;
- method step model roles;
- method step capability requirements;
- project model policy;
- user role mappings;
- global `default_model`;
- registry availability and auth;
- fallback and diagnostic rules.

Method steps should request model roles or capabilities, not concrete provider
IDs by default. Examples:

```json
{
  "model_role": "reviewer",
  "required_capabilities": ["high_reasoning", "long_context"]
}
```

Concrete provider/model selections remain allowed for advanced use, but they
should be explicit and auditable because they encode environment-specific
assumptions.

The long-term meaning of `/model` is:

> Prefer this model for ordinary turns and as the fallback for method steps that
> do not request a stronger model role or capability.

If users need stronger control, add explicit commands instead of overloading
ordinary `/model`:

```text
/model gpt-5.5
/model --pin gpt-5.5
/model --role reviewer claude-opus-4-8
/model --clear-role reviewer
```

Meanings:

- `/model X` sets the active model and default preference.
- `/model --pin X` forces this session to use X unless a hard policy blocks it.
- `/model --role reviewer X` maps the reviewer role to X in user settings.
- `/model --clear-role reviewer` removes the user role mapping.

These commands are future scope. The #242 slice should not implement them, but
the persistence model should not block them.

## Model Preference And Policy Layers

Use separate configuration concepts:

### User Preference

User preference belongs in global user settings:

```json
{
  "default_model": {
    "provider": "openai",
    "model_id": "gpt-5.5",
    "endpoint_id": "openai-responses"
  },
  "model_routing": {
    "roles": {
      "reviewer": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-8",
        "endpoint_id": "anthropic-messages"
      }
    },
    "fallback": "default_model"
  }
}
```

Only `default_model` is in the current slice. `model_routing` is a reserved
future shape.

### Project Policy

Project policy belongs in project settings and should be explicit. A project may
also declare an explicit `default_model` as a team default, but ordinary
interactive `/model` must not create or mutate that value.

```json
{
  "default_model": {
    "provider": "openai",
    "model_id": "gpt-5.5",
    "endpoint_id": "openai-responses"
  },
  "model_policy": {
    "allowed_providers": ["openai", "anthropic"],
    "allowed_roles": ["planner", "coder", "reviewer"],
    "deny_endpoints": ["untrusted-local"]
  }
}
```

Project policy may constrain routing, but ordinary `/model` should not create or
mutate this policy.

### Session Runtime State

Session runtime state records what actually happened:

- the active model after a `/model` command;
- model changes in session history;
- method step routing decisions;
- fallback reason, if the requested model was not used.

This state is separate from user defaults because replay and audit need facts,
not preferences.

## Proposed Architecture

### Current Slice

Add an explicit persistence step to the TUI model selection path:

```text
/model selection
  -> resolve selected choice from available model details
  -> build a ModelSelection with provider, model_id, endpoint_id
  -> session.set_model(selection)
  -> settings_manager.set_default_model(selection, scope="global")
  -> show "Model set" status
```

The persistence call should happen only after `session.set_model(selection)`
succeeds. A model that cannot be applied should not become the saved default.

Persist from the selected choice or resolved `Model`, not by reading the current
model back from `session.get_model_selection()` after the switch. Some existing
selection helpers expose only provider/model ID and can drop `endpoint_id`; the
persistence path must preserve endpoint identity when the selected model came
from an endpoint-aware model detail.

All TUI model entry points should share the same persistence wrapper. Plain
mode, screen mode typed `/model`, model selector submit, and the settings model
page all eventually call model selection helpers today. If only one entry point
adds persistence, #242 will be inconsistent.

The persistence API can be a thin helper on the session facade or UI command
handler, but it should not hide inside the low-level `set_model()` method.

Recommended naming:

```python
remember_model_selection(selection, scope="global")
```

or:

```python
persist_model_selection(selection, scope="global")
```

The name should communicate durable settings writes, not ordinary runtime model
switching.

### Future Router

Introduce a future `ModelRouter` behind a narrow interface:

```python
@dataclass(frozen=True)
class ModelRequest:
    reason: str
    method_id: str | None = None
    plan_id: str | None = None
    step_id: str | None = None
    role: str | None = None
    required_capabilities: tuple[str, ...] = ()
    preferred_model: ModelSelection | None = None
    pinned_model: ModelSelection | None = None


@dataclass(frozen=True)
class ModelDecision:
    selection: ModelSelection
    source: str
    requested_role: str | None = None
    fallback_from: ModelSelection | None = None
    diagnostics: tuple[str, ...] = ()
```

The initial implementation can be trivial:

```text
if pinned model exists and is allowed -> use pinned
else if preferred/default model exists and is valid -> use preferred/default
else registry fallback
```

Later implementations can add role and capability matching without changing
method execution callers.

Router capability labels are semantic routing labels, not raw `models.json`
keys. The first router should map them onto the current catalog shape instead
of copying catalog field names into method definitions:

| Router label | Current catalog source |
| --- | --- |
| `reasoning` | `capabilities.reasoning` |
| `tool_use` | `capabilities.toolUse` / `Capabilities.tool_use` |
| `structured_output` | `capabilities.structuredOutput` / `Capabilities.structured_output` |
| `vision` | `capabilities.input` contains `image` |
| `long_context` | `capabilities.contextWindow` above a configured threshold |
| `high_reasoning` | `capabilities.reasoning` plus a curated tier/family policy |
| `cheap` | `pricing` below a configured threshold |

This keeps method hints stable if the catalog keeps camelCase JSON keys while
the runtime domain model exposes snake_case Python attributes.

## Method Integration

Current `MethodStep` should not grow hard dependencies on provider-specific
models in the first slice. For future compatibility, method compilation and
projection may carry model hints through existing maps:

```json
{
  "constraint": {
    "model_role": "planner",
    "required_capabilities": ["long_context"]
  }
}
```

Using `constraint` is the safer near-term convention because current coding
domain preparation forwards the source constraint into prepared-turn metadata.
If a future router reads directly from `MethodProjection`, the hint can be
promoted or copied into typed projection fields then.

Long-term, promote this to typed fields if the convention becomes common:

```python
@dataclass(frozen=True)
class MethodStep:
    ...
    model_role: str | None = None
    model_requirements: ModelRequirements = field(default_factory=ModelRequirements)
```

Do not add typed fields until at least one method runtime path consumes the
metadata. The near-term safe move is to preserve and project the hints.

Every method step run should eventually record the selected model decision in
`WorkStepRun.metadata` or a dedicated work event payload:

```json
{
  "model_decision": {
    "selection": {
      "provider": "openai",
      "model_id": "gpt-5.5",
      "endpoint_id": "openai-responses"
    },
    "source": "role:reviewer",
    "requested_role": "reviewer",
    "fallback_from": null,
    "diagnostics": []
  }
}
```

This is future scope, but the design should reserve the concept now.

## Startup Resolution

Recommended startup precedence for ordinary TUI sessions:

1. Settings compose global, then project, then session patches.
2. Bootstrap resolves the composed `default_model` candidate.
3. `AgentSession` may restore a model from existing session history when
   resuming.
4. Explicit CLI model override is applied after session creation and wins for
   the running session.
5. Future session-level pinned model, if introduced, should win over defaults
   but remain below explicit CLI override.
6. Registry fallback is used when no valid default candidate exists.

Project policy constrains every resolved choice above. It does not become the
user's fallback preference, and ordinary `/model` does not rewrite it.

If `default_model` is unavailable:

- do not delete it automatically;
- use the normal fallback model for this session;
- emit a recoverable diagnostic with provider, model ID, endpoint ID, and reason;
- let the user fix it with `/model` or model resource/auth changes.

## Error Handling

Persisting a model preference can fail after the runtime model switch succeeds.
The TUI should keep the session on the selected model and show a warning such
as:

```text
Model changed to openai:gpt-5.5, but saving the default failed: <reason>
```

Applying the runtime model can fail before persistence. In that case:

- do not write settings;
- keep the previous active model;
- show the model resolution/auth error.

Startup resolution can fail to use the saved default. In that case:

- use a fallback model if one exists;
- record a diagnostic;
- keep the saved preference unchanged.

Future method routing failures should distinguish:

- policy denial;
- missing model;
- ambiguous model;
- missing auth;
- missing endpoint/environment;
- capability mismatch;
- no fallback available.

## Testing

Current slice tests:

- `/model` calls runtime `set_model()` and then persists global
  `default_model`.
- Failed `set_model()` does not persist.
- Persistence failure leaves runtime model changed and emits a warning.
- `endpoint_id` round-trips through settings.
- Startup uses saved `default_model` when valid.
- Startup falls back with a diagnostic when saved default is missing,
  ambiguous, or endpoint-unavailable.
- Missing auth keeps the selected model behavior consistent with the current
  auth bridge and surfaces auth guidance rather than silently rewriting the
  user's saved default.
- Project settings are not modified by ordinary `/model`.
- Project explicit `default_model` still overrides the saved global preference
  on startup.
- Existing explicit CLI model override still wins.
- Plain mode, screen mode, selector submit, and settings-page model selection
  all use the same persistence behavior.

Future router tests:

- default model fallback;
- pinned model override;
- role mapping override;
- method step role request;
- capability-based fallback;
- project policy denial;
- diagnostic payload recorded in work events.

## Rollout

### Phase 1: #242 Persistence

- Add explicit persistence after successful TUI `/model` selection.
- Store structured `default_model` in global user settings.
- Keep `set_model()` runtime-only.
- Add focused tests around persistence and startup fallback.

### Phase 2: Router Skeleton

- Add `ModelRequest` and `ModelDecision` internal types.
- Add a trivial `ModelRouter` that returns explicit override, default model, or
  registry fallback.
- Do not change method behavior yet.

### Phase 3: Method Hints

- Preserve `model_role` and `required_capabilities` hints from method step
  projection/constraint metadata.
- Record resolved model decisions in work metadata.

### Phase 4: Multi-Model Method Routing

- Add user role mappings.
- Add project model policy.
- Add capability matching against model registry facts.
- Add explicit `/model --pin` and `/model --role` commands if user workflows
  need them.

## Open Questions

- Should global `default_model` be a simple single preference, or should it
  become workspace-keyed memory once users regularly work across projects with
  different model stacks?
- Should project settings allow an explicit project `default_model`, or only
  model policy and role recommendations?
- What is the minimal capability vocabulary for model routing:
  `high_reasoning`, `long_context`, `cheap`, `vision`, `tool_use`, and
  `structured_output` are likely enough for the first router.
- Should role mappings live under `model_routing.roles` or a more general
  `routing.models.roles` namespace if future non-model routing also appears?
