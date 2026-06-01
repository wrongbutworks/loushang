# Loushang Work / Method / Channel / Harness Architecture Draft

## Status

Draft.

This document records the target architecture direction for turning `loushang`
from a coding-first CLI/TUI product into a method-guided, multi-domain work
operating layer.

This draft supersedes the older "runtime kernel" wording in this file. The
preferred package-level naming is now:

- `loushang.channel`
- `loushang.work`
- `loushang.method`
- `loushang.agent.harness`
- `DomainApp`

Related draft:

- [Loushang Work / Method / Channel / Harness target architecture](./loushang-work-method-channel-harness-architecture.md)

This is an architecture draft, not a detailed implementation plan.

## Scope

This draft covers the shared architecture needed to support:

- native CLI/TUI, future GUI, HTTP, RPC, WebSocket, stdio, and stream surfaces
- WeChat, Feishu, mini app, and other product channels
- upper-level host architectures that embed or orchestrate `loushang`
- multiple domain apps such as coding, cowork, research, presentation, and
  evolution
- method-guided execution with skill-compatible method resources
- multi-agent, workflow, approval, artifact, and playback requirements
- external identity, session addressing, delivery, and reconnect requirements
- memory, context, extension, scheduler, and provider-routing requirements
- a first implementation version centered on the coding domain app

This draft does not specify:

- exact wire schema versioning
- concrete TUI widget implementation
- full GUI behavior
- a complete autonomous team platform
- a complex method DSL
- replacement of the current `AgentSession` in the first slice

## Core Direction

`loushang` should not be modeled as an enhanced TUI, a coding-only session
engine, or a generic `runtime` package. The target architecture should model
`loushang` as a **method-guided work operating layer**.

The target mental model is:

```text
Hosts / Products / SDK
  CLI / TUI / GUI / HTTP / WebSocket / stdio
  WeChat / Feishu / mini app
  Hermes / OpenClaw / Manus / upper-level orchestrators

        |
        v

loushang.channel
  channel adapters
  inbound normalization
  outbound delivery
  channel capability
  delivery policy projection
  reconnect / reply / edit / final-only

        |
        v

loushang.work
  WorkOperation
  WorkRun
  WorkEvent
  WorkSession
  TaskFlow
  AgentLane
  ArtifactRef
  ApprovalRequest
  MethodRun
  Scheduler
  EventLog

        |
        v

loushang.method
  MethodDescriptor
  MethodLoader
  MethodRegistry
  MethodSelector
  MethodCompiler
  MethodProjector
  skill-backed method compatibility

        |
        v

Domain Apps
  loushang.coding
  loushang.research
  loushang.cowork
  loushang.ppt
  loushang.evolution

        |
        v

loushang.agent.harness
  one prepared agent turn
  turn phase / turn snapshot
  steer / follow-up / next-turn queues
  save point / settled events
  hooks / session write ordering
  AgentEvent -> HarnessEvent

        |
        v

loushang.agent + loushang.ai
  low-level agent loop
  model/provider streaming
  tool call / tool result semantics
```

The TUI must not be the architectural center. It is one channel/host
composition over the same operation/event model that future GUI, remote
services, messaging channels, and upper-level host architectures use.

## Naming Boundary

### Why Not `loushang.runtime`

`runtime` is ambiguous. It can mean:

- Python or Node runtime
- model runtime
- agent loop runtime
- TUI runtime
- extension runtime
- workflow runtime

The target control plane should not be named `loushang.runtime` because it does
more specific work: it accepts work, creates runs, records events, coordinates
tasks, applies methods, tracks artifacts, and projects results back to
channels.

### Why Not `loushang.platform`

`platform` is too broad. It tends to become a dumping ground for shared code.
The architecture needs a name that is narrower than platform and more semantic
than runtime.

### Preferred Name: `loushang.work`

`work` expresses the actual domain:

- a piece of work is submitted
- it becomes a run, task, or step
- it may be guided by a method
- it is executed by a domain app
- it may require approvals
- it produces artifacts
- it can be replayed, resumed, inspected, or audited

The word `runtime` can still be used as a descriptive adjective where useful,
but it should not be the package name for this control plane.

## Layer Responsibilities

### Hosts / Products / SDK

A host embeds or orchestrates `loushang`.

Examples:

- native `loushang` CLI/TUI process
- HTTP daemon
- desktop or web app process
- OpenClaw, Hermes, Manus, or another upper-level architecture
- test playback runner
- scheduler process

