# Fixed MethodPlan P3 Design

## Goal

P3 introduces the first multi-step method execution path while preserving the fast single-turn coding experience.

The target is **fixed linear `MethodPlan` execution**:

```text
MethodDescriptor
  -> MethodCompiler
  -> MethodPlan(mode="fixed" | "single_turn")
  -> WorkRun / WorkStepRun
  -> CodingDomainApp prepares one coding turn per step
  -> AgentSession still executes one prepared turn at a time
```

P3 should also make method metadata easier to evolve toward the long-term methodology standard. In particular, method resources need a multi-dimensional applicability/tag model so Loushang can later select or recommend methods for domains such as coding, presentation/PPT, cowork, research, and other task contexts.

Success criteria:

- Existing no-method and single-turn method behavior remains unchanged.
- A method can compile into a fixed ordered list of steps.
- Each step is observable through work events.
- `WorkRun` records `method_id` and `plan_id`.
- Step events record `step_id`, status, and useful metadata.
- Method data structures gain a stable applicability/tag shape without requiring automatic selection in P3.
- P3 public API does not expose graph workflows, subagents, conductor scheduling, or automatic method evolution.

## Scope

### In Scope

- Extend `loushang.method` types for fixed plans.
- Add a structured `MethodApplicability` data object.
- Keep existing `MethodDescriptor.domain` for compatibility, but treat it as a legacy/convenience projection.
- Extend `MethodStep` with method-aligned fields such as role, phase/activity/task references, expected artifacts, success criteria, and applicability hints.
- Extend `MethodCompiler` to return `mode="fixed"` when method metadata declares fixed steps.
- Keep `mode="single_turn"` as the default for existing skills and methods.
- Extend `loushang.work` with step lifecycle concepts.
- Add work events for step started/completed/failed.
- Add P3 tests for method types, compiler behavior, work event projection, and coding work shell behavior.

### Out Of Scope

- Automatic method selection.
- Fuzzy/semantic method routing.
- Mermaid/D2 execution.
- `METHOD.md` runtime implementation.
- `SOUR.md` runtime implementation.
- Graph workflows, branches, loops, joins, dynamic graph rewrite.
- Subagent lanes, cross-domain execution, conductor scheduling.
- Method evolution proposals or automatic method rewriting.
- TUI/RPC method picker.
- Rewriting `AgentSession` internals.

## Design Principle

P3 should be small in execution behavior and forward-looking in data shape.

That means:

- Execution behavior only supports fixed linear steps.
- Data structures can already carry phase/activity/task/role/guidance/workproduct references.
- Applicability tags should be structured enough for future selection, but P3 should not implement selection beyond existing explicit method id/name selection.

## Domain And Multi-Tag Model

The user-facing intuition is correct: `code`, `ppt`, `co-work`, `research`, etc. are domains or domain-adjacent application categories.

However, they should not be the only tag dimension. Domain is one axis among several:

```text
Method applicability =
  domain
  + task type
  + artifact type
  + modality
  + lifecycle
  + complexity
  + risk
  + toolchain
  + custom tags
```

This follows the existing experimental principle:

```text
Task = How x What x Who x In/Out
```

Recommended canonical examples:

| Dimension | Examples | Meaning |
| --- | --- | --- |
| `domains` | `coding`, `software`, `ppt`, `presentation`, `cowork`, `research`, `business`, `product` | What kind of work/domain app the method fits |
| `task_types` | `exploring`, `designing`, `coding`, `debugging`, `reviewing`, `writing`, `presenting` | What the user is trying to do |
| `contexts` | `oss-library`, `enterprise`, `startup-mvp`, `legacy-system`, `personal-assistant` | Operating context |
| `artifact_types` | `code`, `tests`, `architecture-doc`, `slides`, `research-report`, `decision-record` | Expected work products |
| `modalities` | `text`, `code`, `slides`, `browser`, `voice`, `canvas` | Surface/media modality |
| `toolchains` | `python`, `typescript`, `pytest`, `playwright`, `canva`, `github` | Tool or ecosystem hints |
| `lifecycle` | `new-feature`, `maintenance`, `migration`, `incident`, `proposal` | Work lifecycle |
| `complexity` | `quick`, `standard`, `deep` | Expected depth |
| `risk` | `low`, `medium`, `high` | Operational risk |
| `tags` | arbitrary dimension map | Future/custom project dimensions |

