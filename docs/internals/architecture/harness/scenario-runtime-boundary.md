# Scenario Runtime Boundary

## Decision

`loushang.harness.scenario` owns reusable scripted interaction-scenario
mechanics. It intentionally keeps the accepted `Workflow` vocabulary because
scenario files already use that name, but it is not `loushang.work` and does
not model a MethodPlan, a work artifact, or a WorkEvent lifecycle.

```text
Scenario
  -> Product-selected ScenarioAdapter
  -> RuntimeEvent / Product interaction
  -> ScenarioResult

Work / Method
  -> domain plan and completion semantics
  -> WorkEvent and artifact lifecycle
```

The Scenario runtime is an execution and verification mechanism. A Product,
OEM, or test suite selects inputs, adapters, artifact rules, and completion
criteria.

## Harness Ownership

Harness owns:

- immutable workflow steps, expectations, event patterns, and result values;
- JSON/YAML scenario parsing and deterministic scenario-file discovery;
- sequential execution, wait, timeout, abort, progress-observer, and result
  collection mechanics;
- a structural `ScenarioAdapter` / `WorkflowAdapter` contract;
- an optional Agent-session adapter that observes `RuntimeEvent` when exposed,
  with a legacy product-event subscription fallback;
- read-only file assertions relative to the Product-selected working root;
- the `CommandRunner` protocol and command-result value.

Harness does not import a Product or execute an assertion command. A command
expectation without a supplied `CommandRunner` becomes a failed check with a
clear diagnostic. This prevents an implicit shell policy from becoming a
cross-product default.

## Product Ownership

Coding keeps:

- CLI orchestration, text/JSON reporting, scenario discovery policy, and
  Product fixture selection;
- the Product decision to run a local shell command for legacy workflow
  assertions;
- its default `run_local_shell_command` adapter, including `shell=True`;
- Product prompt semantics, model readiness checks, and session/runtime
  creation and disposal.

Other Products may supply an `ExecService`-backed runner, an approval-aware
runner, a remote runner, or no command runner at all. They need not depend on
Coding to reuse the scenario engine.

## Compatibility

`loushang.coding.workflow` remains an accepted compatibility namespace. Its
schema, loader, event, assertion, fake-runtime, and runner imports re-export
Harness-owned implementations. Its runner injects Coding's legacy local
command-runner default; it does not duplicate execution or assertion logic.

## Non-Goals

This migration does not add:

- a scenario persistence, event-log, or replay protocol;
- a cross-process scheduler or team/subagent orchestration;
- shell execution, approval policy, or workspace-root policy in Harness;
- a replacement for `loushang.work`, `loushang.method`, or Product artifact
  completion semantics.

## Verification

- `harness.scenario` imports no Coding, Work, Method, TUI, AI, or Agent code;
- Harness scenario command assertions require an injected `CommandRunner`;
- Coding compatibility imports preserve schema and event object identity;
- a minimal OEM-style adapter validates that the core runner needs only the
  `ScenarioAdapter` prompt contract, without a Coding test double;
- an Agent session that exposes `subscribe_runtime_events()` is observed via
  the common RuntimeEvent stream, including a no-provider Coding `AgentSession`
  integration probe;
- Coding's existing scenario CLI and workflow tests retain their behavior.
