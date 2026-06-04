# Loushang Coding Built-in Tool Family Expansion Design

## Goal

Define the next built-in tool family for `loushang-coding` so the runtime moves beyond `bash` and starts to look like a real coding agent product layer.

The design target is:

- align the built-in tool surface with `pi`'s core coding tool family
- keep `ToolDefinition` as the only stable runtime tool protocol
- keep tool failure semantics aligned with [ARD-002: Loushang Coding Tool Error Semantics](/home/dev/workspace/loushang/docs/architecture/coding/ARD-002-coding-tool-error-semantics.md)
- stage delivery so read-only tools land before file-mutation tools

This design covers the built-in tools themselves. It does not redesign the core authoring surface, which is covered by [Loushang Coding ToolDefinition-Centered Tool Authoring Design](/home/dev/workspace/loushang/docs/superpowers/specs/2026-05-18-loushang-coding-tool-definition-centered-tool-authoring-design.md).

## Why This Comes Next

`loushang-coding` already has:

- a definition-first tool registry
- a runtime/session spine
- diagnostics, retry, compaction, and extension hooks
- a new tool authoring direction centered on `ToolDefinition`

The biggest remaining product gap is not another internal runtime primitive. It is the missing built-in tool family.

Right now the built-in surface is still essentially `bash`-only. That keeps the runtime flexible, but it does not yet provide the narrow, high-signal file and search primitives that a coding agent should prefer over raw shell usage.

The next step should therefore be:

- add the `pi`-aligned file/search tools
- keep them definition-first
- keep their failure semantics strict
- avoid prematurely introducing a large helper or sandbox subsystem

## Scope

### In Scope

The target tool family is:

- `read`
- `ls`
- `find`
- `grep`
- `write`
- `edit`

This aligns `loushang-coding` with `pi`'s core built-in coding tools:

- `read`
- `bash`
- `edit`
- `write`
- `grep`
- `find`
- `ls`

### Phased Delivery

To reduce coupling and keep the first increment stable, delivery should be split into two phases.

#### Phase 1: Read-only tools

- `read`
- `ls`
- `find`
- `grep`

These have simpler semantics, weaker coupling to future mutation safety features, and lower rollback cost.

#### Phase 2: Mutation tools

- `write`
- `edit`

These should follow once the authoring layer and error semantics are stable, because they need tighter guarantees around overwrite behavior, edit matching, and failure reporting.

### Out Of Scope

This design does not introduce:

- a new tool-specific path sandbox
- a new approval or permission engine
- binary/media editing support
- line-oriented patch tools beyond `edit`
- MCP tool compatibility changes
- UI-specific rendering behavior

## Design Principles

### `ToolDefinition` Remains Core

All built-in tools should continue to normalize into `ToolDefinition`.

The wider runtime should not need to understand whether a built-in tool was authored via:

- a handwritten `ToolDefinition`
- a `@tool`-decorated Python function
- a transitional helper during rollout

The stable system boundary remains `ToolDefinition`.

### Keep `builtins.py` Thin

`builtins.py` should stop accumulating tool implementation logic.

Its long-term role should be:

- import each built-in tool definition factory
- register them with the registry
- define the default built-in tool family

Actual tool behavior should live in tool-specific modules.

### One Tool, One File

Each built-in tool should have its own module so semantics remain easy to understand and evolve independently.

Recommended layout:

```text
src/loushang/coding/tools/
  __init__.py
  builtins.py
  bash.py
  read.py
  ls.py
  find.py
  grep.py
  write.py
  edit.py
```

If shared logic genuinely emerges later, it should stay inside the `tools/` boundary first, for example:

```text
src/loushang/coding/tools/
  file_ops.py
```

This should only happen after duplication is proven. Do not pre-emptively move tool-domain logic into `utils/`.

### Align With `pi` At The Contract Level

The goal is not a line-by-line port of `pi`. The goal is interface and behavior alignment.

That means:

- same tool names
- very similar parameter shapes
- very similar success vs error semantics
- read/search tools preferred over forcing the model through `bash`

### Error Semantics Stay Strict

Built-in tools must follow [ARD-002](/home/dev/workspace/loushang/docs/architecture/coding/ARD-002-coding-tool-error-semantics.md):

- success returns `AgentToolResult`
- failure raises
- the tool itself must not encode failure as a fake successful text payload
- `agent_loop` remains the sole boundary that turns tool failure into `ToolResultMessage.is_error=True`

