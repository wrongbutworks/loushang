# Method Deviation And Evolution Draft

## Status

Draft.

Created on 2026-06-04.

This note records the current design direction for method deviation,
constraint, audit, and evolution. It is not an implementation plan yet.

Related notes:

- [P3 Fixed MethodPlan Flow Research](./p3-fixed-methodplan-flow-research.md)
- [Fixed MethodPlan P3 Design](../../specs/2026-06-03-fixed-methodplan-p3-design.md)
- [Loushang Work / Method / Channel / Harness Architecture Draft](./loushang-work-method-channel-harness-architecture.md)

## Problem

Loushang methods should make agent work more reliable, inspectable, and
teachable. They should not turn methodology into a rigid cage.

The method runtime therefore needs to distinguish three concerns:

- guidance: what the method recommends and why.
- constraint: which parts are optional, adaptable, approval-gated, or mandatory.
- audit: what actually happened, including justified deviations.

Useful deviations should also be able to become method evolution material. A
successful adaptation should not silently rewrite the method, but it should be
recorded, reviewed, and promotable into a future method version.

## Core Position

A method proposes an expected path. Work records the actual path.

The default posture should be:

```text
method proposes -> agent adapts when justified -> work records facts
  -> human/critic reviews -> method evolves deliberately
```

This keeps methodology operational without making it brittle:

- Methods provide strong defaults and shared vocabulary.
- Constraints are explicit, not assumed.
- Deviations are allowed when policy permits them.
- Deviations must be visible in the work record.
- Effective deviations enter an evolution candidate pool before changing the
  method itself.

## Boundary

### `loushang.method`

`loushang.method` owns the expected work shape:

- method identity and applicability.
- compiled method plan.
- method step guidance.
- step flexibility and constraint policy.
- audit requirements declared by the method.
- optional alternative paths declared by method authors.

It does not own execution facts.

### `loushang.work`

`loushang.work` owns actual execution facts:

- work run status.
- plan run status.
- step run status.
- skipped, adapted, blocked, failed, or completed steps.
- deviation records.
- evidence and approval references.
- replay and projection from event logs.

It does not redefine method intent.

### Domain Apps

Domain apps, such as `loushang.coding`, translate method guidance into a domain
turn. They may choose how to adapt within policy, but they should emit work
events that make the adaptation inspectable.

### Harness

The agent harness executes prepared turns. It should not carry method semantics
directly. Long term, UI status should consume work/method projections instead of
embedding coding-specific concepts in terminal primitives.

## Three-Layer Step Semantics

Each method step can be understood through three layers.

### 1. Guidance

Guidance describes the recommended behavior:

- goal.
- rationale.
- instructions.
- expected artifacts.
- success criteria.
- useful references.

Guidance answers: what should the agent try to do?

### 2. Constraint

Constraint describes how strictly the step should be followed.

Recommended initial levels:

| Level | Meaning |
| --- | --- |
| `advisory` | The step is guidance only. It may be changed or skipped without a special gate. |
| `reasoned` | The step may be skipped, merged, reordered, or adapted, but a reason must be recorded. |
| `evidence` | Deviation is allowed only with supporting evidence, such as existing tests, prior context, or observed repo state. |
| `approval` | Deviation requires explicit user, policy, or system approval. |
| `mandatory` | The step must be executed unless the run is blocked or failed. |

Constraint answers: how much freedom does the agent have?

### 3. Audit

Audit describes what must be recorded:

- planned step id.
- actual action.
- final status.
- deviation type, if any.
- reason.
- evidence references.
- approval reference, if required.
- outcome and risk.

Audit answers: what facts must be available later?

## Suggested Method Shape

The exact schema is not frozen, but method resources should move toward a shape
like this:

