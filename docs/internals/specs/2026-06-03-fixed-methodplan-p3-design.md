# Fixed MethodPlan P3 Design

## Status

Current status as of 2026-06-04: P3 fixed MethodPlan is partially implemented
on `main`.

Already landed:

- P3.0: `MethodApplicability` data model and frontmatter parsing.
- P3.0.1: method CLI JSON/text output exposes applicability metadata.
- P3.1: fixed `MethodPlan` compilation from method metadata.
- P3.2: work plan and step lifecycle events, replay, and inspect summaries.
- P3.2.x: planned step policy, deviation metadata, and tool approval audit
  events are projected into durable work logs.
- P3.3: coding-domain non-interactive paths prepare and execute one coding turn
  per fixed method step.

Remaining hardening:

- Ensure assistant-level failures such as `stop_reason="error"` or
  `stop_reason="aborted"` produce `WorkStepFailed` / `WorkPlanFailed` instead
  of completed step events.
- Keep TUI/RPC method picking and step status visualization out of this design
  until the work-log semantics are trustworthy.

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
- Method data structures keep the existing stable applicability/tag shape without requiring automatic selection in P3.
- P3 public API does not expose graph workflows, subagents, conductor scheduling, or automatic method evolution.

## Scope

### In Scope

- Extend `loushang.method` types for fixed plans.
- Use the existing structured `MethodApplicability` data object.
- Keep existing `MethodDescriptor.domain` for compatibility, but treat it as a legacy/convenience projection.
- Preserve current `MethodStep` fields and carry method-aligned details through
  projection, constraint, audit, metadata, and applicability hints.
- Extend `MethodCompiler` to return `mode="fixed"` when method metadata declares fixed steps.
- Keep `mode="single_turn"` as the default for existing skills and methods.
- Extend `loushang.work` with step lifecycle concepts.
- Add work events for step started/completed/failed.
- Add P3 tests for method types, compiler behavior, work event projection, and coding work shell behavior.

### Implementation Slices

- P3.1: compile fixed `MethodPlan` steps from method metadata. Landed.
- P3.2: add work plan and step lifecycle events. Landed.
- P3.2.5: record step policy/deviation metadata. Landed.
- P3.3: execute fixed `MethodPlan` steps through the coding domain app in
  non-interactive CLI paths. Landed; the former tracking issue was deleted
  after merge.
- P3.4: harden failed-step semantics for assistant-level failures. Remaining.

The P3.0 applicability foundation is already part of main and is not repeated in
these implementation slices.

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

### Current `MethodApplicability`

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

Already has:

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
    constraint: Mapping[str, object] = ...
    audit: Mapping[str, object] = ...
    applicability: MethodApplicability = field(default_factory=MethodApplicability)
```

Future fixed-plan shape can add direct fields if they remove real complexity:

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
- In current P3, planned constraints are carried through `constraint`, audit
  requirements through `audit`, and model-visible guidance through `projection`.
- `expected_artifacts` and `success_criteria` remain useful future fields, but
  are not required for the current P3 execution path.
- `applicability` on a step can narrow or override the plan-level applicability.

### `MethodPlan`

Already has:

```python
applicability: MethodApplicability = field(default_factory=MethodApplicability)
```

Future plan shape can add:

```python
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

Already has applicability hints:

```python
@dataclass(frozen=True)
class MethodContext:
    domain: str | None = None
    task: str | None = None
    metadata: Mapping[str, object] = ...
    applicability: MethodApplicability = field(default_factory=MethodApplicability)
```

P3 compiler/projector can pass this through. P3 selector does not use it for automatic selection.

## Fixed Step Source

P3 supports fixed steps from frontmatter without requiring `METHOD.md`.

Example `methods/task/review/SKILL.md`:

```markdown
---
name: review-with-tests
description: Review code changes and verify with focused tests
type: task
domains: [coding]
task_types: [reviewing, verifying]
complexity: standard
plan_mode: fixed
steps: [inspect, verify]
step_titles:
  inspect: Inspect current changes
  verify: Run focused checks
step_guidance:
  inspect: Read changed files and summarize intent.
  verify: Run focused tests or explain why they cannot run.
step_constraints:
  inspect:
    level: reasoned
    requires_reason: true
  verify:
    level: evidence
    requires_evidence: true
step_audit:
  inspect:
    record: [status, reason]
  verify:
    record: [status, reason, evidence]
---

Use this method to inspect changes before giving review findings.
```

Compiler behavior:

- No `steps` -> existing `single_turn` plan.
- `plan_mode: fixed` plus valid `steps` -> `fixed` plan.
- Invalid `steps` -> clear compiler error.

P3 should keep parsing conservative:

- `steps` is currently a list of non-empty string step ids.
- `step_titles`, `step_guidance`, `step_constraints`, and `step_audit` are
  optional maps keyed by step id.
- Each fixed step currently executes on `current_agent`.
- Unknown frontmatter remains preserved in descriptor metadata; it is not
  promoted to execution semantics unless compiler/projector code explicitly
  supports it.

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

Already covered by P3.0/P3.0.1 and should remain regression coverage:

- `MethodApplicability` defaults are empty.
- Frontmatter `domain` maps into applicability domains.
- Frontmatter `domains` maps into applicability domains.
- Frontmatter tags map into `MethodApplicability.tags`.

P3 fixed-plan method coverage:

- Existing skill-backed methods still compile to `single_turn`.
- Method with valid `steps` compiles to `fixed`.
- Invalid steps fail clearly.
- Fixed plan preserves step guidance, planned constraints, audit policy, step
  order, and applicability.

### Work Tests

- `WorkRun` can carry `plan_id` and `current_step_id`.
- `WorkStepRun` serializes through event payloads.
- Work event log records plan/step lifecycle.
- Replay can recover the sequence of step events for a run.

### Coding Domain Tests

- Single-turn method behavior stays unchanged.
- `prepare_turn()` remains compatible and returns the first prepared turn.
- `prepare_turns()` prepares all fixed steps in order.
- Prepared turns include method/plan/step metadata.
- Prepared turns include planned constraint and audit policy metadata.

### Regression Tests

- No method remains unchanged.
- Existing `--method` single-turn path remains unchanged.
- Method defaults from P2.7 still apply.
- `--no-method` still disables all method behavior.
- Non-interactive fixed method execution calls one runner turn per prepared
  step and only completes the plan on the last step.

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