A host creates or resumes sessions, submits operations, subscribes to events,
manages process lifetime, supplies external services, and may enforce
deployment-level policy.

The host is not the same thing as a channel. A desktop app may be both host and
channel, while an upper-level architecture may host `loushang` and expose its
own channels.

### `loushang.channel`

`channel` is the external entry and delivery boundary. It is not the business
control plane.

Responsibilities:

- receive external input
- normalize inbound events
- parse external identity and conversation source
- convert inbound input into `WorkOperation`
- declare channel capabilities
- render `WorkEvent` according to channel capability
- perform outbound delivery
- support reconnect, reply, edit, attachment, final-only, and streaming

Non-responsibilities:

- method selection
- multi-agent scheduling
- tool policy
- coding workflow
- work run lifecycle
- single-turn agent lifecycle

Core objects:

```text
ChannelAdapter
ChannelInbound
ChannelOutbound
ChannelCapability
DeliveryPolicy
DeliveryAddress
ExternalIdentity
ConversationAddress
WorkspaceAddress
SessionAddress
```

`ExternalIdentity`, `ConversationAddress`, `WorkspaceAddress`,
`SessionAddress`, and `DeliveryAddress` are shared value objects. They may be
created by channel adapters, recorded by `work`, and used by delivery logic,
but channel-specific SDK objects should not leak into `work`.

### `loushang.work`

`work` is the control plane. It knows how work is submitted, routed, scheduled,
recorded, cancelled, resumed, and delivered.

Responsibilities:

- receive `WorkOperation`
- create and manage `WorkRun`
- manage `WorkSession`
- relate run, session, task, artifact, channel, domain, and method metadata
- maintain `TaskFlow`
- manage `AgentLane`
- emit `WorkEvent`
- append to `EventLog`
- manage `ArtifactRef`
- handle `ApprovalRequest`
- call `method` for method selection and compilation
- call `DomainApp` to execute domain steps
- provide one control surface for scheduler, replay, SDK, and upper-level hosts

Non-responsibilities:

- channel-specific send/receive logic
- coding tool details
- low-level model provider behavior
- the internal state machine of one prepared agent turn

Core objects:

```text
WorkOperation
WorkRun
WorkEvent
WorkSession
TaskFlow
TaskRun
AgentLane
ArtifactRef
ApprovalRequest
MethodRun
EventLog
DomainAppRegistry
Scheduler
```

### `loushang.method`

`method` is the method asset and method compilation layer. It describes how
work should be done, but it does not execute tools or advance the agent loop by
itself.

Responsibilities:

- discover method resources
- parse method metadata
- keep compatibility with existing skills
- register methods
- select a method for a context
- compile a method into `MethodPlan`
- project the current method step into prompt, skill, tool, artifact, and gate
  guidance

Non-responsibilities:

- `WorkRun` state persistence
- multi-agent scheduling
- file edits or test execution
- channel delivery

Core objects:

```text
MethodDescriptor
MethodLoader
MethodRegistry
MethodSelector
MethodCompiler
MethodPlan
MethodProjector
MethodTrace
```

`MethodRun` belongs in `loushang.work` because it must be recorded together
with `WorkRun`, `TaskRun`, `ArtifactRef`, and `ApprovalRequest`.

### `DomainApp`

`DomainApp` is the domain capability provider. The first implementation should
ship with `loushang.coding`.

Responsibilities:

- declare a domain id
- declare supported operation kinds
- declare tools, policy, artifact types, prompts, and method packs
- map `MethodStep` into domain tasks
- call `agent.harness` or another executor

Non-responsibilities:

- channel protocol
- generic work run lifecycle
- generic method loader
- generic agent harness

The first coding domain app should provide:

```text
coding tools
coding policy
coding prompt resources
coding artifacts: patch / test_report / review_finding / summary
coding method packs: bugfix / review / tdd
```

### `loushang.agent.harness`

`agent.harness` is the executor for **one prepared agent turn**.

Responsibilities:

- turn phase
- turn snapshot
- steer / follow-up / next-turn queue
- save point
- settled event
- context / provider / tool hooks
- session write ordering
- projection from `AgentEvent` to `HarnessEvent`

Non-responsibilities:

- channel
- work run
- task flow
- method selection
- multi-agent team
- domain workflow

