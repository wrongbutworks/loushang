# Loushang Coding ToolDefinition-Centered Tool Authoring Design

## Goal

Define a Python-native tool authoring surface for `loushang-coding` that improves ergonomics without changing the core tool architecture.

The design target is:

- keep `ToolDefinition` as the single core tool protocol
- align with `pi`'s definition-first semantics
- add `@tool` as an authoring convenience layer, not a second tool system
- support richer parameter shapes from day one:
  - `TypedDict`
  - `dataclass`
  - `Pydantic` models as an optional integration
- support a small injected `ToolContext`
- allow decorated tools to return either plain Python values or explicit `AgentToolResult`

This design does not try to implement the core read/write tool family yet. It defines the authoring layer that those tools should be built on.

## Why This Comes Next

`loushang-coding` now has a stronger runtime spine:

- extension runner and extension API
- compaction, branch summary, retry, diagnostics
- definition-first tool registry
- tool diagnostics and runtime diagnostics snapshots

The next highest-leverage usability step is to make tool authoring much easier without weakening the current runtime model.

If the project jumps straight to `read / grep / find / ls / write / edit` using only handwritten `ToolDefinition(...)`, it will improve capability but miss the opportunity to stabilize the long-term authoring surface first.

This design therefore treats `@tool` as a platform-enabling layer rather than a cosmetic feature.

## Alignment With Pi

This design aims to align with the following `pi` semantics:

- tool definitions are the stable system boundary
- authoring ergonomics should not replace the core tool protocol
- registries, extension systems, diagnostics, and prompt assembly should continue to operate on normalized tool definitions

The goal is not a literal port of a Python SDK decorator. The goal is semantic alignment:

- author-facing sugar may exist
- core runtime still consumes stable tool definitions
- tool execution, interception, diagnostics, and prompt wiring remain definition-first

## Design Principles

### `ToolDefinition` Stays Core

`ToolDefinition` remains the only core tool protocol recognized by:

- `ToolRegistry`
- `ExtensionAPI`
- prompt assembly
- diagnostics and tool interception surfaces
- future plugin-packaged tools

Everything else compiles or normalizes into `ToolDefinition`.

### `@tool` Is Supplemental

`@tool` is an authoring surface. It is not a new runtime object model.

It should make tools easier to declare, but it should not become a second execution protocol that the rest of the system has to understand.

### Normalization Happens Early

Any user-facing authoring shape should be normalized into `ToolDefinition` as early as possible.

That means:

- `ToolRegistry.register_tool(...)`
- `ExtensionAPI.register_tool(...)`

should both accept a small set of authoring inputs, then immediately convert them into `ToolDefinition`.

### Rich Schemas Should Be Supported, But Conservatively

`v1` should support richer Python parameter shapes, but the inference layer must remain explicit and testable.

This means:

- inference should live in dedicated helpers
- overrides should be allowed
- unsupported type shapes should fail clearly rather than silently generating misleading schemas

## Architecture

### Core Layers

The tool subsystem should be understood as three layers:

#### `ToolDefinition`

The stable system protocol.

It remains the model consumed by:

- registry
- extensions
- prompt integration
- diagnostics-producing execution wrappers

#### `DecoratedToolSpec`

The authoring-time intermediate representation produced by `@tool`.

It stores:

- the original Python callable
- decorator metadata overrides
- inferred schema hints
- context injection metadata
- return normalization metadata

It is not a runtime execution object and should not become a core dependency of the wider tool system.

#### Materialized Runtime Tool

The existing wrapper/materialization layer remains the runtime-facing bridge to `AgentTool`.

This means the current runtime execution flow stays structurally unchanged:

```text
authoring surface -> ToolDefinition -> wrapped runtime tool -> agent/tool execution
```

## Normalization Contract

### `tool_to_definition(...)`

Introduce a single normalization/compilation entrypoint:

```python
tool_to_definition(obj) -> ToolDefinition
```

`tool_to_definition(...)` should accept:

- `ToolDefinition`
- `DecoratedToolSpec`
- existing `AgentTool`

The return value should always be `ToolDefinition`.

This becomes the authoritative conversion point for all tool authoring forms.

### Registry Integration

`ToolRegistry.register_tool(...)` should accept the same supported authoring forms and immediately normalize them through `tool_to_definition(...)`.

This preserves the current definition-first behavior while improving ergonomics.

### Extension Integration

`ExtensionAPI.register_tool(...)` should follow the same rule:

- accept `ToolDefinition` or supported authoring inputs
- immediately normalize to `ToolDefinition`
- store only normalized definitions in the loaded extension

This keeps extension runtime semantics aligned with the rest of the system.

## `@tool` Decorator

### Purpose

The decorator should exist to make tool declaration concise and readable, while still targeting the `ToolDefinition` protocol.

### Metadata Surface

`@tool(...)` should support the following optional overrides:

