# Session Capabilities Runtime Boundary

## Decision

`loushang.harness.session.capabilities` owns the live application of
Product-selected session capabilities:

- tool selection, allowed-name filtering, live Agent-tool rebind, and prompt
  rebuild notification;
- ordered composition of approved command sources and ordered command dispatch;
- selected workspace command-tool invocation, incremental output forwarding,
  cancellation, portable command-result normalization, transcript commit, and
  context refresh.

It reuses the existing `ToolActivationCoordinator`, `CapabilityPackComposer`,
command dispatch primitives, workspace execution types, and
`CommandExecutionRecord`. It does not create another tool registry, command
catalog, workspace backend, or transcript repository.

## Product Binding

Products supply callback ports for:

- default and initial tool selection, contribution admission, and tool context;
- prompt construction after the active tool set changes;
- command-source descriptors, priorities, and concrete command handlers;
- current workspace, selected command-tool definition, command parameter
  construction, call ID, transcript append, and context refresh;
- approval/extension interception and Product diagnostics translation.

The runtime deliberately permits a different descriptor priority and handler
priority for a command source. A Product can display its built-in command
before an extension command while allowing the extension to handle that
invocation first. Source admission and Product policy happen before values are
passed to Harness.

## Coding Binding

Coding binds `ToolController`, `CommandController`, and `BashController` as
thin adapters. Coding keeps its prompt text, default built-in tools, concrete
tool context, tool admission diagnostics, built-in command implementations,
resource and extension command mapping, `user_bash` extension protocol,
Pi-style result projection, and TUI/RPC/HTML presentation.

`BashController` currently chooses the `bash` workspace tool and constructs
`['/bin/bash', '-lc', command]`. That shell choice is a Coding binding decision;
the Harness runtime only owns selected command-tool lifecycle and portable
result commit mechanics.

## Dependency Rule

This optional Agent-session profile may import public Agent tool contracts,
Harness capability primitives, workspace execution types, and portable
conversation records. It must not import Coding, Product prompts, extension
runner APIs, providers, model/auth resolution, Product stores, or UI/RPC
types. Those concerns are supplied through explicit ports.

## Verification

- Harness tests verify neutral tool rebind, separate command catalog/dispatch
  precedence, and a command execution's single transcript commit.
- Coding tests preserve active-tool policy, command precedence, extension
  interception, Bash protocol output, and transcript context projection.
- Architecture tests require the Harness runtime to stay free of Coding imports
  and the three Coding controllers to adopt the Harness runtime classes.