This boundary matches the general shape of Pi's AgentHarness and OpenClaw's
agent harness approach: harness is not a provider, not a channel, not a tool
registry, and not the upper workflow engine.

### `loushang.agent` And `loushang.ai`

`loushang.agent` and `loushang.ai` remain the lower-level model and agent-loop
layers.

They own:

- provider/model streaming semantics
- tool call and tool result semantics
- low-level agent event production
- model message construction and parsing
- provider routing primitives where already established

They should not own `WorkRun`, channel delivery, method selection, or
multi-agent coordination.

## Historical Term Mapping

The older English draft used broader runtime names. The aligned names are:

```text
Operation
  -> WorkOperation

RuntimeEvent / Event
  -> WorkEvent at the work boundary
  -> AgentEvent inside loushang.agent
  -> HarnessEvent inside loushang.agent.harness

RuntimeSession
  -> WorkSession

Runtime Kernel
  -> loushang.work

Host API / Channel API
  -> host integration surface + loushang.channel adapter boundary

WorkflowRun / AgentRun
  -> WorkRun + TaskFlow + AgentLane where applicable
```

The following value objects keep their names but move to clearer ownership:

```text
ExternalIdentity
ConversationAddress
WorkspaceAddress
SessionAddress
DeliveryAddress
ChannelCapability
DeliveryPolicy
SurfaceRequest
ArtifactRef
DomainApp
```

Address and delivery objects are produced or interpreted by `channel` and
recorded by `work`. `SurfaceRequest` and `ArtifactRef` are semantic work facts
that channels render according to capability.

## Operation / Event Model

### WorkOperation

`WorkOperation` is the unified intent object entering `loushang.work`.

Suggested operation kinds:

```text
SubmitTurn
SubmitSteer
SubmitFollowUp
InterruptRun
CancelRun
Approve
Reject
InvokeCommand
StartWorkflow
StartTeamRun
AttachArtifact
OpenSurface
ResumeSession
```

The first coding slice can implement a smaller subset:

```text
SubmitCodingTurn
StartCodingTask
StartCodingWorkflow
StartCodingTeamRun
InterruptRun
Approve
Reject
```

Operations are intent-bearing inputs, not UI callbacks.

### WorkEvent

`WorkEvent` is the output fact emitted by `loushang.work`. It may be projected
from `AgentEvent`, or produced directly by `work`, `method`, or a `DomainApp`.

Suggested first event family:

```text
OperationAccepted
WorkRunStarted
WorkRunCompleted
WorkRunFailed
TaskStarted
TaskCompleted
TaskFailed
MethodSelected
MethodPlanCreated
MethodStepStarted
MethodStepCompleted
ContentDelta
ToolCallStarted
ToolCallCompleted
ApprovalRequested
ApprovalResolved
ArtifactCreated
ArtifactUpdated
SurfaceRequested
OperationFailed
```

Existing `loushang.agent.AgentEvent` should not be discarded. The relationship
is:

```text
AgentEvent
  low-level turn_start / message_update / tool_execution_start / ...

HarnessEvent
  AgentEvent + harness-owned events

WorkEvent
  HarnessEvent + run/session/task/channel/domain/method metadata
```

Events should be append-friendly, replayable where possible, and consumable by
multiple observers.

## Separation Rules

### Host Is Not Channel

A host owns embedding and lifecycle. A channel owns interaction.

For example, a desktop app may be both a host and a channel, but an upper-level
architecture such as OpenClaw or Hermes may host `loushang` while exposing its
own channels. A TUI process is only one host/channel composition.

### Channel Is Not Domain App

A Feishu adapter should not know how `loushang.coding` builds prompts. A PPT
app should not know how a terminal draws a selector. Both communicate through
operations, events, surfaces, artifacts, and capabilities.

### Channel Is Not Work

`channel` adapts input and output. It does not own run state, task state,
method state, artifact lineage, or multi-agent scheduling.

### Domain App Is Not Work

Coding is the first domain app, but it should not define the shared control
plane. Concepts such as run, task, event, artifact, approval, method run, and
session addressing must remain domain-neutral.

### Harness Is Not Work

`agent.harness` runs one prepared agent turn. It does not decide whether a
request is a single turn, a method-guided run, a workflow, or a multi-agent team
run.

### Method Is Not Code Branching

Concrete methods should be resources, not hardcoded code branches. Runtime code
should provide loaders, registries, selectors, compilers, and projectors.

## Method Resource Model

Concrete methods must not be hardcoded.

