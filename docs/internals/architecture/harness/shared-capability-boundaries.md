# Shared Capability Boundaries

## Purpose

This document describes how common capabilities should be split between
`loushang.harness`, product adapters, OEM layers, and extensions.

The guiding rule is:

```text
harness provides mechanism
product adapter provides defaults and semantics
OEM layer overrides product policy
extensions contribute optional capabilities
```

## Layer Model

The long-term product stack is:

```text
client / UI / SDK
  -> channel
  -> work
  -> method            # optional structured-work layer
  -> product adapter   # coding / design / research / ppt / cowork
  -> harness
  -> agent
  -> ai
```

This is a responsibility stack, not a blanket import rule. The important import
rule is that harness stays below product adapters and above agent primitives.
It must not reach upward into product, work, method, channel, TUI, or AI
provider details.

## Product Kernel Ownership

Prompts, skills, and tools are central product assets, but they are not the
complete product boundary. Every product adapter retains an irreducible kernel
of domain semantics and policy:

- product goals, domain language, and completion criteria;
- system prompt and prompt-section content;
- skill content and default activation policy;
- domain-specific concrete tools;
- selection and activation policy for shared tool packs;
- context salience, compaction, and summarization policy;
- risk classification, approval defaults, and permission policy;
- artifact semantics, such as code changes, research reports, slide decks,
  design assets, or collaborative documents;
- product commands, configuration defaults, and presentation projections;
- resource search roots, file conventions, and compatibility formats.

Harness may own the value types, registries, assembly engines, schedulers, and
other mechanisms used to apply these decisions. It must not choose the values
or defaults on a product's behalf. A reusable concrete capability that is not
domain-specific may live in a shared tool or capability package; each product
still decides whether and how that capability is enabled.

This product kernel is what differentiates `coding`, `design`, `research`,
`ppt`, `cowork`, and OEM products. Product bootstrap and wiring should become
small as Harness grows, but these semantics must not migrate merely to reduce
the number of lines in a product package.

## Tools

Harness may own:

- tool definition value types that are not product-specific;
- schema inference and normalization helpers;
- registry/resolution interfaces;
- contribution records from packages or extensions;
- availability metadata and diagnostics;
- wrapper engines that adapt neutral tool call inputs to `loushang.agent`
  tool primitives.

Product adapters own:

- default tool packs;
- product-specific tool names and descriptions;
- concrete coding/design/research/ppt behavior;
- prompt wording around tool use;
- destructive-operation policy;
- product-specific tool discovery.

Extensions may contribute tools through harness-shaped records, but product or
OEM policy decides whether those tools are active.

## Approval

Harness may own:

- `ApprovalRequest`;
- `ApprovalDecision`;
- `ApprovalResolver` protocol;
- headless default resolvers such as deny-all or allow-readonly;
- approval broker mechanics that can suspend and resume a pending decision.

Product adapters own:

- interactive approval UI;
- product-specific risk classification;
- persisted allowlists;
- explanations shown to users;
- default approval rules.

The first harness migration should keep interactive resolvers outside harness
unless a neutral broker can be expressed without importing UI callbacks.

## Presentation And Renderers

Harness may own neutral presentation records:

- text blocks;
- structured rows or key/value fields;
- file references;
- image/file/artifact references by opaque id;
- renderer protocols and registry mechanics.

Harness should not import `loushang.ai` content-part types directly. It may
adapt to agent tool result primitives or define its own neutral presentation
blocks.

Product adapters and UI packages own:

- terminal widgets;
- web/app rendering;
- transcript layout;
- product-specific labels and grouping;
- incremental rendering behavior.

## Workspace And Exec

Harness may own neutral workspace mechanics:

- workspace path reference types;
- file operation request/result shapes;
- process execution request/result shapes;
- stream event records;
- workspace tool protocols.

Product adapters own:

- which workspace roots are allowed;
- whether shell commands can run;
- approval policy around writes and process execution;
- how file edits are described to users;
- default workspace tool activation.

Use `loushang.harness.workspace` or `loushang.harness.tools.workspace`; do not
create a top-level `loushang.workspace` package.

## Resources

Harness may own:

- resource descriptors that are product-neutral;
- source metadata;
- frontmatter parsing;
- resource diagnostics;
- merge and precedence primitives when expressed generically.

Product adapters own:

- prompt/theme/skill/extension semantics;
- search roots;
- default bundled resources;
- product-specific resource validation;
- resource injection into prompts or tools.