P3 should not force a final ontology. The stable contract is the shape of the applicability object, not a closed enum list.

### Proposed `MethodApplicability`

```python
@dataclass(frozen=True)
class MethodApplicability:
    domains: tuple[str, ...] = ()
    task_types: tuple[str, ...] = ()
    contexts: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()
    modalities: tuple[str, ...] = ()
    toolchains: tuple[str, ...] = ()
    lifecycle: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    complexity: str | None = None
    risk: str | None = None
    tags: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
```

Rules:

- `domains` is multi-valued. A method can fit `("coding", "research")`.
- `domain` on `MethodDescriptor` remains for compatibility and may mirror the first domain.
- `tags` is the escape hatch for dimensions not yet standardized.
- P3 stores and forwards applicability; it does not score or auto-select.
- Future resolver can match explicit user prompts against these dimensions.

Example:

```python
MethodApplicability(
    domains=("coding", "research"),
    task_types=("exploring", "designing"),
    artifact_types=("architecture-doc", "test-plan"),
    toolchains=("python", "pytest"),
    complexity="standard",
    risk="medium",
    tags={
        "domain_app": ("coding",),
        "method_family": ("architecture-first",),
    },
)
```

## Method Type Changes

### `MethodDescriptor`

Add:

```python
applicability: MethodApplicability = field(default_factory=MethodApplicability)
```

Keep existing fields:

```python
domain: str | None = None
phase: str | None = None
meta_role: str | None = None
element_type: str | None = None
metadata: Mapping[str, object] = ...
```

Compatibility rule:

- If frontmatter has `domain`, map it to both `domain` and `applicability.domains`.
- If frontmatter has `domains`, use it for `applicability.domains`; set `domain` to the first value for compatibility.
- If frontmatter has `tags`, preserve it in `applicability.tags` when it is a mapping of string/list-like values.
- Unknown frontmatter remains in `metadata["frontmatter"]`.

### `MethodStep`

Current shape:

```python
@dataclass(frozen=True)
class MethodStep:
    id: str
    title: str
    executor: str
    role_variant: str | None = None
    projection: Mapping[str, object] = ...
```

P3 shape:

```python
@dataclass(frozen=True)
class MethodStep:
    id: str
    title: str
    executor: str = "current_agent"
    phase: str | None = None
    activity: str | None = None
    task: str | None = None
    role: str | None = None
    role_variant: str | None = None
    guidance_refs: tuple[str, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    applicability: MethodApplicability = field(default_factory=MethodApplicability)
    projection: Mapping[str, object] = ...
```

Notes:

- `executor` stays `str`, not an enum, so P4 can add `agent_lane:<id>`, `role:<name>`, or remote executor references.
- `role` and `role_variant` are hints for projection and future multi-agent routing.
- `expected_artifacts` and `success_criteria` are P3-friendly and support future validation.
- `applicability` on a step can narrow or override the plan-level applicability.

### `MethodPlan`

Add:

```python
applicability: MethodApplicability = field(default_factory=MethodApplicability)
expected_artifacts: tuple[str, ...] = ()
success_criteria: tuple[str, ...] = ()
```

Keep:

```python
id: str
method_id: str
mode: str
steps: tuple[MethodStep, ...]
phase: str | None = None
activity: str | None = None
task: str | None = None
metadata: Mapping[str, object] = ...
```

P3 accepted modes:

- `single_turn`
- `fixed`

Other modes such as `autonomous`, `hybrid`, `graph`, or `conductor` remain future values and should fail clearly if encountered by a P3 executor.

### `MethodContext`

Extend with applicability hints:

```python
@dataclass(frozen=True)
class MethodContext:
    domain: str | None = None
    task: str | None = None
    applicability: MethodApplicability = field(default_factory=MethodApplicability)
    metadata: Mapping[str, object] = ...
```

P3 compiler/projector can pass this through. P3 selector does not use it for automatic selection.

## Fixed Step Source

P3 can support fixed steps from frontmatter or metadata without requiring `METHOD.md`.

