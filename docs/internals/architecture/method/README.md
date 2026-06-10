# Loushang Method Architecture

[Architecture](../README.md)

## Scope

本文档是当前 `loushang.method` 的 canonical architecture note。

历史 design specs 和 experimental methodology 文档可以提供背景和演进理由，但当它们与当前代码、测试或本文件冲突时，优先以当前代码、测试和本文件为准。

## Definition

Method 是面向一类任务的结构化工作契约。

它定义：

- 何时适用
- agent 应扮演什么角色
- 工作处于哪个阶段
- 应按什么 workflow 推进
- 需要遵守哪些 constraints、audit points 和 gates
- 应产出什么 work products 与 acceptance results

换成运行时语义：

```text
Method = Work Contract
Skill  = Local expertise or capability guidance
Tool   = Executable action
Policy = Permission and approval boundary
Work   = Runtime event, log, and projection layer
```

## Current Boundary

`loushang.method` owns:

- method resources
- skill-backed method adaptation
- method registry and explicit selection
- method compile
- method projection
- `MethodPlan` / `MethodStep` data semantics

`loushang.method` does not own:

- coding CLI option parsing
- coding session execution
- agent loop internals
- tool execution policy
- work log persistence
- Native TUI rendering or playback

Coding-specific method usage is bridged through `loushang.coding.domain`.
Runtime execution observability is projected through `loushang.work`.

## Relation To Agent Harness And Products

`loushang.method` is optional for product execution.

Product packages such as `loushang.coding`, and future `loushang.research`,
`loushang.ppt`, and `loushang.cowork`, may call `loushang.agent.harness`
directly for lightweight turns. They may also write or project through
`loushang.work` directly.

Use `method` when the product needs structured work: planning, staged execution,
review gates, method-specific constraints, or acceptance criteria. Do not route
every product turn through method by default.

`cowork` is treated as a future product line, parallel to `coding`, `research`,
and `ppt`; it is not the name of the shared work or collaboration abstraction.

## Artifact Boundary

Method defines expected artifacts: what a structured workflow or method step
should produce.

`loushang.work` records actual artifact references: what was produced, where it
is, which run or step produced it, and how it relates to the expected artifact.

Product packages such as `coding`, `research`, `ppt`, and `cowork` own concrete
artifact types, content, loading, rendering, validation, and materialization.

Therefore the shared work layer should prefer a lightweight `ArtifactRef` over a
shared abstract `Artifact` base class.

## Field Mapping

The work-contract definition maps to current method data objects as follows:

| Contract axis | Current representation |
| --- | --- |
| workflow | `MethodPlan.mode`, `MethodPlan.steps`, `MethodStep.constraint`, `MethodStep.audit` |
| what | `MethodDescriptor.name`, `description`, `content`, `element_type`, `domain`, `applicability` |
| role | `MethodDescriptor.meta_role`, `MethodStep.role_variant`, `MethodProjection.meta_role` |
| task | `MethodDescriptor.element_type="task"`, `MethodApplicability.task_types`, `MethodContext.task`, `MethodPlan.task` |
| phase | `MethodDescriptor.phase`, `MethodPlan.phase`, `MethodApplicability.lifecycle` |
| constraints | `MethodStep.constraint`, projected policy metadata |
| gates | `MethodProjection.approval_gates`, currently mostly reserved |
| skills | `MethodProjection.allowed_skills`, currently reserved for future step-local skill binding |
| tools | `MethodProjection.suggested_tools`, currently reserved |
| artifacts | `MethodProjection.expected_artifacts`, currently reserved |

## Method, Skill, Tool, Policy, Work

Method should orchestrate a class of work. It defines the role, phase, workflow, constraints, artifacts, and acceptance expectations.

Skill should provide local expertise or capability guidance. A skill can be adapted into a `skill_backed` method for compatibility, but method resources should own workflow semantics when both exist.

Tool should execute concrete actions. Tools are not methods; a method can suggest or constrain tool usage, but tool execution remains governed by tool runtime and policy.

Policy should define permission, approval, and safety boundaries. Method metadata can carry policy hints, but enforcement belongs to the domain/runtime layer that executes the turn.

Work should record runtime execution. Method plans and steps become observable through work events, work logs, and inspection surfaces.

## Meta-Phase And Meta-Role

Current runtime support is intentionally light:

- `phase` is a string hint carried from descriptor to plan/projection.
- `meta_role` is a string hint carried from descriptor to step projection.
- `role_variant` is available at step level.
- `MethodApplicability.lifecycle` provides an additional lifecycle axis.

These fields are not yet closed enums. The experimental methodology documents remain design inputs for richer phase and role taxonomies:

- [Meta-Phase](../../experimental/methodology/meta-phase.md)
- [5+1 Meta Roles](../../experimental/methodology/meta-roles-5plus1.md)

## Evolution Rules

- Keep method resources domain-neutral where possible.
- Keep coding-specific policy and session behavior in `loushang.coding`.
- Prefer explicit method selection before automatic method routing.
- Store and project method metadata before enforcing it.
- Treat `MethodApplicability` shape as stable, but do not freeze the final ontology too early.
- Bind skills step-locally in the future instead of globally injecting all method-related skills.

## Related Documents

- [Architecture Overview](../architecture-overview.md)
- [Coding Domain Component](../coding/component-interfaces/domain.md)
- [Method Compatibility Note](../coding/component-interfaces/method.md)
- [Method P1 Resource Compatibility Design](../../specs/2026-06-02-method-p1-resource-compatibility-design.md)
- [Fixed MethodPlan P3 Design](../../specs/2026-06-03-fixed-methodplan-p3-design.md)
