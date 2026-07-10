# Workspace Operation Migration Plan

## Goal

Move product-neutral filesystem operation protocols, sync-or-async resolution,
and the local filesystem backend into `loushang.harness.workspace` while
preserving coding public imports, Pi adapters, and concrete tool behavior.

## Tasks

- [ ] Add harness behavior tests for operation result resolution.
- [ ] Add harness behavior tests for the local filesystem backend.
- [ ] Add coding compatibility identity tests for operation protocols.
- [ ] Add compatibility tests for the local backend and default singleton.
- [ ] Move operation protocols and the combined protocol to harness.
- [ ] Move `resolve_operation` and its neutral result type to harness.
- [ ] Move `LocalToolOperations` and `LOCAL_TOOL_OPERATIONS` to harness.
- [ ] Keep normalization, Pi adapters, payload projection, and abort behavior in coding.
- [ ] Redirect coding internal consumers to the harness owners.
- [ ] Add architecture ownership and documentation tests.
- [ ] Update the harness architecture index and migration inventory.
- [ ] Run focused harness, coding tool-operation, and architecture tests.
- [ ] Run Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving concrete read, write, edit, list, find, or grep tools.
- Moving tool cancellation, path resolution, mutation queues, or policy.
- Moving Pi compatibility adapters into harness.
- Renaming accepted coding SDK symbols during the owner move.
- Adding operation symbols to top-level harness exports.