The stable code surface should be:

```text
MethodLoader
MethodRegistry
MethodSelector
MethodCompiler
MethodProjector
```

Concrete methods come from resources:

```text
methods/**/METHOD.md
methods/**/SKILL.md
skills/**/SKILL.md
```

### Minimal Degradation Path

A method can degrade to a plain skill:

```markdown
---
name: bugfix
description: Debug and fix a failing behavior.
---

Read the failure carefully.
Reproduce before editing.
Make the smallest safe change.
Run verification before final response.
```

This file has no steps, roles, gates, or artifacts, but it still runs.

Compilation result:

```text
MethodPlan
  mode: single_turn
  steps:
    - id: main
      executor: current_agent
      projection: inject method content as guidance
```

This keeps the first version runnable even when the only available method is a
simple skill.

### Existing Skill Compatibility

Existing `skills/**/SKILL.md` files must remain compatible:

- no required format migration
- no required directory migration
- still available in `<available_skills>`
- still loadable through explicit skill invocation

Compatibility rule:

```text
SkillDescriptor
  -> MethodDescriptor(kind="skill_backed", id="skill:<name>")
```

Any existing skill can therefore act as a single-step method:

```text
/method skill:debugging
```

`MethodSelector` may also select a skill-backed method in high-confidence,
low-risk cases.

### Enhanced Method

A richer method may add metadata over time:

```yaml
---
id: software/bugfix
name: Bugfix
description: Reproduce, fix, and verify a bug.
domain: coding
execution_mode: fixed
applicability:
  when:
    - failing test
    - runtime error
roles:
  - investigator
  - implementer
  - verifier
steps:
  - id: reproduce
    role: investigator
    goal: reproduce the failure
  - id: fix
    role: implementer
    goal: make the smallest safe change
  - id: verify
    role: verifier
    goal: run targeted tests
uses_skills:
  - debugging
artifacts:
  - failure_summary
  - patch
  - test_report
gates:
  - before_destructive_command
  - before_public_api_change
---
```

These fields are resource declarations, not hardcoded branches in the work
layer.

## Command Model

Commands should be registered in a unified catalog and dispatched through typed
semantics rather than scattered across UI, session, and product code.

Suggested command classes:

- `prompt`: expands into model-visible instructions or messages
- `local`: executes local work-layer behavior and may return events or text
- `surface`: opens a semantic surface for channel-specific rendering
- `workflow`: starts or controls a long-running workflow
- `agent`: starts, routes, or supervises an agent lane
- `artifact`: creates, updates, previews, exports, or compares artifacts
- `admin`: reads or changes settings, diagnostics, status, or policy

Each command should carry:

- stable name and aliases
- domain app owner
- availability rules
- required capabilities
- whether it is safe in remote or restricted channels
- whether it may run during an active turn or run
- whether it produces model-visible content
- whether it opens a surface
- playback expectations for regression coverage

Command execution should produce typed effects or `WorkOperation`, not direct
terminal writes.

## Turn, Queue, And Interrupt Discipline

The architecture needs two queue levels:

```text
agent.harness queue
  steer / follow-up / next-turn queue for one prepared agent turn

work queue / task queue
  run / task / workflow / multi-agent scheduling above the harness
```

Required work-level concepts:

- active run state: idle, dispatching, running, cancelling, completing, failed
- pending operation queue
- priority classes for immediate, next, and later operations
- explicit distinction between user turns, steers, commands, approvals, and
  system notifications
- single owner for deciding when queued work may run
- deterministic transition after interrupt, cancellation, completion, and error

Suggested rule:

- if a user turn is running, normal user input becomes queued work
- if a steer is queued and the user interrupts the active turn, `work` should
  coordinate cancellation and then allow `agent.harness` to dispatch the first
  eligible queued steer
- surface/admin commands may be allowed during a running turn only if their
  command metadata explicitly allows it
- non-interactive channel operations must follow the same queue rules as TUI
  operations

The work queue must be work state, not TUI state. The harness queue must remain
single-turn execution state, not multi-agent scheduling state.

## Protocol Boundary

The external boundary should use operation/event semantics.

Operations flow in:

```text
host/channel -> WorkOperation -> loushang.work
```

Events flow out:

```text
loushang.work -> WorkEvent -> channel/host observers
```

Requests that require a response, such as approvals or user selections, should
use explicit correlation identifiers. They may be represented as
event/request families at the channel layer, but their work semantics should
remain auditable and replayable.