```yaml
steps:
  - id: inspect-context
    title: Inspect current context
    guidance:
      goal: Understand the current repository state before changing behavior.
      expected_artifacts:
        - relevant files identified
        - current branch and worktree state known
    constraint:
      level: reasoned
      can_skip: false
      can_merge: true
      can_reorder: false
      requires_reason: true
    audit:
      record:
        - status
        - reason
        - evidence

  - id: run-verification
    title: Run focused verification
    constraint:
      level: evidence
      can_skip: true
      requires_reason: true
      requires_evidence: true
    alternatives:
      - id: explain-unavailable-verification
        applies_when: verification cannot run in the current environment
        guidance:
          goal: Explain why verification could not run and record residual risk.
        required_evidence:
          - command attempted
          - failure output or environment limitation
```

Compatibility rule: existing methods without explicit constraint metadata should
continue to behave as method guidance. They should not suddenly become hard
workflow locks.

## Work Deviation Record

When actual work diverges from the compiled method plan, `loushang.work` should
eventually be able to record a structured deviation.

Sketch:

```python
@dataclass(frozen=True)
class WorkStepDeviation:
    step_id: str
    policy_level: str
    deviation_type: str
    reason: str
    evidence_refs: tuple[str, ...] = ()
    approval_ref: str | None = None
    risk: str | None = None
    outcome: str | None = None
```

Potential `deviation_type` values:

- `skipped`
- `adapted`
- `merged`
- `reordered`
- `blocked`
- `approval_denied`

This is work-layer fact data. It should be derived from events and projected
into `WorkPlanRun` / `WorkStepRun` views.

## Method Evolution

Deviation is not failure by default. It is raw material.

Useful deviations should follow a deliberate evolution loop:

```text
Observation -> Candidate -> Review -> Promotion -> Method Version
```

### Observation

The work log records that a step was skipped, adapted, merged, reordered, or
blocked, together with reason and evidence.

### Candidate

A reviewer, CLI command, background analyzer, or future method-evolution app can
turn repeated or high-value observations into candidates.

Sketch:

```yaml
candidate_id: method-evolution:dev-workflow:verification-fast-path
method_id: dev-workflow
step_id: run-verification
observed_change: skipped full suite and ran focused tests
reason: change touched only documentation
evidence:
  - files changed were markdown only
  - focused link check passed
outcome: accepted by reviewer
candidate_change:
  type: add-alternative
  alternative_id: docs-only-verification
```

### Review

A human reviewer, critic agent, or policy gate decides whether the candidate is:

- promoted.
- revised.
- rejected.
- kept for more observations.

### Promotion

Promotion updates the method resource deliberately. It may add an alternative,
relax a constraint, strengthen a constraint, or document an anti-pattern.

The runtime should not silently mutate method resources from one successful
deviation.

## Initial Implementation Direction

This note does not require immediate implementation. When implemented, the
lowest-risk sequence is:

1. Add method-side constraint/audit metadata parsing and projection without
   enforcement.
2. Extend work step events and projections with optional deviation metadata.
3. Show deviations in CLI/TUI work inspection.
4. Add a reviewed evolution candidate format.
5. Only then consider enforcement, approvals, and method promotion tooling.

This ordering keeps existing method execution stable while making the future
semantics inspectable.

## Non-Goals For The First Slice

- No automatic method rewriting.
- No hidden agent-only deviation.
- No graph workflow execution.
- No LLM-generated dynamic plan mutation during P3 fixed-plan execution.
- No generic TUI semantic migration yet.
- No hard enforcement for existing method resources that do not declare
  constraint policy.

## Open Questions

- Should the default implicit level be `advisory` or `reasoned` for methods that
  do not declare a constraint?
- Should approvals live in `loushang.work`, `loushang.policy`, or a later
  harness-level gate?
- Should method evolution candidates be stored as work artifacts, method
  artifacts, or a separate `loushang.evolution` concept?
- How much evidence is enough for promoting a deviation into a method
  alternative?
- Should failed deviations become anti-pattern guidance in the method resource?
