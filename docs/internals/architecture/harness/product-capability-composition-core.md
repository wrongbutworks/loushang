# Harness Product Capability Composition Core Boundary

## Status

Implementation complete for integration into `lane/harness`.

The core lives under `loushang.harness.capabilities` and is adopted by the
Coding command catalog and controller, prompt assembler and preflight adapter,
and tool controller. The package is deliberately not re-exported from the
top-level `loushang.harness` namespace.

## Purpose

Products need the same mechanics for composing commands, prompts, and tools,
but must keep control of their domain content and policy. This core separates
those concerns:

```text
Harness: describe, resolve, compose, dispatch, diff
Product: contribute content, choose defaults, apply policy, project results
```

Coding is the compatibility adapter. Product-neutral Harness fixtures using
research and design vocabulary provide the independent contract probe; a
second production Product is not required by the neutrality evidence gate.

## Harness Ownership

### Commands

`loushang.harness.capabilities.commands` owns:

- generic command descriptors with opaque source metadata;
- name normalization and slash-command parsing, including the accepted MCP
  marker form;
- aliases, deterministic precedence, conflict reporting, and catalog lookup;
- completion projection from neutral descriptor metadata;
- ordered synchronous and asynchronous dispatch with opaque results.

Harness does not assign semantic precedence to builtin, extension, prompt, or
skill commands. The Product supplies descriptor order and precedence values.
Aliases belong to their primary descriptor: when that descriptor loses its
primary-name conflict, its aliases are inactive too. Active aliases participate
in completion and resolve to the canonical descriptor.

### Prompts

`loushang.harness.capabilities.prompt` owns:

- ordered prompt-section and prepared-prompt records;
- deterministic composition with included and omitted section trace entries;
- injectable argument parsing, placeholder detection, substitution, and
  argument-appending policy;
- the accepted default positional and sliced placeholder expansion mechanism.

The Product supplies every section and therefore controls selection, content,
salience, and order. Harness does not discover prompt resources or author
prompt text.

### Tools

`loushang.harness.capabilities.tools` owns:

- available, allowed, requested, active, and missing-name accounting;
- ordered tool resolution and activation snapshots;
- deterministic activation diffs and revision tracking;
- refresh behavior for additions, removals, reorderings, and same-name
  replacements;
- injected new-tool activation and rebind callbacks.

The coordinator carries opaque tool definitions. It does not materialize Agent
tools, create execution context, rebuild prompts, or emit Product events.

## Product Ownership

Coding and future Product adapters retain:

- concrete builtin, extension, prompt, and skill command definitions;
- command source precedence choices, handlers, routing, diagnostics, and UI;
- system prompt text, prompt-section selection and order, skill XML, resource
  lookup, resource diagnostics, and runtime footer content;
- default tool packs, allowed/default-active policy, Product-tuned tool
  metadata, and extension activation choices;
- Agent tool materialization, `ToolContext` construction, prompt rebuilding,
  audit events, approval/risk policy, and presentation;
- model registry, authentication resolution, settings fields and defaults,
  transcript schema, compaction prompts, artifact semantics, channels, and UI.

These are Product semantics or integration effects, not composition mechanics.

## Coding Compatibility

Accepted Coding imports remain available:

- `coding.commands.slash` re-exports the neutral parser and completion helper;
- `coding.commands.types.SessionCommandDescriptor` remains a real Coding
  adapter class so runtime type checks continue to work;
- `coding.prompt.templates` and `coding.prompt.types` preserve established
  imports while delegating shared behavior;
- Coding controllers inject handlers, policy, materialization, diagnostics,
  and prompt projection into the Harness mechanisms.

The migration must preserve existing command dispatch order, prompt output,
tool activation behavior, and public Coding import paths.

## Import And Validation Rules

- `loushang.harness.capabilities` must not import Product, method, work, TUI,
  AI, provider, or product storage packages.
- Capability symbols must not become top-level Harness exports.
- Harness tests must use Product-neutral fixtures rather than importing Coding.
- Coding behavior tests cover command compatibility, prompt parity, dynamic
  tool registration, allowlists, same-name replacement, and prompt rebinding.
- Architecture import boundaries, Ruff, mypy, and the full non-live repository
  suite remain merge gates.