The protocol should support:

- in-process SDK embedding
- JSONL stdio
- HTTP request/response
- WebSocket streaming
- service-side event stream
- test playback from memory
- persisted event log replay

## Channel Capability Model

Channels should declare capabilities so `work` and domain apps can degrade or
enrich behavior without hardcoding channel names.

Example capabilities:

- streaming text
- rich blocks
- interactive surfaces
- keyboard interrupt
- ordered delivery
- reconnection
- file upload
- artifact preview
- approval prompts
- multi-observer session
- background notifications
- ephemeral message update
- durable transcript display

If a channel lacks a capability, the system should either:

- use a simpler event shape
- choose a non-interactive fallback
- require a host-side handler
- reject the operation with a typed error

## External Identity And Session Addressing

The architecture should model external identity explicitly instead of letting
each channel invent its own session-key rules.

Required objects:

- `ExternalIdentity`: user, account, tenant, organization, or service identity
- `ConversationAddress`: platform, channel, chat, thread, and message address
- `WorkspaceAddress`: local path, remote workspace, project, or tenant scope
- `SessionAddress`: normalized key used to find or create a work session
- `DeliveryAddress`: target used for replies, edits, notifications, or callbacks

The address model should support:

- one user across multiple channels
- one channel conversation with multiple users
- thread-scoped sessions
- tenant-scoped policy
- channel-specific alternate identifiers
- privacy-preserving display names
- deterministic resume and fork behavior

Session addressing should be a policy, not hardcoded string concatenation.
Different hosts may choose different policies:

- per workspace
- per user
- per chat
- per thread
- per upper-level host run
- per scheduled job

The selected policy should be recorded in session metadata so later replay,
search, audit, and resume behavior can explain why a session was grouped the
way it was.

## Delivery And Streaming Policy

Streaming is a delivery concern, not only an agent concern.

`work` should emit stable events such as `ContentDelta`, `ToolCallStarted`,
`ToolCallCompleted`, `ApprovalRequested`, and `WorkRunCompleted`. Each channel
then chooses how to deliver those events.

Suggested delivery strategies:

- `diff_frame`: for native terminal rendering
- `sse`: for HTTP event streams
- `websocket`: for interactive web or desktop clients
- `edit_message`: for platforms that support editing a previous message
- `draft_message`: for platforms with native draft streaming
- `chunked_messages`: for platforms with message length limits
- `final_only`: for channels where progressive updates are noisy or expensive

Delivery policy should handle:

- rate limiting
- coalescing
- retry and fallback
- message length limits
- final-message correction
- partial-delivery recovery
- platform-specific markdown or rich-block conversion
- cancellation and stale-response suppression

`work` should not know whether a platform implements streaming by editing a
message, sending a draft, pushing SSE frames, or repainting a terminal region.
It should only produce ordered events with enough metadata for `channel` to
make those choices.

## Multi-Agent And Workflow Model

Multi-agent collaboration should not live in `agent.harness`. It belongs in
`loushang.work`.

Core objects:

```text
TaskFlow
  A multi-step workflow.

TaskRun
  One concrete task instance.

AgentLane
  An agent execution lane bound to role, session, workspace, and tool scope.

TaskLedger
  Shared task, dependency, claim, heartbeat, and status ledger.

CollaborationBus
  Messages between agents, conductor instructions, and human intervention
  records.

ArtifactRef
  References to patches, test reports, review findings, summaries, and other
  work products.

ApprovalRequest
  High-risk actions, human confirmations, and policy gates.
```

The first version does not need a full team platform. It should support three
levels:

```text
Single Agent
  Default fast coding path.

Method-Guided Single Agent
  Method injects guidance but does not change execution topology.

Controlled Workflow
  Method compiles into fixed steps advanced by work.
```

Later versions can add:

```text
Subagent
  Main agent delegates a short task and consumes the result.

Team Run
  Multiple AgentLane instances collaborate with a shared TaskLedger.
```

Coding domain roles may include:

```text
planner
  Read-only, produces a plan.

investigator
  Read-only or limited execution, reproduces the issue.

implementer
  Can edit, produces a patch.

tester
  Can run tests, produces a test_report.

reviewer
  Read-only, produces review_finding.

integrator
  Aggregates artifacts, writes final summary, and applies or merges when needed.
```

These roles should come from method resources or domain app resources, not
hardcoded branches in `loushang.work`.