If `loushang.resource.frontmatter` becomes part of the shared substrate, migrate
it intentionally into `loushang.harness.resources.frontmatter` rather than
expanding `loushang.resource` into a broad top-level subsystem.

## Prompt

Harness may own prompt assembly contracts:

- prepared prompt value types;
- prompt section records;
- trace/diagnostic records;
- assembler protocol.

Product adapters own:

- system prompt text;
- product instructions;
- AGENTS.md or equivalent loading policy;
- template selection;
- prompt ordering;
- domain-specific preflight.

Prompt defaults are product behavior. Only the neutral assembly contract belongs
in harness.

## Context

Harness may own:

- context item refs;
- context bundles;
- budget accounting;
- truncation and packing contracts;
- neutral context assembly protocol;
- context diagnostics.

Product adapters own:

- what facts enter context;
- ranking and salience policy;
- summarization prompts;
- domain-specific compaction behavior;
- transcript rebuild semantics.

Do not create `loushang.context` now. Use `loushang.harness.context` for shared
mechanics and keep product memory/context policy inside product packages.

`loushang.harness.context.budget` now owns deterministic percentage/reserve
threshold accounting and `loushang.harness.context.usage` owns the neutral
usage-estimate result record. Coding still owns message token estimation,
model adaptation, usage snapshots, compaction decisions, and all transcript
policy. Context item refs, bundles, diagnostics, and general packing contracts
remain deferred.

## Memory

Harness may later own a narrow memory provider protocol:

- `MemoryRef`;
- `MemoryQuery`;
- `MemoryHit`;
- `MemoryProvider`.

Harness should not own memory storage, long-term profile semantics, or product
memory policy. Those belong to products, OEM layers, or deployments.

Do not introduce top-level `loushang.memory` until there is a separate accepted
architecture decision.

## Session And Lifecycle

Harness may own:

- host lifecycle protocols;
- idle/abort/dispose contracts;
- queue snapshot records;
- steering/follow-up request shapes;
- run status and generic session status records.

Product adapters own:

- session controllers;
- transcript storage;
- JSONL schemas;
- command execution;
- product event buses;
- product resource watchers;
- UI-facing session models.

Do not move `AgentSession`, product controllers, or store code wholesale into
harness.

`loushang.harness.host.types` now owns neutral host status, lifecycle events,
run state, and queue snapshots. `loushang.harness.host.queue` owns the generic
input-queue ledger, `loushang.harness.host.events` owns ordered event dispatch,
and `loushang.harness.host.runtime` owns driver-delegating run/abort/idle/dispose
coordination. Coding retains message construction and delivery, its event
schema and projection, session controllers, replacement, transcript storage,
and UI state.

## Work, Method, And Channel References

Harness may carry opaque ids or metadata for:

- work runs;
- method descriptors;
- method steps;
- artifacts;
- channel requests.

Harness must not import `loushang.work`, `loushang.method`, or channel core to
interpret those values. Product adapters, work projection, and channel hosts
perform interpretation outside harness.

## Diagnostics

Harness may own:

- neutral diagnostic records;
- severity/source/category vocabulary;
- diagnostics query interfaces;
- health/status report contracts.

Product adapters own:

- actual checks;
- user-facing remediation;
- product-specific grouping;
- CLI/TUI formatting.

`loushang.harness.diagnostics.types` now owns the shared vocabulary, records,
queries, summaries, and startup-check contracts.
`loushang.harness.diagnostics.service` owns bounded retention, fingerprinting,
deduplication, filtering, aggregation, normalization, and caller-supplied check
execution. Coding retains actual checks, observability mapping, serialization,
remediation, session projection, and UI behavior.

## OEM And Extension Contribution Model

The shared contribution flow should be:

```text
extension/package contributes neutral records
  -> harness validates and normalizes contribution shape
  -> product adapter decides applicability
  -> OEM layer may override activation/policy
  -> product host materializes runtime behavior
```

Harness should not decide that an extension is trusted or that a product should
enable a contributed tool, renderer, resource, or policy rule by default.

`loushang.harness.contributions` owns the current shared descriptor, inventory,
indexing, and duplicate-key contracts. Product adapters construct those records
from their manifests or runtime objects and decide whether a contribution is
applicable. Middleware invocation, observer dispatch, activation, precedence,
and OEM override policy remain outside Harness until their cross-product shape
is proven.
