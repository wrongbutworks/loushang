# Workspace Path And Mutation Migration Plan

## Goal

Move neutral workspace path resolution and mutation coordination into harness
while preserving coding input policy, public imports, queue identity, and tool
behavior.

## Tasks

- [x] Add harness tests for user expansion and `cwd` resolution.
- [x] Add harness tests for configurable normalizers and path variants.
- [x] Add harness tests for canonical absolute path identity.
- [x] Add coding compatibility tests for `path_utils` behavior.
- [x] Implement `loushang.harness.workspace.paths`.
- [x] Reduce coding `path_utils` to policy and compatibility wrappers.
- [x] Add harness mutation queue concurrency and cleanup tests.
- [x] Move mutation queue ownership to harness.
- [x] Preserve coding snake-case function, registry, and camelCase alias identity.
- [x] Redirect write/edit internal consumers to the harness queue owner.
- [x] Add architecture owner and documentation tests.
- [x] Update the harness architecture index and migration inventory.
- [x] Run focused path, queue, tool, and architecture tests.
- [ ] Run Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving workspace root, sandbox, approval, or mutation policy.
- Moving concrete workspace tools.
- Making coding's `@` syntax a harness default.
- Enabling optional input correction for every product.
- Moving camelCase SDK aliases into harness.
