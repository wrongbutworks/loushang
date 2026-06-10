# Agent Harness Module Ownership Inventory

## Status

Planning inventory for P1 of
[ARD-001: Agent Harness and Product Adapter Boundaries](ARD-001-agent-harness-and-product-adapters.md).

This document records current module ownership before adding
`loushang.agent.harness`. It is intentionally an inventory, not an implementation
plan.

## Scope

Covered packages:

- `loushang.agent`
- `loushang.coding`
- `loushang.work`
- `loushang.method`

Out of scope:

- moving files
- adding harness code
- introducing `channel`
- creating `research`, `ppt`, or `cowork` packages
- changing public exports

## Ownership Categories

| Category | Meaning |
| --- | --- |
| Keep | Current package is the right owner. |
| Harness input | Existing object should be consumed by `agent.harness` without moving it. |
| Harness candidate | Future harness code should live here, usually as a thin facade. |
| Product adapter | Product-specific assembly; keep out of `agent` and `work` primitives. |
| Work primitive | Cross-product work event/log/projection ownership. |
| Method primitive | Cross-product structured-work ownership. |
| Transitional coupling | Current dependency or location is accepted for now, but should not expand. |
| Do not move | Explicitly excluded from `agent.harness` migration. |

## Current Dependency Observations

Current code already satisfies the most important low-level rule:

```text
loushang.agent does not import loushang.coding, loushang.work, or loushang.method.
```

Current expected product dependencies:

```text
loushang.coding -> loushang.agent
loushang.coding -> loushang.work
loushang.coding -> loushang.method
```

Current transitional compatibility exports:

```text
loushang.work.CodingWorkShell remains as a compatibility export for the coding-owned implementation.
```

These couplings do not block P2 harness work because `agent.harness` must not
depend on `method`, `work`, or `coding`. They should be isolated in later
resource-loader / product-adapter cleanup.

## `loushang.agent`

| Module | Current responsibility | Ownership | P2 action |
| --- | --- | --- | --- |
| `agent/types.py` | Agent messages, tool protocols, loop config, event types, state types | Keep / Harness input | Reuse types from harness. Do not move. |
| `agent/agent_loop.py` | Low-level run loop, event emission, model stream and tool execution orchestration | Keep / Harness input | `run_agent()` should call existing loop functions. Do not duplicate the loop. |
| `agent/agent.py` | Stateful `Agent` facade, queues, active run lifecycle, subscriptions | Keep / Harness host | Keep lifecycle here; delegate prompt and continuation loop execution through `agent.harness`. |
| `agent/proxy.py` | Proxy stream adapter | Keep | No P2 change. |
| `agent/__init__.py` | Stable public exports | Keep | Do not re-export harness API in P2. |
| `agent/harness/*` | Headless run scaffolding for product adapters | Harness candidate | Add in P2 as a thin facade only. |

P2 allowed additions:

```text
src/loushang/agent/harness/__init__.py
src/loushang/agent/harness/types.py
src/loushang/agent/harness/runner.py
```

P2 harness must not import:

```text
loushang.coding
loushang.work
loushang.method
loushang.tui
```

## `loushang.coding`

`loushang.coding` remains the coding product adapter. Most modules are explicitly
not harness candidates.

| Component | Current responsibility | Ownership | P2 action |
| --- | --- | --- | --- |
| `bootstrap` | Default product assembly | Product adapter | Do not move. Later may call harness. |
| `cli` / `sdk_surface` / `mode` | Product entry points and I/O modes | Product adapter | Do not move. |
| `runtime` | Current coding session lifecycle host | Product adapter | Do not move in P2. Later may use harness internally. |
| `session` | Single coding session facade and controllers | Product adapter | Do not move. |
| `store` | Coding transcript/session persistence | Product adapter | Do not move. |
| `message` | Coding session entries, custom messages, JSONL transforms | Product adapter | Do not move. Agent message primitives already live in `agent`. |
| `event` | Coding session event protocol and projection | Product adapter | Do not move. Work projection lives in `work`. |
| `tools` | Coding tool registry and concrete tools | Product adapter | Do not move. Only generic `AgentTool` protocol belongs in `agent`. |
| `exec` | Local command execution service | Product adapter | Do not move. |
| `policy` | Coding tool permission and approval policy | Product adapter | Do not move. |
| `prompt` | Coding prompt assembly, preflight, templates | Product adapter | Do not move. |
| `loader` / `resources` / `skill` | Coding resource discovery and injection | Product adapter | Do not move. May later split shared resource loader if method needs it. |
| `package` / `plugin` | Coding package/plugin lifecycle and materialization | Product adapter | Do not move. |
| `extensions` | Coding extension API, runner, policy, contributions | Product adapter | Do not move to agent in P2. |
| `domain` | Method-to-coding prepared turn bridge | Product adapter | Keep as product bridge. |
| `control` | Settings, model controls, auth integration | Product adapter | Do not move. |
| `compaction` | Coding transcript compaction and summaries | Product adapter | Do not move. |
| `diagnostics` / `observability` | Coding diagnostics surface | Product adapter | Do not move. |
| `platform` | Clipboard, git, version, terminal/platform helpers | Product adapter | Do not move. |
| `workflow` | Prompt workflow loader/runner | Product adapter | Do not move. |
| `ui` | Coding TUI adapter and playback scenarios | Product adapter | Do not move to `agent` or `tui`. |