Default permissions should be conservative:

- planner and reviewer default to read-only
- tester can execute tests but not edit
- implementer can edit, preferably in an isolated worktree for risky changes
- integrator handles final apply, merge, and summary steps

## Coding Fast Path

The first version must preserve the current quick coding experience:

```text
loushang "fix this bug"
```

It should not default to a complex method plan or multi-agent team.

Default path:

```text
CLI/TUI input
  -> channel adapter
  -> SubmitCodingTurn
  -> WorkRun(single_turn)
  -> existing AgentSession.prompt()
  -> AgentEvent projection
  -> WorkEvent stream
  -> channel delivery
```

Only these cases should upgrade the execution mode:

- user explicitly selects a method
- user explicitly requests workflow, multi-agent, review, or full verification
- task risk is high
- task complexity exceeds a single-turn threshold
- method selector has a high-confidence match for a deeper workflow

Suggested modes:

```text
fast
  no method or skill-backed method

guided
  single-turn method projection

workflow
  fixed MethodPlan / TaskFlow

team
  multi-agent AgentLane
```

## Extension Registry And Hook Lifecycle

The architecture should expose extension registries as first-class boundaries,
not as one-off plugin side effects.

Suggested registries:

- command registry
- tool registry
- domain app registry
- channel adapter registry
- provider registry
- memory provider registry
- context engine registry
- method registry
- surface registry
- artifact renderer/exporter registry

Suggested hook families:

- `on_session_start`
- `on_session_end`
- `before_operation`
- `after_operation`
- `before_run`
- `after_run`
- `before_turn`
- `after_turn`
- `before_model_call`
- `after_model_call`
- `before_tool_call`
- `after_tool_call`
- `before_artifact_update`
- `after_artifact_update`
- `on_error`

Hook behavior should be typed. Hooks that only observe should not be able to
block. Hooks that can block or modify behavior must declare that capability and
should return structured decisions such as:

- allow
- block
- request approval
- inject context
- transform input
- transform output
- emit event

Extensions should be governed by capability and trust policy. A project-local
extension, user-installed extension, bundled extension, and remote extension may
have different default permissions.

## Memory And Context Services

Memory and context management should be shared services, not coding-only
helpers.

The memory service should support:

- pre-turn retrieval
- post-turn synchronization
- explicit memory writes
- provider-specific storage
- privacy and source attribution
- output scrubbing for hidden memory context
- session-start and session-end lifecycle

The context service should support:

- token accounting
- preflight context estimation
- compaction policy
- manual focused compaction
- head/tail protection
- structured summaries
- context-engine replacement by extension
- per-domain context projection

The architecture should separate:

- durable memory
- current session transcript
- temporary retrieved context
- hidden system context
- visible user-facing transcript
- domain artifacts

This separation is required for multi-channel use. A messaging channel may show
only final assistant text, while a TUI or GUI can expose detailed tool progress
and artifact state. Both should still be backed by the same work facts.

## Scheduler And Background Hosts

Scheduled work should be modeled as another host shape rather than a special
case inside a chat channel.

Required concepts:

- `ScheduledJob`
- `ScheduleTrigger`
- `BackgroundRun`
- `DeliveryTarget`
- `RunLease`
- `RetryPolicy`
- `TimeoutPolicy`

A scheduler host should submit `WorkOperation` the same way an interactive host
does. It may use different policies:

- restricted capabilities
- no interactive surfaces
- final-only delivery
- explicit delivery target
- isolated session addressing
- stronger timeout and retry limits

Scheduled jobs, background tasks, and long-running workflows should all emit
events and artifacts that can be inspected later through the normal session and
event store.

## Provider Routing And Failure Policy

Provider selection and failover should be modeled below domain apps and above
raw model adapters.

Required concepts:

- provider profile
- model profile
- credential source
- credential pool
- routing policy
- retry policy
- failover reason
- provider capability map
- usage and cost attribution

The architecture should distinguish:

- provider authentication failures
- billing or quota exhaustion
- rate limits
- overload and transient failures
- context overflow
- provider policy blocks
- unsupported modality or tool shape
- malformed provider responses

This lets hosts and channels present useful status without encoding provider
quirks themselves. It also allows upper-level hosts to supply their own routing
or credential policy while still using the same work and harness semantics.

## Session Store, Search, And Lineage

`work` should keep a durable session and event store that is useful across
channels and domain apps.

