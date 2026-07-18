# Session Facade Boundary

## Decision

`loushang.harness.session.SessionFacade` owns the standard Product-facing
operation surface over an already composed optional Agent session. It combines
existing Harness-owned runtimes through narrow ports; it does not create a new
Agent loop, transcript repository, tool registry, command catalog, or
compaction implementation.

The Facade provides:

- queue-aware state and transcript context/record/file reads;
- active-tool and command catalog access, plus ordered command dispatch;
- prompt, steering, follow-up, queue inspection/clear, runtime subscription,
  continue, abort, and idle waiting;
- selected command-tool execution with output forwarding, cancellation, and
  retry controls;
- common transcript inspection for fork candidates and assistant text.

`SessionRuntime`, the Agent transcript profile, session capabilities runtime,
and maintenance runtimes remain their own owners. The Facade only makes their
already-bound operations available through one reusable Product surface.

## Product Binding

A Product supplies its already-admitted:

- `SessionRuntime` with turn policy, application-input policy, event routing,
  and transcript-commit binding;
- transcript, tools, commands, command-execution, view, and retry ports;
- prompt content, model/thinking selection, context policy, lifecycle cleanup,
  and channel event projection.

The view port may project state and context usage into the Product's own domain
types. The Facade deliberately does not impose a universal session-state schema
or a universal Product command result schema.

## Coding Binding

Coding `AgentSession` is a compatibility and Product adapter over the Facade.
It retains model catalog and auth resolution, provider registration, default
tools and prompt content, Coding command handlers, extension API event and
`user_bash` mapping, Pi-style protocol aliases, package/root/trust policy,
diagnostic wording, compaction strategy, lifecycle cleanup, and TUI/RPC/HTML
projection.

In particular, Pi-style `executeBash` options and result aliases remain in
`BashController`. Harness exposes only neutral selected command-tool execution;
it must not acquire Pi protocol vocabulary.

## Dependency Rule

`harness.session.facade` may depend on public Agent/AI message values required
by `SessionRuntime`, Harness runtime/event/tool contracts, and workspace output
types. It must not import Coding, a Product store, model/provider/auth runtime,
extension runner API, Product configuration, or any UI/RPC/HTML type. Product
policy is passed through the bound ports rather than imported.

## Verification

- Harness contract tests compose the Facade with an independent fake Product
  runtime, transcript, tools, commands, command tool, view, and retry port.
- Coding session regressions preserve the public `AgentSession` behavior while
  its common operations delegate through `SessionFacade`.
- Architecture tests prohibit Coding imports and Pi protocol names in the
  Facade, and require Coding `AgentSession` to adopt it.