Explicit non-goals for P2:

- no migration of read / ls / find / grep / bash / edit / write tools
- no migration of slash commands
- no migration of AGENTS.md or coding prompt assembly
- no migration of extension policy or UI/autocomplete integration
- no migration of coding session JSONL schema

## `loushang.work`

`loushang.work` owns cross-product work facts and projections. It should stay
independent from product packages.

| Module | Current responsibility | Ownership | Follow-up |
| --- | --- | --- | --- |
| `work/types.py` | `WorkOperation`, `WorkRun`, `WorkEvent`, plan/step run data, `ArtifactRef` | Work primitive | Keep artifact references generic; product packages own concrete artifact content. |
| `work/event_log.py` | Event log protocol, in-memory backend, JSONL backend | Work primitive | Keep. |
| `work/projection.py` | Generic mapping from agent-like events to `WorkEvent` | Work primitive | Keep. It accepts mappings and does not need product imports. |
| `work/plan_projection.py` | Plan/step run projection from work log entries | Work primitive | Keep. |
| `work/coding.py` | Compatibility re-export for `CodingWorkShell` | Transitional compatibility | Do not expand. Implementation lives in `loushang.coding.work_shell`. |
| `work/__init__.py` | Work exports | Work primitive plus lazy compatibility exports | Avoid eager product imports. |

`CodingWorkShell` is useful but product-specific. Its implementation and coding
runtime entrypoint live in `loushang.coding.work_shell`. The `loushang.work`
export is retained as a lazy compatibility bridge, not a pattern for future
`ResearchWorkShell`, `PptWorkShell`, or `CoworkWorkShell` modules inside
`loushang.work`.

## `loushang.method`

`loushang.method` owns structured work contracts. It is optional for product
execution and must not become a mandatory harness dependency.

| Module | Current responsibility | Ownership | Follow-up |
| --- | --- | --- | --- |
| `method/types.py` | `MethodDescriptor`, `MethodPlan`, `MethodStep`, `MethodProjection` | Method primitive | Keep. |
| `method/compiler.py` | Compile method descriptors into plans | Method primitive | Keep. |
| `method/projection.py` | Project method steps into guidance/facts | Method primitive | Keep. |
| `method/registry.py` / `selector.py` | Method registry and explicit selection | Method primitive | Keep. |
| `method/applicability.py` | Applicability metadata parsing | Method primitive | Keep. |
| `method/resources.py` | Product-neutral skill-like resource protocol and minimal skill discovery for method loading | Method primitive | Keep scoped to method needs. Do not absorb coding prompt/theme/extension loading. |
| `method/loader.py` | Discover method resources and skill-backed methods | Method primitive | Keep independent from coding loader. |
| `method/skill_adapter.py` | Adapt skill-like descriptors into method descriptors | Method primitive | Accept protocol-shaped resources; do not depend on coding descriptor classes. |

Known method cleanup candidates:

- completed: move reusable frontmatter parsing to `loushang.resource`
- completed: introduce method-owned skill-like resource protocols so method
  discovery does not depend on `coding.loader`
- keep method expected artifacts as method metadata; do not record actual
  artifact refs in `method`

## P2 Harness Inputs

The P2 harness can be built from existing agent primitives:

| Needed by harness | Existing source |
| --- | --- |
| system prompt, messages, tools | `AgentContext` |
| model, stream options, callbacks | `AgentLoopConfig` |
| prompt messages | `list[AgentMessage]` |
| event collection | `AgentEvent` sink |
| result transcript | `run_agent_loop(...)` return value |
| continuation mode | `run_agent_loop_continue(...)` |
| cancellation | existing `signal` argument / abort signal shape |
| custom stream function | existing `StreamFn` |

The P2 `AgentRunSpec` should mostly package these existing inputs. It should not
invent product concepts such as session ids, work run ids, command names, or UI
surfaces.

The P2 `AgentRunResult` should return agent-level facts only:

- status / stop reason
- new messages
- collected agent events
- error, if any
- usage if already available from emitted agent events

Work projection remains a product or work-layer concern:

```text
AgentRunResult -> product adapter -> WorkEvent
```

## Do Not Move List

These names are intentionally excluded from `loushang.agent.harness`:

- `AgentSession`
- `AgentSessionRuntime`
- `SessionManager`
- `CommandController`
- `ToolController`
- `ExtensionRunner`
- `ExtensionAPI`
- `ExtensionContext`
- `CodingDomainApp`
- `CodingWorkShell`
- coding concrete tools
- coding slash command registry
- coding prompt assembly
- coding package/plugin materialization
- TUI playback and UI controllers

## Current Follow-up Sequence

1. Completed: add thin `loushang.agent.harness` facade and tests.
2. Completed: add `loushang.work.ArtifactRef`.
3. Completed: move coding runtime imports to the `loushang.coding.work_shell` adapter.
4. Completed: route `Agent` prompt and continuation execution through `agent.harness` while preserving the stateful lifecycle.
5. Completed: isolate method resource loading from `loushang.coding.loader`.
6. Completed: move `CodingWorkShell` implementation ownership to `loushang.coding.work_shell`.
