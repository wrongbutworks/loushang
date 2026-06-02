# Loushang Method P1 Resource Compatibility Design

## Goal

在 Work P0 已经合并的基础上，引入最小可运行的 `loushang.method` 资源层。

P1 的目标不是实现完整方法论执行引擎，而是先让 Loushang 可以把现有 skill 生态看作一种 method 资源，并为后续 `methods/**/METHOD.md`、DomainApp、TaskFlow、多 agent 协作留下稳定边界。

成功标准：

- 现有 `skills/**/SKILL.md` 不迁移也能投影为 skill-backed method。
- `MethodDescriptor`、`MethodLoader`、`MethodRegistry`、`MethodCompiler`、`MethodProjection` 有稳定 P1 公共 API。
- method 可以编译成 single-turn `MethodPlan`。
- method projection 可以生成 prompt guidance，但默认不改变现有 CLI / AgentSession 行为。
- P1 public API 不暴露 TaskFlow、AgentLane、CollaborationBus、多步骤 workflow 等 P3/P4 概念。

## Scope

### In Scope

- 新增独立包 `loushang.method`。
- 定义 P1 `MethodDescriptor` schema。
- 定义 `MethodLoader`，内部可以复用现有 coding resource discovery。
- 定义 `MethodRegistry`，支持 list/get/select 的内存状态。
- 定义 `SkillDescriptor -> MethodDescriptor(kind="skill_backed")` 适配规则。
- 定义 single-turn `MethodPlan` 和 `MethodStep`。
- 定义 `MethodCompiler`，P1 永远输出 single-turn plan。
- 定义 `MethodProjector` / `MethodProjection`，把 plan 投影成 prompt guidance。
- 增加 focused tests 和 public API tests。

### Out Of Scope

- 自动 method selection。
- `--method` CLI 参数。
- session 持久化 selected method。
- 多步骤 TaskFlow。
- `CodingDomainApp` 实现。
- 多 agent 协作。
- method marketplace / package lifecycle。
- 迁移 `AgentSession` 内部职责。

## Why This Comes Next

Work P0 已经提供：

- `WorkOperation`
- `WorkRun`
- `WorkEvent`
- `EventLogBackend`
- `CodingWorkShell`
- JSONL work log
- work log inspect CLI

这让系统有了外部可观察的 work 生命周期。但目前 work 还不知道“该按什么方法执行”。如果直接进入 DomainApp 或多 agent，很容易把流程、领域、方法、队列混在一起。

因此 P1 应先补上 method 资源兼容层，让 method 从 hardcoded prompt / skill usage 中独立出来。

相关架构文档：

- `docs/architecture/drafts/loushang-work-method-channel-harness-architecture.md`
- `docs/architecture/drafts/loushang-runtime-architecture.md`
- `docs/architecture/coding/core-data-objects/resource-descriptors.md`
- `docs/architecture/coding/component-interfaces/method.md`

## Approaches Considered

### Approach 1: Put Method Under `loushang.coding.method`

把 method 作为 coding 子模块实现。

Pros:

- 实现最快。
- 可以直接依赖 `DefaultResourceLoader` 和 `SkillDescriptor`。

Cons:

- method 未来会跨 coding、research、cowork 等 domain。
- 后续从 coding 迁出会产生迁移成本。
- 容易让 method selection 和 coding prompt assembly 耦合。

Rejected.

### Approach 2: Independent `loushang.method`, Reusing Coding Resource Loader Internally

新增独立包 `loushang.method`，P1 内部可以适配 `SkillDescriptor` 和 `DefaultResourceLoader`，但 method 公共 API 不放在 `loushang.coding` 下。

Pros:

- method 边界从第一天就是跨 domain 的。
- P1 仍能复用现有 skill 生态，落地成本低。
- 不要求修改 `ResourceBundle` 公共结构。
- 可以渐进接入 work / domain app。

Cons:

- `loushang.method` P1 会临时依赖 coding loader 类型做兼容适配。
- 需要明确该依赖是 compatibility bridge，不是长期 domain ownership。

Recommended.

### Approach 3: Extend `ResourceBundle` With `methods`

直接给现有 resource loader 和 `ResourceBundle` 增加 `methods` 字段。

Pros:

- 资源发现入口统一。
- 后续 extension / package 可能更容易看到 methods。

Cons:

- 太早扩大 loader 公共结构。
- 会牵扯 extension discover hooks、package projection、session refresh、resource diagnostics。
- P1 的核心其实是 method schema 和 skill compatibility，不是统一资源发现系统重构。

Rejected for P1. This can be revisited after P1 API stabilizes.

## Recommended Architecture

P1 新增：

```text
src/loushang/method/
  __init__.py
  types.py
  skill_adapter.py
  loader.py
  registry.py
  compiler.py
  projection.py
```

### `types.py`

Owns:

- `MethodDescriptor`
- `MethodContext`
- `MethodPlan`
- `MethodStep`
- `MethodProjection`

This file should stay data-only. It must not import coding session, work shell, CLI, or resource loader implementation.

### `skill_adapter.py`

Owns:

- `method_from_skill(skill: SkillDescriptor) -> MethodDescriptor`
- skill-backed method id normalization
- skill metadata preservation

This is the only P1 module that should know the details of `SkillDescriptor`.

### `loader.py`

Owns:

- `MethodLoader`
- discovery from current resource loader
- future placeholder for `methods/**/METHOD.md`

P1 `MethodLoader` should be method-facing even if it delegates to `DefaultResourceLoader`.

### `registry.py`

Owns:

- `MethodRegistry`
- list/get/select semantics
- selected method state in memory

P1 registry does not persist selected method to session files.

### `compiler.py`

Owns:

- `MethodCompiler`
- `compile(descriptor, context) -> MethodPlan`

