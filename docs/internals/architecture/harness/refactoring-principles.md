# Harness Refactoring Principles

## Purpose

This document defines the rules for moving shared behavior into
`loushang.harness`.

The goal is to make future products easier to build without making harness a
new product framework, a second agent runtime, or a dumping ground for code that
happens to be reused once.

## Core Rule

Harness owns product-neutral mechanisms. Products own policy and semantics.

Put code in harness only when all of these are true:

- it is demonstrably product-neutral and useful to planned product lines; a
  second production consumer is evidence, not a prerequisite;
- it does not depend on coding, design, research, ppt, cowork, TUI, method,
  work, or AI provider semantics;
- it describes a contract, helper engine, registry, resolver, lifecycle shape,
  or neutral event/presentation record;
- product adapters can choose defaults, policy, activation, storage, and UI
  behavior outside harness.

Keep code out of harness when it decides what a specific product should do,
which tools should be enabled by default, how a product prompt is assembled,
how product artifacts are materialized, or how a product UI should behave.

## Neutrality Evidence Gate

A Harness extraction does not require a second production consumer. It may
proceed before another product ships only when all of the following evidence
is present:

- a boundary decision names the product-neutral mechanism, the product policy
  left behind, and explicit non-goals;
- the Harness API uses product-neutral vocabulary and carries no product
  imports, product defaults, or product-specific storage and UI semantics;
- the existing product adapter proves compatibility with current behavior;
- an independent contract probe exercises the proposed API without Coding
  runtime objects or Coding vocabulary;
- focused tests enforce behavioral invariants, dependency direction, and any
  accepted compatibility identities;
- the API stays in a focused module and avoids premature top-level exports.

The independent contract probe may be a minimal reference adapter, a planned
product spike, or a product-neutral test fixture. A renamed Coding fixture is
not sufficient: the probe must construct and exercise the contract from the
neutral boundary. When that probe exposes a required product-shaped field or
policy decision, split the contract again or keep it product-owned.

A later production consumer should validate and refine the contract, but its
absence is not a migration blocker when this evidence gate is satisfied.

## Mechanism Versus Policy

Use this split when judging a candidate:

| Concern | Harness may own | Product adapter owns |
| --- | --- | --- |
| Tools | registry interfaces, schema inference, contribution resolution, neutral tool metadata | default tool set, product tool names, destructive-tool policy, tool descriptions tuned for a product |
| Approval | approval request/decision value types, resolver protocol, headless deny/allow defaults | interactive approval UI, product-specific rules, persisted allowlists |
| Presentation | neutral content blocks, renderer protocol, renderer registry | terminal/web widgets, product-specific transcript layout |
| Resources | source descriptors, frontmatter parsing, merge/diagnostic primitives | prompt/theme/skill loading policy, search roots, product resource semantics |
| Workspace | file/process operation protocols, neutral exec request/result shapes | when an operation is allowed, how it is explained to users, workspace defaults |
| Context | context item refs, budget accounting, packing contracts | what content is important, summarization prompts, product-specific memory policy |
| Session | host lifecycle protocols, idle/abort/dispose/queue snapshots | transcript schema, controllers, product session store, command execution |
| Diagnostics | diagnostic records, severity/source vocabulary, query interface | product health checks, user-facing grouping, remediation text |

The product adapter can call harness engines. The product adapter chooses how
those engines are configured and exposed.

## Top-Level Package Discipline

Do not create new top-level packages merely because a concept is shared.

Preferred destinations for shared substrate:

- `loushang.harness.workspace`
- `loushang.harness.resources`
- `loushang.harness.context`
- `loushang.harness.approval`
- `loushang.harness.presentation`
- `loushang.harness.tools`
- `loushang.harness.diagnostics`

Avoid new top-level packages such as:

- `loushang.runtime`
- `loushang.product`
- `loushang.workspace`
- `loushang.context`
- `loushang.memory`
- `loushang.session`

`loushang.work`, `loushang.method`, `loushang.agent`, `loushang.ai`, and
`loushang.tui` are separate subsystem packages with their own boundaries. They
should not be absorbed into harness.

`loushang.resource` currently exists as a small shared frontmatter location. If
resource substrate becomes harness-owned, prefer a planned migration into
`loushang.harness.resources.frontmatter` instead of expanding the top-level
`loushang.resource` package.

## Import Rules

Harness may import stable `loushang.agent` primitives.

Harness must not import:

- product packages;
- `loushang.method`;
- `loushang.work`;
- `loushang.tui`;
- `loushang.ai`;
- channel implementations.

If a contract needs to reference work, method, channel, UI, or product facts, it
should use opaque strings, dataclasses with neutral fields, or protocols defined
inside harness. The consumer outside harness performs the interpretation.

## Public API Rules

Keep `loushang.harness.__init__` small.

Do not add every harness type to top-level `__all__`. Prefer direct imports
from focused modules, such as:

```python
from loushang.harness.commands import CommandDef
```

Top-level exports are reserved for stable, intentional entry points. This
prevents early internal contracts from becoming public API accidentally.

## Migration Slice Checklist

Each code migration slice should be small enough to review as one boundary
change.

Before moving code:

- identify the harness mechanism and the product policy being left behind;
- choose the target harness module;
- check that no forbidden imports are introduced;
- decide whether old imports are removed or temporarily shimmed;
- define focused tests proving product behavior is unchanged.

During the move:

- move types before engines;
- move engines before product defaults;
- keep command handlers, prompt policy, UI controllers, and session stores in
  product packages;
- update internal imports to the new harness path;
- run architecture import-boundary tests.

After the move:

- keep or add docs that explain the new owner;
- remove transitional shims unless an accepted compatibility decision says
  otherwise;
- do not expand harness top-level exports unless the contract is intentionally
  public.

## Parallel Lane Safety

Harness refactoring is safe to run in parallel with `tui`, `agent`, and `ai`
lanes if it follows these constraints:

- it does not change the agent loop contract without coordination with the
  agent lane;
- it does not change provider/model/auth behavior without coordination with the
  AI lane;
- it does not change terminal primitives or render-loop behavior without
  coordination with the TUI lane;
- it keeps shared contracts product-neutral and leaves product-specific wiring
  in product packages.

The harness lane should coordinate with the code lane whenever a slice changes
`loushang.coding` behavior, tests, or imports.