Required store capabilities:

- append-friendly events
- transcript reconstruction
- session metadata
- external address metadata
- artifact references
- parent/child session lineage
- fork and branch relationships
- compaction boundaries
- usage and cost records
- full-text or structured search
- audit-friendly operation history

The store should distinguish:

- raw operation log
- work event log
- user-visible transcript
- compacted model context
- artifact revisions
- diagnostic records

This distinction matters because a channel may display one projection, a
replay test may assert another, and an upper-level host may need a third form
for analytics or orchestration.

## TUI Stability And Performance Constraints

The native TUI must continue to preserve the already established goals:

- no unnecessary screen clearing
- no visible flicker during streaming
- stable composer input echo
- bounded render cost for long transcripts
- stable working timer updates
- deterministic resize recovery
- line-level or region-level differential rendering
- stable surfaces and overlays

To preserve these goals, the TUI should remain a `WorkEvent` consumer and
render-model owner, not the work state owner.

Recommended TUI flow:

```text
WorkEvent
  -> TUI state reducer
  -> logical render model
  -> frame scheduler
  -> diff renderer
  -> terminal writer
```

Events should not trigger direct terminal writes. High-frequency streaming
events should be coalesced by the frame scheduler. Transcript rendering should
continue to use bounded active windows and cached stable blocks.

## Playback Regression Model

Playback regression should become a first-class work and channel testing
strategy.

Layers:

- protocol playback: feed `WorkOperation`, assert `WorkEvent` sequences
- work playback: assert run, task, command, approval, and artifact state
- method playback: assert method selection, compilation, projection, and gates
- harness playback: assert turn lifecycle, queue behavior, save points, and
  `AgentEvent` projection
- channel playback: assert channel projection and capability fallback
- TUI playback: assert fake terminal frames, cursor/composer behavior, and
  bounded repaint behavior
- performance playback: assert frame count, render latency, and bounded work
  for long transcripts
- delivery playback: assert rate limiting, coalescing, edit/final fallback, and
  stale-response suppression
- identity playback: assert session-key policy, thread routing, resume, and
  fork behavior across channel addresses
- extension playback: assert hook decisions, injected context, blocked tools,
  and extension-provided commands

Playback outputs should support:

- in-memory assertions for automated tests
- optional event/session dump for human inspection
- optional screen-frame dump for visual debugging

This layer should cover most interaction correctness and performance regression
risk, while manual terminal testing remains a smaller final acceptance step.

## Upper-Level Host Integration

Upper-level architectures such as OpenClaw, Hermes, and Manus should integrate
through host/work APIs, not terminal emulation.

Required embedding surfaces:

- create or resume workspace/session
- submit operations
- subscribe to events
- invoke commands
- provide approvals and responses
- attach or consume artifacts
- control cancellation and shutdown
- observe diagnostics and usage

This allows an upper-level architecture to treat `loushang` as a work component
while keeping its own orchestration, product surface, deployment model, and
governance.

## First Version Scope

### P0: Wrap Existing `AgentSession` With `WorkRun`

Goal: establish the work shell without changing the user experience.

Scope:

- add `WorkOperation`
- add `WorkRun`
- add `WorkEvent`
- add minimal `EventLog`
- wrap existing `AgentSession.prompt()`
- project existing `AgentEvent` into `WorkEvent`
- add `run_id`, `session_id`, `domain`, and `operation_id` to work events

Out of scope:

- multi-agent
- method workflow
- complex scheduler

### P1: Method Resource Compatibility

Goal: let method degrade to skill and keep compatibility with the existing
skill ecosystem.

Scope:

- add `MethodDescriptor`
- extend the resource loader or add a method loader
- support `SkillDescriptor -> skill-backed MethodDescriptor`
- support `methods/**/METHOD.md`
- support `methods/**/SKILL.md`
- support single-turn `MethodPlan`
- inject method projection into prompt
- record `method_id` on `WorkRun`

### P2: Coding DomainApp

Goal: expose current coding capability as the first domain app.

Scope:

- `CodingDomainApp`
- coding operation kinds
- coding artifact types
- coding policy bridge
- coding method packs as resources
- gradual adaptation of existing command/session/tool behavior through the
  domain app boundary

### P3: Fixed MethodPlan / TaskFlow

Goal: support auditable multi-step method execution.

Scope:

- `MethodCompiler`
- `TaskFlow`
- `TaskRun`
- step started/completed events
- artifact created/updated events
- approval gates

