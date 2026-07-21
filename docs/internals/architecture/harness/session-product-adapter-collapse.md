# Session Product Adapter Collapse

## Decision

`loushang.harness.session` is the only owner of common live-session
mechanics. `SessionRuntime` owns the Agent loop subscription, prompt and queue
ordering, ApplicationMessage delivery, ordered runtime events, and abort/idle
coordination. `SessionFacade` owns the reusable Product-facing operation
surface. `AgentSessionInspector` owns product-neutral state, context usage,
statistics, and transcript text/fork-candidate observation. The Agent
transcript maintenance runtime owns retry state and retry lifecycle.

Coding must bind those components through explicit Product ports. It must not
recreate a session runtime, a session event stream, a retry state machine, or
an inspection controller merely to adapt Coding policy.

## Implemented Collapse

- `SessionFacadePorts` groups the transcript, tools, commands, selected
  command-tool, inspection, and retry adapters supplied by a Product. It keeps
  those Product decisions separate from `SessionRuntime` ownership.
- `AgentSession` now supplies `AgentSessionInspector` directly as its Facade
  inspection port. The removed `coding.session.SessionViewController` was only
  a binding wrapper around the Harness inspector.
- Pi-style statistics and camelCase fork-candidate payloads live in
  `coding.platform.session_projection` as pure Coding projections. They are
  not a Harness state model or a session controller.
- `AgentSession` now binds Coding retry settings, its Agent state, and the
  overflow classifier directly to `AgentTranscriptRetryRuntime`. The removed
  `coding.session.RetryController` was only a constructor wrapper.
- Historical private forwarding methods that had no production consumer have
  been removed from `AgentSession`; callers use the composed Harness runtime
  or Product adapter directly.
- `ExtensionInputRuntime`, `ExtensionAgentHookRuntime`, and
  `ExtensionAgentEventRuntime` own standard extension input delivery, Agent
  hook composition, and lifecycle-event mirroring in the optional
  `harness.extensions.agent` profile, where lifecycle is observation-only and
  typed ports prevent a reverse Session dependency. `ExtensionSessionRuntime`
  owns bind/refresh/invalidation coordination. The removed Coding controllers
  were implementation-only wrappers around these product-neutral mechanics.

## Product Boundary

Coding retains:

- model registry, model/auth resolution, provider registration, and model or
  thinking selection policy;
- Coding prompt content, default tool selection/materialization, `bash` and
  other code-tool semantics, command handlers, and summary prompts/model calls;
- Coding extension API/hooks, package/root/trust policy, diagnostics wording,
  session index policy, cwd/session-file acceptance, and lifecycle cleanup;
- Pi/RPC/TUI/HTML wire projections, command aliases, and Coding display state.

These are Product semantics, not reusable Host/Session mechanics. Moving them
to Harness would create false neutrality and make Research, Design, PPT, and
OEM adapters depend on Coding vocabulary.

`AgentTranscriptSessionRuntime` composes the common lifecycle transaction with
the transcript directory/catalog runtime. `AgentSessionRuntime` binds that
facade directly and retains only the Coding file-store, cwd acceptance,
`before` fork interpretation, extension hooks, diagnostics, package APIs,
session-index policy, and presentation ports. This wave does not move
ModelRegistry, authentication, Coding extension APIs, code tools, or UI
projection.

## Verification

- Harness Facade tests compose `SessionFacadePorts` with independent fake
  Product ports.
- Coding session tests verify the direct inspector and Pi projection preserve
  context usage, stats, fork-candidate, retry, and `AgentSession` behavior.
- Architecture tests require Coding to adopt the Harness Facade, inspector,
  and retry runtime while prohibiting the removed controller paths.