Example `methods/task/review/SKILL.md`:

```markdown
---
name: review-with-tests
description: Review code changes and verify with focused tests
type: task
domains: [coding]
task_types: [reviewing, verifying]
complexity: standard
steps:
  - id: inspect
    title: Inspect current changes
    phase: EXPLORE
    role: EXPLORER
    success_criteria:
      - Changed files and intent are understood
  - id: test
    title: Run focused regression tests
    phase: VERIFY
    role: VALIDATOR
    expected_artifacts:
      - test-report
    success_criteria:
      - Relevant tests pass or failures are captured
---

Use this method to inspect changes before giving review findings.
```

Compiler behavior:

- No `steps` -> existing `single_turn` plan.
- `steps` present and valid -> `fixed` plan.
- Invalid `steps` -> clear compiler error.

P3 should keep parsing conservative:

- `steps` must be a list of mappings.
- Each step needs `id` and `title`.
- Optional fields use string or list of strings.
- Unknown step fields go into `projection` or step metadata only if explicitly supported; otherwise preserve in `projection["frontmatter"]` or plan metadata.

## Work Type Changes

### `WorkRun`

Add:

```python
plan_id: str | None = None
current_step_id: str | None = None
```

Existing:

```python
method_id: str | None = None
```

### `WorkStepRun`

Add a new data object:

```python
WorkStepStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "cancelled",
]

@dataclass(frozen=True)
class WorkStepRun:
    run_id: str
    plan_id: str
    step_id: str
    sequence: int
    status: WorkStepStatus
    method_id: str | None = None
    title: str | None = None
    phase: str | None = None
    activity: str | None = None
    task: str | None = None
    role: str | None = None
    expected_artifacts: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
```

P3 does not need durable step store beyond event log unless implementation naturally benefits from in-memory tracking. The event log remains the replay source.

### `WorkEvent`

Add event kinds:

- `WorkPlanStarted`
- `WorkStepStarted`
- `WorkStepCompleted`
- `WorkStepFailed`
- `WorkPlanCompleted`
- `WorkPlanFailed`

Payload examples:

```python
{
    "plan_id": "plan:review-with-tests",
    "method_id": "review-with-tests",
    "step_id": "inspect",
    "step_sequence": 1,
    "step_title": "Inspect current changes",
    "phase": "EXPLORE",
    "role": "EXPLORER",
    "expected_artifacts": [],
    "success_criteria": ["Changed files and intent are understood"],
}
```

Delivery hints:

- `WorkPlanStarted`: `coalesce`
- `WorkStepStarted`: `coalesce`
- `WorkStepCompleted`: `coalesce`
- `WorkStepFailed`: `immediate`
- `WorkPlanCompleted`: `final_only`
- `WorkPlanFailed`: `immediate`

## Coding Domain Integration

P3 should not make `CodingDomainApp` execute the whole plan. It should prepare one step at a time.

Add a step-aware request path:

```python
@dataclass(frozen=True)
class CodingDomainRequest:
    user_input: str
    method: str | None = None
    cwd: Path | None = None
    step_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
```

Add to prepared turn metadata:

```python
plan_id: str | None
step_id: str | None
method_id: str | None
```

Behavior:

- No method -> unchanged.
- Single-turn method -> unchanged except optional `plan_id`.
- Fixed plan + no `step_id` -> prepare first step.
- Fixed plan + `step_id` -> prepare that step.
- Invalid `step_id` -> clear error.

The work layer can call `CodingDomainApp.prepare_turn(...)` for each step, or a thin P3 coordinator can do that. The domain app should remain a preparation boundary, not a scheduler.

## P3 Execution Flow

Minimal flow:

```text
CLI / caller submits prompt + method
  -> MethodLoader/Selector finds descriptor
  -> MethodCompiler compiles plan
  -> CodingWorkShell creates WorkRun(method_id, plan_id)
  -> if plan.mode == single_turn:
       existing P2 behavior
     else if plan.mode == fixed:
       emit WorkPlanStarted
       for each step in order:
         emit WorkStepStarted
         prepare step prompt
         run one AgentSession prompt
         if success: emit WorkStepCompleted
         if failure: emit WorkStepFailed and WorkPlanFailed
       emit WorkPlanCompleted
```