### P4: Controlled Subagent

Goal: provide minimal multi-agent collaboration without a full autonomous team.

Scope:

- `AgentLane`
- read-only reviewer/planner lane
- implementer lane
- tester lane
- task assignment
- result aggregation

## Existing Code Migration Direction

### `AgentSession`

Current `AgentSession` is thick. It contains tool, prompt, queue, compaction,
extension, command, and session-store responsibilities.

Migration direction:

```text
Current:
  AgentSession remains the coding execution facade.

P0:
  WorkRun wraps AgentSession.prompt().

P1/P2:
  method projection and CodingDomainApp assemble AgentSession from outside.

Later:
  AgentSession gradually shrinks into CodingSessionFacade.
```

### `AgentSessionRuntime`

Current `AgentSessionRuntime` mainly manages one current session and one rebind
callback.

Migration direction:

```text
AgentSessionRuntime
  -> WorkSessionRegistry
  -> SessionController
  -> multi-session / multi-lane support
```

### `QueueController`

Current `QueueController` is a single-agent turn queue for steer and follow-up
work.

Migration direction:

```text
QueueController
  remains under agent.harness / single-agent turn semantics.

WorkQueue / TaskQueue
  added for work/task/multi-agent scheduling.
```

### `coding.workflow.runner`

Current workflow runner is better treated as a test, playback, and fixed
scenario validation tool.

Migration direction:

```text
Short term:
  keep it for workflow scenario tests.

Mid term:
  MethodPlan / TaskFlow can reuse its lessons, but production scheduling moves
  to loushang.work.
```

### `RpcMode`

Current RPC mode directly parses JSON lines and calls session methods.

Migration direction:

```text
RPC request
  -> WorkOperation
  -> WorkRun / WorkEvent
```

## Outside-In And Inside-Out Design

### Outside-In

External users and hosts should only need to see:

```text
submit operation
subscribe events
wait/cancel run
list artifacts
approve/reject request
```

They do not need to know whether the internal execution is a single agent, a
method workflow, or a multi-agent team.

### Inside-Out

The internal migration should abstract from existing capability:

```text
AgentEvent
  -> HarnessEvent
  -> WorkEvent

AgentSession.prompt()
  -> WorkRun(single_turn)

SkillDescriptor
  -> skill-backed MethodDescriptor

coding workflow tests
  -> MethodPlan / TaskFlow validation
```

## Success Criteria

The first version succeeds if:

- the existing coding fast path does not slow down
- every coding turn has a `WorkRun`
- every important output has a `WorkEvent`
- methods can be discovered, enabled, disabled, and overridden like skills
- a plain skill can be used as the smallest method
- an enhanced method can compile into a single-step `MethodPlan`
- the coding domain app can run as the first `DomainApp`
- future multi-agent and workflow features do not require rewriting channel or
  agent loop boundaries

## Non-Goals

The first version should not attempt:

- a complete autonomous team platform
- a complete GUI
- all channel adapters
- full self-evolution
- a complex method DSL
- replacement of existing `AgentSession`

The primary goal is to make the boundaries real:

```text
channel handles delivery
work handles run/task/event/artifact
method handles guidance/plan assets
domain app handles domain execution
harness handles one prepared turn
agent/ai handle the low-level model loop
```

## Open Questions

1. Which package should introduce `WorkOperation`, `WorkRun`, and `WorkEvent`
   first: a new `loushang.work` package or a transitional module under the
   current coding package?
2. What is the smallest event schema that can project current `AgentEvent`
   without losing turn, tool, approval, and artifact semantics?
3. Which current coding commands are domain commands, and which should become
   shared work commands?
4. What is the minimum `ArtifactRef` model that supports patches, reports,
   review findings, and future non-coding artifacts?
5. Which host API should be implemented first: in-process SDK, JSONL stdio,
   HTTP, or WebSocket?
6. How much of current RPC mode should be treated as a transitional surface
   versus a long-term channel implementation?
7. What is the minimum external identity model that can support terminal,
   HTTP, Feishu, WeChat, mini app, and upper-level host integrations?
8. Which method metadata fields are needed in P1, and which should wait until
   fixed `MethodPlan` support?
9. Which extension hooks are safe to expose early, and which should wait until
   capability governance is stronger?
10. What store backend is sufficient for early session search and lineage
    without overcommitting to a database architecture?
