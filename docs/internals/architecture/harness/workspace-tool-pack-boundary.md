# Harness Workspace Tool Pack Boundary

## Decision

`loushang.harness.tools.workspace` owns the reusable concrete workspace tool
pack. The owner includes read, list, find, grep, write, edit, and process
execution definitions together with the support code required to run them.

This is the canonical public owner. Products import it directly rather than
through a product compatibility facade.

## Harness Ownership

Harness owns:

- `ToolContext` and the neutral context-provider/event-sink shapes;
- definition normalization, wrapping, argument preparation, cancellation, and
  update helpers;
- read, list, find, grep, write, edit, and bash implementations;
- local operation adapters, ignore matching, diff generation, process helpers,
  output previews, truncation projections, and neutral renderers;
- optional `fd`/`rg` discovery, managed download mechanics, and a neutral
  `LOUSHANG_WORKSPACE_TOOLS_DIR` location override;
- policy-enforcement plumbing and `PolicyEnforcementError`, expressed against
  an injected evaluator and Harness approval resolver.

Harness provides generic workspace descriptions. It does not import Coding or
AI packages, choose a product tool pack, select allowed roots, classify risk,
or resolve credentials and models.

## Product Ownership

Coding retains:

- builtin pack membership, default activation, and activation order;
- product-tuned tool descriptions and prompt snippets;
- `PolicyEngine`, risk rules, approval defaults, and interactive approval UI;
- workspace root/sandbox selection and product explanations;
- Coding protocol, command, session, UI, and transcript projections.

`coding.control` is frozen for this consolidation. Model registries, provider
registration, settings, and persisted model selection do not move into Harness.
Request authentication remains AI-owned and does not move into Harness.

## Product Composition

`loushang.coding.tool_pack` adds Coding metadata and the product-selected
managed downloader, then registers Coding's selected tool pack through
`WorkspaceToolRegistry`. It is not a generic tools facade.

The shared external-tool locator accepts the legacy `LOUSHANG_CODING_BIN_DIR`
and `LOUSHANG_CODING_AGENT_DIR` environment aliases and reuses an existing
`~/.loushang/coding/bin` directory. New installs default to the neutral
`~/.loushang/tools/bin` location.

`loushang.coding.tools` is not an accepted compatibility path. Generic callers
must import their concrete Harness owner, and Pi-style aliases are not carried
forward.

## Evidence

- Harness tests construct and execute workspace tools without importing Coding.
- Coding tests verify its selected metadata and activation without recreating a
  generic tool owner.
- Architecture tests reject product imports from Harness and pin the product
  factory/builtin ownership split.
- Focused Coding tool tests prove existing execution, renderer, policy,
  external-tool, path, truncation, and Pi-compatible behavior.