This is especially important during migration from the current `bash` implementation, which still contains pseudo-success error paths.

## Architecture

### Authoring And Materialization Path

Built-in tools should sit on top of the same authoring/materialization path as future extension-defined tools:

```text
built-in tool implementation
  -> ToolDefinition
  -> ToolRegistry
  -> materialized AgentTool
  -> agent_loop execution
```

If the `@tool` authoring layer is present, built-ins should use it when it makes the implementation smaller and clearer. If that layer is still landing in parallel, built-ins may temporarily use handwritten `ToolDefinition(...)`, but they should still target the same final contract.

### Registration Boundary

`ToolRegistry` remains the source of truth for built-in tool definitions.

`AgentSession` remains the owner of:

- which tools are active for the current run
- how tool events are projected into diagnostics/session state

The built-in tool family should not bypass this layering.

### Shared Context

Built-in tools should use the same small `ToolContext` described in the tool authoring design.

Initial runtime facts a built-in tool may rely on:

- `tool_call_id`
- `cwd`
- `diagnostics`

Built-ins should not require direct access to `AgentSession`.

## Path And Filesystem Semantics

### Path Resolution

All file-oriented built-in tools should accept user-facing `path` values as either:

- relative paths, resolved against `ToolContext.cwd`
- absolute paths

Tool implementations should normalize these to an absolute path internally and include the normalized path in `details` when useful.

### Path Policy

This design does not introduce a new path sandbox or approval model.

`v1` should therefore:

- resolve paths predictably against `cwd`
- fail clearly on nonexistent or invalid paths
- avoid inventing hidden path restrictions inside individual tools

If a future policy layer adds path restrictions, those restrictions should be enforced consistently above or beside tool implementations, not as ad hoc per-tool rules.

### Text-first Scope

`read`, `write`, and `edit` are text-first in this design.

`v1` does not promise:

- image decoding
- binary diffing
- media transformation

Binary or obviously non-text payloads may return a clear unsupported error rather than a lossy representation.

## Tool Contracts

### Common Rules

All six tools should follow the same execution contract:

- validate arguments early
- return `AgentToolResult` on success
- raise typed exceptions on failure
- use `details` for structured success metadata
- never return an error-shaped text payload as a successful result

Common exception categories should follow `ARD-002`:

- validation errors
- permission/policy errors
- runtime execution errors

### `read`

#### Purpose

Read a text file, optionally slicing by line window.

#### Proposed Schema

```python
{
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "offset": {"type": "integer", "minimum": 1},
        "limit": {"type": "integer", "minimum": 1},
    },
    "required": ["path"],
    "additionalProperties": False,
}
```

#### Result Shape

`content` should contain the requested file text.

`details` should include minimal structured metadata such as:

- `path`
- `start_line`
- `end_line`
- `truncated`

#### Non-error Outcomes

These should not raise:

- file successfully read but truncated to the requested slice
- short or empty text files

### `ls`

#### Purpose

List directory entries in a compact, model-friendly format.

#### Proposed Schema

```python
{
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": False,
}
```

#### Result Shape

`content` should contain a line-oriented directory listing.

Directories should be visually distinct, for example with a trailing `/`.

`details` should include minimal metadata such as:

- `path`
- `truncated`
- `entry_limit_reached`

#### Non-error Outcomes

These should not raise:

- empty directory
- directory list truncated by `limit`

### `find`

#### Purpose

Find file paths below a directory root using a simple pattern search.

#### Proposed Schema

```python
{
    "type": "object",
    "properties": {
        "pattern": {"type": "string"},
        "path": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1},
    },
    "required": ["pattern"],
    "additionalProperties": False,
}
```

#### Result Shape

`content` should contain one matching path per line.

`details` should include:

- `path`
- `truncated`
- `result_limit_reached`

#### Non-error Outcomes

These should not raise:

- no files found
- result list truncated by `limit`

### `grep`

#### Purpose

Search text file contents by pattern, preferably using a fast local engine such as `rg` when available.

#### Proposed Schema

To stay close to `pi`, `ignoreCase` should remain camelCase.

```python
{
    "type": "object",
    "properties": {
        "pattern": {"type": "string"},
        "path": {"type": "string"},
        "glob": {"type": "string"},
        "ignoreCase": {"type": "boolean"},
        "literal": {"type": "boolean"},
        "context": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1},
    },
    "required": ["pattern"],
    "additionalProperties": False,
}
```

