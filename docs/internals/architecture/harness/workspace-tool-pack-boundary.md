# Harness Workspace Tool Pack Boundary

## Decision

`loushang.harness.tools.workspace` owns the reusable concrete workspace tool
pack. The owner includes read, list, find, grep, write, edit, and process
execution definitions together with the support code required to run them.

This is an ownership lift-and-shift. It preserves accepted Coding import paths
while avoiding an unrelated public API redesign in the same batch.

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

`coding.control` is frozen for this consolidation. Auth resolution, credentials,
model registries, provider registration, settings, and persisted model
selection do not move into Harness.

## Compatibility

The accepted `loushang.coding.tools.*` implementation modules are module-level
aliases to their Harness owners. The thin Coding factory adds product metadata
and the product-selected managed downloader. `coding.tools.builtins` remains the
product activation adapter.

The shared external-tool locator accepts the legacy `LOUSHANG_CODING_BIN_DIR`
and `LOUSHANG_CODING_AGENT_DIR` environment aliases and reuses an existing
`~/.loushang/coding/bin` directory. New installs default to the neutral
`~/.loushang/tools/bin` location.

These compatibility paths can be simplified after downstream imports have
moved. Their existence does not permit new implementation code in Coding.

## Evidence

- Harness tests construct and execute workspace tools without importing Coding.
- Coding compatibility tests verify module and public type identity.
- Architecture tests reject product imports from Harness and pin the product
  factory/builtin ownership split.
- Focused Coding tool tests prove existing execution, renderer, policy,
  external-tool, path, truncation, and Pi-compatible behavior.
