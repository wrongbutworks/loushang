# Coding LSP Architecture

[Coding Architecture](../loushang-coding-system-context.md)

## Status

Proposed architecture package.

This package designs the `coding.lsp` Product capability. It does not describe
an already implemented runtime. Current code and accepted Coding/Harness ARDs
remain authoritative until this proposal is accepted and implemented.

## Architecture Method

The design follows the repository's architecture method in this order:

```text
Requirements
  -> Specification
  -> Subsystem placement
  -> System context
  -> Candidate components
  -> Component boundaries
```

Read the documents in that order:

1. [Requirements](requirements.md)
2. [Specification](specification.md)
3. [Subsystem Placement](subsystem.md)
4. [System Context](system-context.md)
5. [Candidate Components](candidate-components.md)
6. [Component Boundaries](component-boundaries.md)

The adjacent [Harness Foundation](harness-foundation.md) design records the
Product-neutral Process Hosting, authorization/sandbox-lifetime, and session
cleanup required before production active LSP. Its separate committed
workspace-mutation contract supports the later passive diagnostic loop; it is
not a prerequisite for active semantic queries. The design does not move LSP
protocol semantics into Harness.

## Decision Summary

The canonical Product capability id is `coding.lsp`, not `code.lsp`, because
the owning Product package is `loushang.coding` and the established sibling id
is `coding.arch`.

`coding.lsp` is:

- a Coding Product Capability Bundle;
- language-extensible through declarative Server definitions;
- independent of VS Code, Cursor, or another editor;
- backed by separately installed language-server executables;
- model-facing through bounded, structured code-intelligence tools;
- workspace/session-scoped at first, with language-server processes started
  lazily and retained until crash, explicit stop, or Session close in P0;
- capable of both active semantic queries and passive diagnostic feedback;
- optional and governed by the existing `disabled | on_demand | always`
  Product capability mount policy.

It is not:

- a new top-level Loushang subsystem;
- part of `loushang.agent` or `loushang.ai`;
- a Method or Work runtime;
- a replacement for `coding.arch`, compilers, linters, or tests;
- permission to download or execute an arbitrary language server.

## Reference Synthesis

The target combines two reference lessons:

```text
CC lesson
  Product-native feedback loop:
  semantic query -> edit sync -> diagnostics -> next-turn repair

Codex lesson
  Optional capability packaging:
  core remains small; specialized capability is discovered and activated
  only when relevant, and a warm helper process can be reused.
```

Loushang adds its own boundary model:

```text
Coding Product
  owns capability identity, defaults, server admission, tools, diagnostics,
  prompt guidance, configuration, and presentation

Harness
  owns product-neutral tool composition, policy/approval enforcement,
  workspace mutation mechanics, lifecycle/disposal, and context budgets

Extension or package
  may contribute declarations, but cannot grant itself execution authority
```

The references are used deliberately, not copied wholesale:

| Concern | CC reference | Codex reference | Loushang decision |
| --- | --- | --- | --- |
| Product loop | Native semantic tools plus edit-to-diagnostic feedback | Mainline has no equivalent Product LSP loop | Adopt the complete loop as a Coding capability |
| Packaging | Product-integrated runtime and plugin Server declarations | Experimental Skill/daemon demonstrates optional, warm capability packaging | Use `coding.lsp` plus a separate `coding.lsp.tools` family |
| Lifecycle | Lazy external Server processes | A task-specific warm helper can survive repeated calls | Keep processes warm only inside a session/workspace owner |
| Safety | Trust and file filtering around Server use | Narrow task surface | Product admission precedes launch; no implicit installation |
| Extensibility | Language definitions supplied by plugins | Skill-specific adapter | Normalize declarative definitions through Coding, not Harness |

CC is the behavioral feedback-loop reference. The observed Codex LSP work is
experimental capability packaging rather than an accepted generic Codex LSP
subsystem, so this design does not attribute Product runtime guarantees to it.

## Target Shape

```text
Coding config / CLI / package / extension
                |
                v
      coding.lsp Product binding
        catalog + admission + selector
                |
                v
      workspace-scoped LSP runtime
       supervisor + client + documents
          |                    |
          v                    v
 active semantic tools    diagnostic inbox
          |                    |
          +--------+-----------+
                   v
             Agent context
```

Tool activation and process startup are deliberately separate:

- `on_demand` or `always` controls whether tool definitions are available or
  active in the Coding session;
- the selected language-server process still starts only on first relevant
  use; workspace warm-up is a deferred Product policy.

## Relationship To `coding.arch`

`coding.arch` owns deterministic project-structure facts such as import graphs,
cycles, hotspots, and architecture boundaries. `coding.lsp` owns online
language-semantic facts such as definitions, references, types, implementations,
call hierarchy, and diagnostics.

Future integration may let `coding.arch` consume an optional semantic-fact
port, but its deterministic analyzer and CI gates must continue to work without
an LSP Server.

## Implementation Status Rule

Implementation progress belongs in a dated plan or issue, not in these live
architecture documents. When implementation changes an accepted boundary,
update this package and the affected canonical Coding/Harness architecture note
in the same integration change.