#### Result Shape

`content` should contain line-oriented matches in a stable, model-friendly format, for example:

```text
path/to/file.py:42:def create_agent_session(...):
```

`details` should include:

- `path`
- `truncated`
- `match_limit_reached`

#### Non-error Outcomes

These should not raise:

- no matches found
- match list truncated by `limit`

### `write`

#### Purpose

Replace the contents of a file with the provided text.

#### Proposed Schema

```python
{
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}
```

#### Result Shape

`content` should be a short success message.

`details` should include at least:

- `path`
- `bytes_written`

#### Error Outcomes

These should raise:

- invalid path
- write failure
- unsupported content or encoding problems

Overwriting an existing file should be a normal success path unless a future policy layer says otherwise.

### `edit`

#### Purpose

Apply one or more exact text replacements inside a file.

#### Proposed Schema

To stay aligned with `pi`, `oldText` and `newText` remain camelCase.

```python
{
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "oldText": {"type": "string"},
                    "newText": {"type": "string"},
                },
                "required": ["oldText", "newText"],
                "additionalProperties": False,
            },
            "minItems": 1,
        },
    },
    "required": ["path", "edits"],
    "additionalProperties": False,
}
```

#### Result Shape

`content` should be a short success summary.

`details` should include:

- `path`
- `applied_edit_count`
- `diff`

#### Error Outcomes

These should raise:

- no edit matched
- an edit matched more than once when the contract expects uniqueness
- edits overlap or conflict
- file read/write failure

## Result And Error Semantics

### Success Path

Successful tool calls should use `AgentToolResult` exactly as the common tool protocol expects.

The main text should go in `content`.

Stable structured metadata should go in `details`.

### Failure Path

Built-in tools should raise typed exceptions rather than constructing pseudo-success responses.

The failure normalization path should therefore be:

```text
tool raises
  -> agent_loop normalizes to ErrorInfo-backed error result
  -> ToolResultMessage.is_error=True
  -> AgentSession projects diagnostics from the event/result
```

### Non-error Empty Results

The following outcomes are valid successes, not failures:

- `find` finds nothing
- `grep` matches nothing
- `ls` lists an empty directory
- `read` returns an empty file

These should produce explicit text in `content`, not an exception.

## Diagnostics And Observability

Built-in tools should not become the primary owner of diagnostics recording.

The authoritative failure fact remains:

- the raised exception
- the normalized `ErrorInfo`
- the resulting `tool_execution_end` event

`ToolContext.diagnostics` may be used for supplemental warning or informational records, but not as the sole place where tool failure is reported.

This keeps built-in tool behavior aligned with `ARD-002` and avoids the current ambiguity where a tool can emit diagnostics yet still appear successful.

## Testing Strategy

The expanded built-in tool family should be covered at three levels.

### 1. Tool unit tests

Each tool module should have focused tests for:

- schema shape
- happy-path execution
- obvious validation failure
- strict error propagation

### 2. Registry/materialization tests

Tests should prove that each built-in tool:

- normalizes into `ToolDefinition`
- materializes into an executable runtime tool
- keeps its parameter schema stable

### 3. Agent/runtime integration tests

Tests should prove that:

- successful built-in tool execution produces normal tool results
- failing built-in tools become `is_error=True`
- failures are not silently converted into successful text payloads

## Rollout Plan

### Step 1: Reshape the built-in tool boundary

- move `bash` implementation out of `builtins.py`
- make `builtins.py` registration-only

### Step 2: Add read-only tools

- `read`
- `ls`
- `find`
- `grep`

### Step 3: Let the read-only tool family stabilize

Confirm:

- schema ergonomics
- result formatting quality
- error propagation
- registry/materialization behavior

### Step 4: Add mutation tools

- `write`
- `edit`

Only after the read-only tool family and the new authoring layer are stable enough that mutation semantics are unlikely to churn immediately.

## Open Questions

These questions do not block the spec, but they should be revisited during implementation planning:

- should `grep` always prefer `rg`, or should there be a pure-Python fallback contract in tests
- how strict should `edit` uniqueness matching be in `v1`
- should mutation tools later route through a shared `file_ops.py` helper once duplication appears
- whether a future policy spec should add path-level restrictions above the tool layer

## Recommended Next Step

Write the implementation plan for Phase 1 only:

- `read`
- `ls`
- `find`
- `grep`

That keeps the next execution slice small while preserving a complete design target for the full built-in tool family.