P3 can treat each step as one prepared coding turn. It does not need a separate planner/conductor loop.

Failure behavior:

- First failing step stops the plan.
- Record failure payload with `step_id`, error message, and source event reference if available.
- No automatic retry in P3.
- User can rerun manually.

## Method Selection Implications

P3 still uses explicit selection:

```text
--method review-with-tests
```

The multi-dimensional tags are stored for future resolver work. Future automatic selection can do:

```text
prompt -> intent/domain classifier -> MethodContext(applicability=...)
       -> MethodResolver.match(...)
       -> selected MethodDescriptor
```

P3 should not implement this. It only makes the data available.

## Relationship To Long-Term Standards

### `SKILL.md`

Still the atomic method element resource and P3 loader input.

### `METHOD.md`

Should be kept as the future composite method manifest. P3 should not require it, but the P3 `MethodPlan` shape should align with it:

- imports
- phase/activity/task/role/guidance/workproduct references
- applicability
- fixed plan template
- gates
- expected artifacts
- evolution policy

### `SOUR.md`

Can remain a future role-source standard. It should not affect P3 execution.

If introduced later, it should feed `role` / `role_variant` projection and method governance, not replace method plans or memory.

### Mermaid / D2

Not a runtime schema in P3.

Future use:

- render `MethodPlan` to Mermaid for visibility.
- parse a limited Mermaid subset as a `METHOD.md` adapter.

## Error Handling

- Unsupported plan mode -> clear error before agent execution.
- Invalid step schema -> compiler error with source path and step index.
- Missing method -> existing P2 behavior.
- Fixed plan with zero steps -> compiler error.
- Step execution failure -> step failed + plan failed events.
- Empty guidance on a step -> run original user input plus step context if available; do not fail only because guidance is empty.

## Testing Strategy

### Method Tests

- `MethodApplicability` defaults are empty.
- Frontmatter `domain` maps into applicability domains.
- Frontmatter `domains` maps into applicability domains.
- Frontmatter tags map into `MethodApplicability.tags`.
- Existing skill-backed methods still compile to `single_turn`.
- Method with valid `steps` compiles to `fixed`.
- Invalid steps fail clearly.
- Fixed plan preserves phase/activity/task/role/expected artifacts/success criteria.

### Work Tests

- `WorkRun` can carry `plan_id` and `current_step_id`.
- `WorkStepRun` serializes through event payloads.
- Work event log records plan/step lifecycle.
- Replay can recover the sequence of step events for a run.

### Coding Domain Tests

- Single-turn method behavior stays unchanged.
- Fixed plan without `step_id` prepares first step.
- Fixed plan with `step_id` prepares the requested step.
- Missing step id fails clearly.
- Prepared turn includes method/plan/step metadata.

### Regression Tests

- No method remains unchanged.
- Existing `--method` single-turn path remains unchanged.
- Method defaults from P2.7 still apply.
- `--no-method` still disables all method behavior.

## Implementation Notes

- Keep new data classes frozen.
- Prefer tuples for public sequence fields.
- Keep `mode` as `str`, not a `Literal`, to avoid future breaking changes.
- Keep tag values normalized to lowercase kebab-case where loader can do so safely; do not mutate arbitrary user metadata.
- Do not add automatic resolver behavior in P3.
- Do not add new CLI flags unless implementation needs a hidden test-only path.
- Keep docs explicit that domain tags are not equivalent to domain apps, though they can use the same names.

## Open Questions

- Should `domain` become deprecated in docs once `applicability.domains` exists, or remain a convenience field permanently?
- Should P3 expose a `method plan show` command to inspect compiled fixed plans before execution?
- Should step success criteria be model-visible by default, or only included in work metadata?
- Should P3 fixed plan execution run all steps automatically, or should the first version only prepare one selected step per operation?

Recommended defaults:

- Keep `domain` as convenience.
- Defer `method plan show` unless implementation is trivial.
- Include success criteria in both model-visible step guidance and work metadata.
- Run fixed steps automatically in non-interactive prompt/print/json paths only after tests prove single-turn behavior is unchanged.
