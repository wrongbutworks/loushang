# Session Agent Runtime Boundary

This document defines Slice A of the Coding shared-layer migration.  It is an
implementation boundary, not a compatibility promise for the old module
layout.

## Baseline

`src/loushang/coding/session/agent_session.py` started at 1,729 lines and is
now 510 lines after the first cutover.
Most of its constructor assembles already shared Harness runtimes: transcript
context, queue and turn policy, retry, compaction/navigation, resource
refresh, tool activation, extension lifecycle, and session disposal.

## Target ownership

`loushang.harness.session.composition`,
`loushang.harness.session.operations_runtime`, and
`loushang.harness.session.agent_adapter` own the reusable composition and
runtime coordination.  They accept explicit Product ports for:

- transcript/session storage and context application;
- model/thinking selection and persisted settings;
- resource and package policy;
- extension bindings and provider actions;
- compaction and branch-summary executors;
- diagnostics, approval, command, and presentation callbacks.

The Harness runtime must not import Coding, Method, Work, or product resource
content.  It may use the stable Agent/AI value contracts already admitted by
`harness.session`.

The implementation diff deletes 1,399 Coding lines and adds 1,949 shared
Harness lines.  This is a 0.72 deletion/addition ratio; tests and
documentation are excluded.

Coding keeps only its product plan and adapters: preferred model policy,
resource roots, command wording, Coding compaction/branch-summary prompts,
provider conversion, footer/diagnostic presentation, and Coding extension API
behavior.

## Deletion condition

The old `AgentSession` implementation is reduced to a thin Product adapter.
No generic queue, retry, compaction/navigation, extension lifecycle,
tool/resource controller, transcript export, or disposal implementation may
remain duplicated in Coding.  The remaining 510 lines are limited to
composition inputs, model restoration, resource/package policy, provider and
footer behavior, replacement validation, and Product compaction/branch hooks.

## Compatibility and validation

The public Coding session surface and RPC wire shape remain unchanged.  The
slice is accepted only when focused session tests, AgentSession regressions,
architecture import-boundary tests, Ruff, and `git diff --check` pass.  A
Harness fake-product probe must construct and dispose the shared runtime
without importing `loushang.coding`.
