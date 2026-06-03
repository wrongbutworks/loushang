# Loushang Coding Tools Substrate Hardening And Pi-Aligned File Tool Semantics Design

## Goal

Harden `loushang-coding`'s built-in tools by introducing a shared tool substrate and migrating the existing file/search tool family onto it.

This design should:

- keep `ToolDefinition` as the only stable tool protocol
- align core file/search tool semantics with `pi`
- introduce the shared substrate that `pi` already relies on:
  - path normalization
  - truncation
  - file mutation queue
  - shared result/diagnostics helpers where needed
- include `bash` in the same substrate so the built-in family does not drift into two different execution semantics

## Scope

### In Scope

- add shared tool substrate modules inside `src/loushang/coding/tools/`
- migrate the current built-in family to use the shared substrate:
  - `bash`
  - `read`
  - `ls`
  - `find`
  - `grep`
  - `write`
  - `edit`
- upgrade `write` and `edit` toward more mature `pi`-aligned file mutation semantics
- unify path resolution, truncation behavior, mutation serialization, and core success/error behavior across the built-in family

### Out Of Scope

- new permission or sandbox systems
- UI-specific tool rendering
- binary/media editing support
- plugin work
- MCP compatibility redesign
- new mode work

## Why This Comes Next

`loushang-coding` already has the right tool-system spine:

- `ToolDefinition` as the core protocol
- `ToolRegistry`
- `@tool` authoring layer
- `ToolContext`
- strict error semantics via [ARD-002: Coding Tool Error Semantics](/home/dev/workspace/loushang/docs/architecture/coding/ARD-002-coding-tool-error-semantics.md)

It also already has the core built-in tool names:

- `bash`
- `read`
- `ls`
- `find`
- `grep`
- `write`
- `edit`

The gap is no longer "missing tool names." The gap is substrate maturity.

Compared with `pi`, `loushang` still lacks the deeper shared tool substrate that makes those tool names behave like a real product family:

- `path-utils`
- `truncate`
- `file-mutation-queue`
- more mature `write/edit` semantics

Without that layer, the current tool family works, but remains shallower, more duplicated, and more likely to drift.

## Pi Alignment

Relevant `pi` references:

- [path-utils.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/path-utils.ts:1)
- [truncate.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/truncate.ts:1)
- [file-mutation-queue.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/file-mutation-queue.ts:1)
- [read.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/read.ts:1)
- [write.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/write.ts:1)
- [edit.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/tools/edit.ts:1)

This design aligns with `pi` at the substrate and contract level, not as a line-by-line port.

The target alignment is:

- shared path semantics across built-in tools
- shared truncation semantics across built-in tools
- serialized mutation for the same file
- file tool results and failures that feel like one coherent family
- `write/edit` semantics that are closer to `pi`'s mature behavior than to a minimal first draft

## Architecture

### Tool Protocol Stays The Same

`ToolDefinition` remains the only stable runtime protocol.

The substrate work must not create a new parallel tool system.

The intended shape remains:

```text
tool implementation
  -> ToolDefinition
  -> ToolRegistry
  -> materialized AgentTool
  -> agent loop
```

The substrate simply makes that built-in family more coherent and more `pi`-like.

### Substrate Boundary

The shared substrate should live inside `src/loushang/coding/tools/`.

This work should not introduce a global utility layer outside the `tools` boundary.

Recommended substrate modules:

```text
src/loushang/coding/tools/
  path_utils.py
  truncate.py
  file_mutation_queue.py
  result_helpers.py        # only if needed
```

The file-level tool implementations should continue to stay separate:

```text
src/loushang/coding/tools/
  bash.py
  read.py
  ls.py
  find.py
  grep.py
  write.py
  edit.py
```

### Phase Structure

#### Phase 1: Shared Substrate

Add:

- `path_utils`
- `truncate`
- `file_mutation_queue`
- any minimal shared helpers needed for consistent result shaping

Also migrate `bash` onto the shared substrate where it benefits from:

- shared path conventions where relevant
- shared truncation behavior
- shared diagnostics/result normalization helpers where relevant

#### Phase 2: Tool Migration

Migrate:

- `read`
- `ls`
- `find`
- `grep`
- `write`
- `edit`

to depend on the substrate instead of each tool carrying private path/truncation/mutation behavior.

## Shared Substrate Contracts

### 1. Path Utilities

The shared path layer should define one stable path-resolution contract for all built-in tools.

#### Required Behavior

- accept relative paths and resolve them against `ToolContext.cwd`
- accept absolute paths unchanged
- normalize user-facing path spellings into a stable internal absolute path
- keep path policy predictable and centralized

#### Non-Goals

- no new sandbox rules
- no hidden per-tool path restrictions
- no mode-specific path behavior

#### Pi Alignment

This should be semantically close to `pi`'s `resolveToCwd(...)` / `resolveReadPath(...)` path helpers.

`loushang` does not need to copy every macOS-specific edge case immediately, but it should adopt the same centralization principle:

- file tools must not each invent their own path resolution behavior

### 2. Truncation

The shared truncation layer should own output-size policy for built-in tools.

