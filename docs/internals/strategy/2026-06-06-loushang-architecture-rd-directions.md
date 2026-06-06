# Loushang Architecture And R&D Directions

## Scope

This memo records a high-level architecture assessment and R&D direction
prioritization for `loushang` as of 2026-06-06.

It is intended as an internal strategy input for later specs, plans, and roadmap
decisions. It is not an implementation plan and does not define new public API
contracts.

## Current Architecture Snapshot

`loushang` is currently a coding-first complex work runtime. The public product
focus is `loushang code`, backed by `loushang.ai` as the model/provider access
layer.

The current primary runtime chain is:

```text
CLI / TUI
  -> loushang.coding bootstrap / runtime / session
  -> loushang.agent loop
  -> loushang.ai provider adapters
  -> tools / events / store / modes / diagnostics
```

The top-level architecture principle remains:

```text
kernel + protocol + adapters + extension points
```

In practice:

- `loushang.ai` absorbs provider, model, streaming, auth, usage, and tool-call
  compatibility variation.
- `loushang.agent` owns the generic agent loop, message/event semantics, tool
  orchestration, queues, abort, steering, and follow-up behavior.
- `loushang.coding` is the coding product assembly layer. It owns session,
  store, tools, settings, policy, diagnostics, resources, extensions, modes,
  commands, compaction, and TUI adaptation.
- `loushang.tui` is the terminal-native UI framework and should remain generic.
- `loushang.method` and `loushang.work` have useful skeletons, but are not yet
  the primary product control plane.
- `loushang.channel` is architecturally important but not yet implemented as a
  package-level subsystem.

## Current Strengths

### Coding Headless Runtime

The non-UI `loushang.coding` runtime is already close to a usable integration
surface. Session persistence, restore/fork/import, tool execution, policy,
diagnostics, resource loading, extensions, package management, print/RPC modes,
compaction, and export are all represented in code and tests.

This makes `loushang code` the right V1 product focus.

### Stable Center Objects

The architecture has correctly concentrated early work around high-fanout
objects:

- `AgentSession`
- `AgentSessionRuntime`
- `SessionManager`
- `SettingsManager`
- `ModelRegistry`
- `DefaultResourceLoader`
- `ToolRegistry`
- `DiagnosticsService`

These are the right objects to stabilize before expanding product surfaces.

### AI Layer Direction

`loushang.ai` has a clear model/provider/event-stream/auth shape. It already
supports the main invocation families and provides a foundation for future model
gateway, usage, and cost governance.

### Native TUI Direction

The native terminal core direction is strategically sound. It prioritizes
deterministic visual stability, a runtime-owned bottom frame, a single terminal
writer, line-level differential rendering, resize repaint policy, transcript
records, surfaces, and playback regression testing.

For a coding agent product, TUI correctness and perceived stability are
product-critical.

## Main Risks

### Coding Entry Surface May Become Too Heavy

The `loushang` command currently routes directly to the coding CLI. This is
reasonable for V1, but if left unchanged it can make future `work`, `research`,
and `ppt` surfaces harder to introduce cleanly.

The risk is that intake, run routing, channel behavior, and non-coding domain
semantics continue to accumulate inside `loushang.coding`.

### `AgentSession` Remains A High-Fanout Hub

`AgentSession` has been split into focused controllers, but it remains the
central facade for session state, commands, tools, extensions, resources,
diagnostics, auth, compaction, selection, queueing, package lifecycle, and
runtime events.

This is acceptable for V1, but future growth should be controlled through
contract tests, stable facade boundaries, and work/channel separation rather
than by adding more direct responsibilities.

### Method Runtime Is Still Thin

`MethodDescriptor`, `MethodPlan`, `MethodStep`, and `MethodProjection` exist, and
`CodingDomainApp` can turn explicit methods into prepared prompts. However, this
is still closer to method-guided prompt preparation than a full method-bound work
runtime.

The missing higher-value loop is:

```text
method -> plan -> step run -> artifacts -> acceptance -> deviation -> handoff
```

### Work And Channel Layers Are Not Yet Product Control Planes

`loushang.work` includes useful event/run types and projection helpers, but it
does not yet own the main operation/run lifecycle. `loushang.channel` is still a
target architecture concept rather than a package implementation.

This limits future daemon, remote, web, messaging, shared run, and team
scenarios.

### AI Provider Boundary Debt

The AI package still has open design debt around:

- consumer-specific behavior leaking into core auth/provider layers
- normalized context as the single source of truth
- default repair semantics for tool/message pairing
- public API surface width
- typed provider option boundaries
- usage observation vs platform quota semantics
- endpoint/model catalog responsibility boundaries

These are not blockers for V1, but they are high-leverage cleanup areas before
gateway and team-level governance.

## High-Value R&D Directions

### 1. V1 Code Hardening

Priority: highest.

Focus on turning `loushang code` into a trustworthy product surface.

Recommended work:

- Cross-component golden flows:
  - CLI/RPC/SDK -> tool -> policy -> diagnostics -> session store
  - extension exec -> resource refresh -> diagnostics
  - compaction fixture -> summary evaluation -> continuation
- Stress and race tests:
  - session restore/import filesystem races
  - runtime replacement callback failures
  - extension reload/shutdown interleavings
  - bash abort and interleaved output under load
  - session index refresh coalescing
