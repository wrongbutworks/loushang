# Harness Workspace Path And Mutation Boundary

## Status

Status: accepted for `lane/harness`.

This document defines product-neutral workspace path resolution, canonical path
identity, optional user-input compatibility helpers, and per-path mutation
coordination as `loushang.harness.workspace` responsibilities. Coding keeps its
tool input syntax, default correction policy, and SDK compatibility aliases.

## Path Engine Decision

`loushang.harness.workspace.paths` owns:

- `PathNormalizer` and `PathVariantProvider` contracts;
- `expand_user_path` for current-user `~` expansion;
- `resolve_path_from_cwd` for caller-supplied relative path resolution;
- `resolve_workspace_path` as the configurable resolution engine;
- `canonicalize_workspace_path` for stable absolute path identity;
- `normalize_unicode_spaces` as an opt-in input normalizer;
- `user_input_path_variants` as an opt-in provider for macOS screenshot spacing,
  Unicode NFD, curly quote, and combined variants.

The engine does not enable product syntax or correction policy by itself.
Callers select normalizers and variant providers. The normalized candidate is
tried first; optional variants are checked only when that candidate does not
exist.

Tilde expansion and caller-supplied `cwd` resolution are mechanisms. They do
not grant filesystem access or choose an allowed workspace root. Product policy
must validate the resolved path before a protected operation executes.

## Coding Path Adapter

`loushang.coding.tools.path_utils` remains the coding path policy adapter and
accepted public import location. It keeps:

- the Pi/coding `@` reference prefix;
- coding's decision to enable Unicode-space normalization and user-input path
  variants by default;
- `expand_path`, `resolve_to_cwd`, `resolve_tool_path`, and `resolve_read_path`;
- Pi-style camelCase aliases.

The adapter delegates path expansion, relative resolution, candidate lookup,
and canonicalization to harness. Existing coding behavior and error text remain
unchanged.

## Mutation Queue Decision

`loushang.harness.workspace.mutation_queue` owns:

- `with_file_mutation_queue`;
- `run_with_file_mutation_queue`;
- the canonical-path lock registry and cleanup mechanics.

The queue uses `canonicalize_workspace_path` and
`loushang.harness.workspace.operations.resolve_operation`. It serializes work
for one canonical absolute path while allowing different paths to progress
independently. It does not decide which operations require serialization or
whether a mutation is allowed.

## Compatibility

Accepted coding paths remain available:

```python
from loushang.coding import withFileMutationQueue
from loushang.coding.tools import with_file_mutation_queue
from loushang.coding.tools.path_utils import resolve_tool_path
```

Coding mutation queue paths re-export the same harness-owned snake-case
functions and lock registry. The camelCase alias remains coding-owned and
points to the harness-owned runner. Coding path functions remain thin policy
wrappers because their default behavior includes coding input semantics.

## Dependency Direction

The target direction is:

```text
coding path policy / concrete write and edit tools
  -> loushang.harness.workspace.paths
  -> loushang.harness.workspace.mutation_queue
  -> loushang.harness.workspace.operations
```

Harness path and mutation modules must not import coding, method, work, TUI,
AI, provider, or product packages. No path or mutation symbols are added to
top-level `loushang.harness.__all__`.

## Non-Goals

This migration does not:

- define workspace roots, sandbox permissions, approval, or mutation policy;
- move concrete read, write, edit, list, find, or grep tools;
- make the `@` prefix a harness default;
- make Unicode or platform correction helpers mandatory;
- move Pi-style aliases into harness;
- change coding path resolution order, queue concurrency, or cleanup behavior.

## Validation

The migration must prove:

- current-user expansion and caller-supplied `cwd` resolution;
- configurable normalizer and variant-provider ordering;
- stable absolute canonical identity and relative-path rejection;
- all coding path compatibility behaviors remain unchanged;
- same-path serialization, different-path concurrency, and failure cleanup;
- coding queue imports preserve function and registry identity;
- write/edit monkeypatch behavior remains unchanged;
- harness import boundaries and top-level export discipline still pass.
