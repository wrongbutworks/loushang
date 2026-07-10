# Harness Workspace Operation Boundary

## Status

Status: accepted for `lane/harness`.

This document defines product-neutral filesystem operation protocols and the
local filesystem backend as `loushang.harness.workspace` responsibilities.
Coding keeps compatibility adapters, tool cancellation behavior, workspace
policy, and concrete tool behavior.

## Decision

`loushang.harness.workspace.operations` owns:

- `OperationResult` and `resolve_operation` for sync-or-async backend results;
- `ReadOperations`;
- `WriteOperations`;
- `EditOperations`;
- `LsOperations`;
- `FindOperations`;
- `GrepOperations`;
- the combined `ToolOperations` protocol;
- `LocalToolOperations` and `LOCAL_TOOL_OPERATIONS`.

The existing names are retained to preserve the accepted coding SDK surface.
The focused harness module gives them neutral ownership without renaming the
public contracts during the owner move.

The local backend is an unscoped filesystem mechanism. It reads, writes,
creates directories, lists directories, and walks files for paths supplied by
its caller. It does not select an allowed root, resolve a product-relative
path, request approval, or decide whether an operation is safe.

## Coding-Owned Behavior

`loushang.coding.tools.operations` remains a product compatibility adapter. It
keeps all `normalize_*_operations` functions and the following product
behavior:

- `is_operation_aborted` and `raise_if_operation_aborted`;
- all Pi-style operation adapters;
- Pi payload decoding and path projection helpers.

Coding also keeps concrete read, write, edit, list, find, and grep tools; tool
descriptions; path resolution; mutation queues; approval and risk policy; AI
image/content projection; renderers; and user-facing result text.

## Compatibility

Accepted coding paths remain available:

```python
from loushang.coding import ReadOperations
from loushang.coding.tools import LocalToolOperations
from loushang.coding.tools.operations import LOCAL_TOOL_OPERATIONS
```

These paths re-export the same harness-owned protocols, class, and singleton.
Harness-owned classes keep their harness `__module__`; compatibility paths
preserve imports and object identity rather than duplicate implementations.

Coding internal consumers import owner symbols from the focused harness module.
They may continue to import normalization, Pi compatibility, and abort helpers
from `loushang.coding.tools.operations`.

## Dependency Direction

The target direction is:

```text
coding concrete tools / factory / compatibility exports
  -> loushang.harness.workspace.operations
```

The harness module must not import coding, method, work, TUI, AI, provider, or
product packages. No operation symbols are added to top-level
`loushang.harness.__all__`.

## Non-Goals

This migration does not:

- move concrete workspace tools;
- move Pi-style compatibility adapters;
- move tool cancellation or signal semantics;
- move file mutation queueing or path canonicalization;
- define workspace roots, sandbox policy, approval policy, or default tools;
- change sync/async backend behavior or filesystem encoding behavior.

## Validation

The migration must prove:

- sync and async operation results resolve through the harness owner;
- local filesystem reads, writes, directory operations, and walks are unchanged;
- coding public paths preserve class and singleton identity;
- Pi-style and custom operation backends remain compatible;
- `LocalToolOperations` monkeypatch behavior is unchanged;
- coding internal consumers use the harness owner;
- harness import boundaries and top-level export discipline still pass.