- `name`
- `description`
- `label`
- `prompt_snippet`
- `prompt_guidelines`
- `schema_overrides`

These are optional. The default path should remain lightweight:

- infer name from the function
- infer description from the docstring
- infer schema from annotations

### What `@tool` Does Not Do

`@tool` should not:

- register the tool
- execute the tool
- make tool interception decisions
- directly control diagnostics behavior
- mutate session internals

It is a declaration layer only.

## `ToolContext`

### Purpose

`v1` should support a small, explicit injected runtime context for decorated tools.

This allows tools to access stable runtime facts without binding the tool surface to `AgentSession`.

### Boundary

`ToolContext` should be intentionally small and read-mostly.

Recommended initial contents:

- `tool_call_id`
- `cwd`
- `diagnostics`

Optional future additions may include more read-only runtime metadata, but `v1` should not expose raw session internals.

### Injection Rules

`ToolContext` should be supported as a typed, explicit function parameter.

Rules:

- at most one `ToolContext` parameter per tool function
- recognize it by type, not by parameter name
- do not expose `AgentSession` in `v1`

This gives decorated tools a controlled escape hatch without collapsing architecture boundaries.

## Schema Inference

### Dedicated Inference Layer

Schema inference should live in dedicated helper functions rather than inside the decorator implementation itself.

Recommended helper split:

- `infer_schema_from_signature(...)`
- `infer_schema_from_type(...)`
- `apply_schema_overrides(...)`

### Supported Shapes

`v1` should support:

- scalar parameters
- optional parameters
- common list forms such as `list[str]`
- `TypedDict`
- `dataclass`
- `Pydantic` models when `pydantic` is installed

### Pydantic Policy

`Pydantic` should be an optional integration.

That means:

- no hard dependency in `loushang-coding`
- when available, use it for schema inference
- when unavailable, decorator functionality should still work for non-Pydantic tool signatures

### Failure Policy

When inference cannot safely generate a schema, the system should fail clearly and early.

`v1` should prefer explicit failure over silently generating a misleading schema.

## Return Normalization

### Supported Return Styles

Decorated tools should support two execution styles:

- return `AgentToolResult`
- return plain Python values

Plain Python return values are the recommended authoring path, but explicit `AgentToolResult` remains fully supported.

### Normalization Rules

`v1` should normalize these conservatively:

- `AgentToolResult` -> use as-is
- `str` -> text result
- `dict`, `list`, `int`, `float`, `bool` -> normalized into a reasonable tool result representation
- `None` -> empty result

Exceptions should continue to propagate upward.

Diagnostics, retry, or other execution-layer policies should remain the responsibility of the existing tool execution chain, not the decorator itself.

## Interaction With Diagnostics

The diagnostics model already lives in the execution chain.

This should remain true after introducing `@tool`:

- authoring sugar does not own diagnostics
- tool execution wrappers continue to emit tool diagnostics
- normalized decorated tools should participate in the same diagnostics path as handwritten `ToolDefinition` tools

This is another reason to normalize decorated tools into the core definition model rather than inventing a parallel runtime path.

## Recommended V1 Scope

### In Scope

- `DecoratedToolSpec`
- `tool_to_definition(...)`
- `@tool(...)`
- `ToolContext`
- dedicated schema inference helpers
- support for richer structured parameter types
- return normalization
- `ToolRegistry.register_tool(...)` support for decorated tools
- `ExtensionAPI.register_tool(...)` support for decorated tools

### Out Of Scope

- streaming tool results
- tool-local state mutation APIs
- direct session injection
- tool classes or multi-method tool frameworks
- plugin packaging
- the actual read/write tool family implementation

## Rejected Designs

### `@tool` As A New Runtime Tool Model

Rejected because it would create a second tool system and pull runtime semantics toward Python decorator behavior instead of stable tool definitions.

### Minimal `@tool` With Only Name And Description

Rejected because it would force any non-trivial tool back into handwritten `ToolDefinition(...)`, producing a split mental model almost immediately.

### Hard Dependency On `Pydantic`

Rejected because it would over-couple the core coding package to one schema ecosystem when optional integration is sufficient for `v1`.

## Implementation Order

Implementation should proceed in this order:

1. `tool_to_definition(...)`
2. `DecoratedToolSpec`
3. `@tool`
4. schema inference helpers
5. `ToolRegistry.register_tool(...)` normalization
6. `ExtensionAPI.register_tool(...)` normalization
7. build `read / grep / find / ls` on top of the new authoring surface

This order keeps the protocol stable first, then improves authoring, then applies the new surface to the first high-value tool family.

## Success Criteria

This design is successful when:

- `ToolDefinition` remains the only core tool protocol
- decorated tools and handwritten tool definitions behave identically after normalization
- `ToolRegistry` and `ExtensionAPI` both remain definition-first
- richer structured parameter types are supported without a hard `Pydantic` dependency
- the next core tools can be built using the new authoring surface instead of raw handwritten definitions