#### Required Behavior

- support head-style truncation for file reads
- support tail-style truncation for shell-like output
- preserve structured truncation metadata
- be reusable by `read`, `grep`, `ls`, and `bash`

#### Pi Alignment

This should align with `pi`'s truncation utilities in spirit:

- the result contains both content and truncation facts
- truncation policy is reusable and centralized

### 3. File Mutation Queue

The shared mutation queue should serialize file mutations targeting the same file.

#### Required Behavior

- mutations to the same canonical file path must execute serially
- mutations to different files may proceed independently
- the queue key must use canonicalized path identity

#### Why It Belongs In Phase 1

`write/edit` reliable semantics will depend on it. This is substrate, not polish.

#### Pi Alignment

This directly follows `pi`'s `file-mutation-queue` idea:

- serialize same-file mutation
- avoid tool-family race conditions

## Tool Family Migration

### `bash`

`bash` already exists and remains special because it relies on `exec` and `policy`.

This design does **not** try to make `bash` identical to the file/search tools.

It **does** require `bash` to share the same family-level substrate where it makes sense:

- truncation
- diagnostics/result consistency
- any path/result helper that is genuinely generic

The goal is one built-in family, not one-off semantics for `bash` and another set for file tools.

### `read`

`read` should move to shared:

- path resolution
- text/binary boundary handling
- head truncation
- structured success metadata

The important contract is:

- successful reads return content plus structured details
- truncation facts are visible
- failures raise, not fake success

### `ls`

`ls` should share:

- path resolution
- result shaping
- truncation where listing output grows large

It should return a consistent structured listing contract rather than a purely ad hoc text dump.

### `find`

`find` should share:

- path resolution
- result shaping
- truncation and listing limits

It should continue to behave like a file-search primitive, not like raw shell passthrough.

### `grep`

`grep` should share:

- path resolution
- truncation
- line result shaping

`grep` especially benefits from centralized truncation so long matches and high-volume output do not each invent their own clipping behavior.

### `write`

`write` should be upgraded toward mature semantics, not left as a minimal helper.

#### Required Behavior

- explicit create/overwrite behavior
- clear handling of missing parent directories vs overwrite conflicts
- mutation serialization through the file mutation queue
- structured result details that explain what happened

#### Error Surface

At minimum, callers should be able to distinguish:

- create success
- overwrite success
- conflict / policy rejection
- invalid path / invalid input
- runtime IO failure

The exact representation can stay inside `AgentToolResult.details` and exceptions, but the semantics must be explicit.

### `edit`

`edit` should move closer to `pi`'s mature semantics, not stop at a lightweight string replace helper.

#### Required Behavior

- path resolution through the shared substrate
- serialized mutation through the file mutation queue
- precise match/replace semantics
- explicit reporting for:
  - no match
  - multi-match ambiguity
  - invalid overlapping edits
  - successful replacement
- diff-aware result details that explain the applied change

#### Scope Guardrail

This design does **not** require inventing a new patch language or a whole new patch subsystem.

It does require `edit` to become a mature structured file-edit tool whose semantics are close to `pi`'s existing file editing expectations.

## Error Semantics

This design continues to follow [ARD-002](/home/dev/workspace/loushang/docs/architecture/coding/ARD-002-coding-tool-error-semantics.md):

- success returns `AgentToolResult`
- failure raises
- tools do not encode failure as pseudo-success text
- `agent_loop` remains the only boundary that turns failures into `ToolResultMessage.is_error=True`

This is especially important while migrating `bash`, `write`, and `edit`.

The substrate may add helpers, but those helpers must not weaken the core failure model.

## Diagnostics

Built-in tools should continue to contribute supplemental diagnostics, but diagnostics must not become a replacement for failure semantics.

The shared substrate may help normalize diagnostics contribution, but:

- primary failure facts still flow through exceptions and `agent_loop`
- diagnostics are supplemental

## Determinism

The hardened tool substrate should improve determinism in two places:

1. path resolution
2. file mutation serialization

The goal is that repeated tool calls with the same logical inputs produce stable path interpretation and stable same-file mutation ordering.

## Implementation Phasing

### Phase 1: Add Shared Substrate

- add `path_utils.py`
- add `truncate.py`
- add `file_mutation_queue.py`
- add minimal shared result helpers if truly needed
- migrate `bash` to shared truncation/result helpers where applicable

### Phase 2: Migrate Current Tools

- migrate `read`
- migrate `ls`
- migrate `find`
- migrate `grep`
- migrate `write`
- migrate `edit`

### Phase 3: Mature File Mutation Semantics

The `write/edit` migration should explicitly finish with:

- clearer success categories
- clearer conflict categories
- diff-aware edit result details
- same-file mutation serialization guaranteed through the queue

## Expected Outcome

After this work:

- `loushang-coding` still has the same built-in tool names
- those tools behave more like one coherent family
- `bash` no longer feels like an unrelated special case
- `write/edit` are materially closer to `pi` semantics
- future tool additions can reuse a stable substrate instead of duplicating path/truncation/mutation logic

That is the intended gain: not just more tools, but a more mature built-in tool platform.