P1 compiler always creates one step:

```text
MethodPlan(mode="single_turn")
  MethodStep(id="main", executor="current_agent")
```

### `projection.py`

Owns:

- `MethodProjector`
- `project(plan, step, context) -> MethodProjection`

P1 projection turns method content into stable guidance. It does not mutate `AgentSession`, `WorkRun`, or prompt state directly.

## Data Model

### `MethodDescriptor`

```python
@dataclass(frozen=True)
class MethodDescriptor:
    id: str
    name: str
    description: str
    kind: Literal["skill_backed", "method_resource"]
    content: str
    domain: str | None = None
    source_path: str | None = None
    version: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
```

Required fields:

- `id`
- `name`
- `description`
- `kind`
- `content`

Compatibility rules:

- Unknown `metadata` keys must be preserved.
- P3 additions such as `steps`, `roles`, `gates`, and `artifacts` must be additive.
- P1 must not require existing `SKILL.md` files to change.

### Skill-Backed Method Mapping

```text
SkillDescriptor -> MethodDescriptor

id          = "skill:<skill.name>"
name        = skill.name
description = skill.description or ""
kind        = "skill_backed"
content     = skill.content
source_path = skill.source_path
metadata    = skill source, frontmatter, activation, and compatibility hints where available
```

If a skill name already starts with `skill:`, the adapter should avoid double-prefixing.

### `MethodContext`

P1 context should be small:

```python
@dataclass(frozen=True)
class MethodContext:
    domain: str | None = None
    task: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
```

It is context for compiling/projecting a method, not a run state object.

### `MethodPlan`

```python
@dataclass(frozen=True)
class MethodPlan:
    id: str
    method_id: str
    mode: Literal["single_turn"]
    steps: tuple[MethodStep, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)
```

### `MethodStep`

```python
@dataclass(frozen=True)
class MethodStep:
    id: str
    title: str
    executor: Literal["current_agent"]
    projection: Mapping[str, object] = field(default_factory=dict)
```

P1 step is descriptive. It is not a TaskFlow step and does not own lifecycle events.

### `MethodProjection`

```python
@dataclass(frozen=True)
class MethodProjection:
    method_id: str
    step_id: str
    system_guidance: str
    user_guidance: str | None = None
    allowed_skills: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    expected_artifacts: tuple[str, ...] = ()
    approval_gates: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
```

P1 `system_guidance` can be deterministic:

```text
Use the following method guidance when performing this turn:

<method content>
```

## Relationship To Existing Components

### Skill Loader

P1 uses existing skills as source material, but it does not move skill discovery into method.

`MethodLoader` can accept:

```python
resource_loader: DefaultResourceLoader | None
package_roots: tuple[str, ...]
```

and expose:

```python
discover_methods(cwd: str | Path) -> list[MethodDescriptor]
reload_methods(cwd: str | Path | None = None) -> list[MethodDescriptor]
list_methods() -> list[MethodDescriptor]
get_method(id_or_name: str) -> MethodDescriptor | None
```

### Work

P1 does not need to modify `CodingWorkShell` immediately.

The clean integration path is:

1. P1 implements pure method APIs.
2. A later small PR may allow work operations to carry `method_id`.
3. DomainApp P2 will decide how to assemble projection into a domain prompt/tool/policy bundle.

If P1 needs a smoke integration, it should be explicit and optional:

```text
compile method -> project guidance -> caller prepends guidance to prompt
```

The method package should not call `CodingWorkShell` directly.

### AgentSession

P1 does not mutate `AgentSession`.

No selected method is persisted to session files. No prompt assembler default changes are allowed in P1.

### CLI

P1 should not add `--method`.

CLI support can be a P1.5 or P2 follow-up after method APIs stabilize.

## Error Handling

P1 should keep errors simple and stable:

- invalid descriptor id -> `ValueError`
- duplicate method id in registry -> `ValueError`
- missing selected method -> return `None`, not exception
- loader discovery diagnostics should be preserved from resource loader where possible

Avoid a large custom exception hierarchy in P1.

## Testing Strategy

### Unit Tests

Add:

```text
tests/method/test_method_types.py
tests/method/test_skill_adapter.py
tests/method/test_method_loader.py
tests/method/test_method_registry.py
tests/method/test_method_compiler.py
tests/method/test_method_projection.py
tests/method/test_public_api.py
```

Coverage:

- dataclass defaults
- metadata is JSON-friendly and preserved
- skill-backed id generation
- loader discovers methods from skills
- registry list/get/select
- compiler returns single-turn plan
- projector returns stable guidance
- public API excludes P3/P4 concepts

### Regression Tests

Keep existing suites passing:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/method tests/coding/test_skill_loader.py tests/coding/test_cli.py tests/work -q
uv --cache-dir .uv-cache run ruff check src/loushang/method tests/method
```

## Rollout Plan

### Task 1: Core Method Types

Create `loushang.method.types` and public exports.

### Task 2: Skill Adapter

Implement `SkillDescriptor -> MethodDescriptor`.

### Task 3: Method Loader

Wrap existing resource loader skill discovery into method discovery.

### Task 4: Method Registry

Add list/get/select behavior with duplicate id protection.

### Task 5: Compiler And Projection

Compile to single-turn plan and project stable guidance.

### Task 6: Public API And Regression

Add public API boundary tests and run focused regression.

## Open Questions

These are explicitly deferred unless implementation reveals a blocker:

- Should `METHOD.md` use frontmatter identical to `SKILL.md`, or a separate schema?
- Should selected method live in settings, session metadata, or work operation payload?
- Should CLI expose `--method` before DomainApp exists?
- Should method projection append to system prompt or user prompt by default?

P1 can ship without answering these globally.

## Tracking

GitHub issue:

- `#36 P1: method resource compatibility`