- Contract locks:
  - SDK surface baseline
  - settings and tool policy contract
  - headless approval resolver contract
  - extension exec API contract
  - summary evaluation fixture contract

This direction has the best near-term value-to-risk ratio because most of the
runtime foundation already exists.

### 2. Native TUI Productization

Priority: highest.

Continue making the terminal experience stable and complete.

Recommended work:

- transcript reader and copy semantics
- terminal playback coverage for resize, cursor, viewport, pending queues, and
  overlay/surface interactions
- abort / steer / follow-up flows
- model and command palettes
- approval presentation
- performance probes for large transcript and streaming cases
- stable rendering of tool blocks, thinking blocks, markdown, images, and
  diagnostics

This is the highest-impact user-facing direction for V1.

### 3. Method Runtime Beyond Prompt Injection

Priority: high.

Upgrade method support from prompt preparation to method-bound execution.

Recommended work:

- Represent method plan runs and step runs as first-class runtime facts.
- Attach method/step metadata to session entries and work events.
- Track expected artifacts, success criteria, acceptance results, and
  deviations.
- Preserve explicit method selection first; postpone automatic method selection
  until the run model is stable.
- Keep method assets separate from runtime facts.

This is the core differentiator between Loushang and a generic coding agent.

### 4. Minimal Work And Channel Spine

Priority: high.

Introduce a narrow `work/channel` spine without blocking V1.

Recommended minimal chain:

```text
ChannelInbound
  -> WorkOperation
  -> WorkRun
  -> WorkEvent
  -> ChannelOutbound
```

The first useful version should support:

- local CLI/TUI as channels
- event log append/query/subscribe
- delivery hints for streaming/coalesced/final-only output
- domain invocation through `loushang.coding`
- stable event projection for future web/RPC/daemon consumers

This prevents `coding` from becoming the permanent top-level platform.

### 5. AI Usage, Gateway, And Provider Governance

Priority: medium-high.

Standardize the AI layer before building gateway/team features on top of it.

Recommended work:

- Split response usage observations from account/platform quota.
- Define stable usage and cost payloads.
- Clean provider-specific auth and compatibility helpers out of generic core
  paths.
- Narrow public exports to primary entry points.
- Strengthen provider option and normalized context typing.
- Decide which facts belong in `models.json`, provider adapters, endpoint
  metadata, or runtime settings.

This direction supports model routing, budgets, audit, and future gateway
infrastructure.

### 6. Extension, Plugin, And Package Ecosystem Hardening

Priority: medium-high.

The substrate already exists. The next value comes from reliability and
developer confidence.

Recommended work:

- API versioning and compatibility checks.
- Trust/signature/security policy for package/plugin sources.
- Better extension diagnostics and lifecycle visibility.
- First-party templates for tools, commands, resources, and themes.
- Stable package manifest and source lifecycle semantics.

This direction supports method marketplace and team-level extension governance.

### 7. Observability, Replay, Export, And Evidence Chain

Priority: medium.

Strengthen the ability to inspect, replay, diagnose, and deliver work.

Recommended work:

- Align session JSONL, `WorkEvent`, diagnostics, HTML export, and playback traces.
- Preserve enough source references for audit and reproduction.
- Improve diagnostic grouping and presentation.
- Add export formats that support review, handoff, and delivery.

This direction directly supports the product promise of recoverable, auditable,
verifiable complex work.

### 8. Ontology And World Model As Later Method Assets

Priority: medium-low for now.

The ontology package is directionally relevant, but should not become the main
short-term product track.

Recommended posture:

- Keep it as a future method/world-model asset substrate.
- Use it first for artifacts, acceptance evidence, method assets, and domain
  object relationships.
- Avoid building a standalone general-purpose knowledge graph before
  method-bound runs and work events are stable.

## Recommended Sequencing

### Near Term

Focus on:

```text
V1 code hardening + Native TUI productization
```

This makes the existing coding-first product reliable and usable.

### Mid Term

Focus on:

```text
Method runtime + WorkEvent / WorkRun integration
```

This turns Loushang's methodology vision into runtime facts instead of prompt
guidance only.

### Later

Focus on:

```text
Channel + daemon + gateway + team + managed runtime
```

These directions should build on stable work/run/method/event contracts rather
than bypassing them.

## Source Evidence

Key files and documents used for this assessment:

- `README.zh-CN.md`
- `pyproject.toml`
- `docs/internals/architecture/architecture-overview.md`
- `docs/internals/architecture/subsystem.md`
- `docs/internals/strategy/strategy.md`
- `docs/internals/strategy/loushang-product-surfaces-and-roadmap.md`
- `docs/internals/architecture/coding/loushang-coding-system-context.md`
- `docs/internals/architecture/coding/reports/2026-05-11-component-completion-status.md`
- `docs/internals/architecture/ai/validation/loushang-ai-implementation-status-round-1.md`
- `docs/internals/architecture/tui/native-terminal-core/README.md`
- `src/loushang/coding/cli/__main__.py`
- `src/loushang/coding/bootstrap.py`
- `src/loushang/coding/session/agent_session.py`
- `src/loushang/coding/runtime/agent_session_runtime.py`
- `src/loushang/agent/agent.py`
- `src/loushang/agent/agent_loop.py`
- `src/loushang/ai/TODO.md`
- `src/loushang/method/types.py`
- `src/loushang/work/types.py`
