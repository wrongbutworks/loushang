# Workspace Operation Migration Plan

## Goal

Move product-neutral filesystem operation protocols, sync-or-async resolution,
and the local filesystem backend into `loushang.harness.workspace` while
preserving coding public imports, Pi adapters, and concrete tool behavior.

## Tasks

- [x] Add harness behavior tests for operation result resolution.
- [x] Add harness behavior tests for the local filesystem backend.
- [x] Add coding compatibility identity tests for operation protocols.
- [x] Add compatibility tests for the local backend and default singleton.
- [x] Move operation protocols and the combined protocol to harness.
- [x] Move `resolve_operation` and its neutral result type to harness.
- [x] Move `LocalToolOperations` and `LOCAL_TOOL_OPERATIONS` to harness.
- [x] Keep normalization, Pi adapters, payload projection, and abort behavior in coding.
- [x] Redirect coding internal consumers to the harness owners.
- [x] Add architecture ownership and documentation tests.
- [x] Update the harness architecture index and migration inventory.
- [x] Run focused harness, coding tool-operation, and architecture tests.
- [x] Run Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving concrete read, write, edit, list, find, or grep tools.
- Moving tool cancellation, path resolution, mutation queues, or policy.
- Moving Pi compatibility adapters into harness.
- Renaming accepted coding SDK symbols during the owner move.
- Adding operation symbols to top-level harness exports.
