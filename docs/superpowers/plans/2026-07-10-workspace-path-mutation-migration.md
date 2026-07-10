# Workspace Path And Mutation Migration Plan

## Goal

Move neutral workspace path resolution and mutation coordination into harness
while preserving coding input policy, public imports, queue identity, and tool
behavior.

## Tasks

- [ ] Add harness tests for user expansion and `cwd` resolution.
- [ ] Add harness tests for configurable normalizers and path variants.
- [ ] Add harness tests for canonical absolute path identity.
- [ ] Add coding compatibility tests for `path_utils` behavior.
- [ ] Implement `loushang.harness.workspace.paths`.
- [ ] Reduce coding `path_utils` to policy and compatibility wrappers.
- [ ] Add harness mutation queue concurrency and cleanup tests.
- [ ] Move mutation queue ownership to harness.
- [ ] Preserve coding snake-case function, registry, and camelCase alias identity.
- [ ] Redirect write/edit internal consumers to the harness queue owner.
- [ ] Add architecture owner and documentation tests.
- [ ] Update the harness architecture index and migration inventory.
- [ ] Run focused path, queue, tool, and architecture tests.
- [ ] Run Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving workspace root, sandbox, approval, or mutation policy.
- Moving concrete workspace tools.
- Making coding's `@` syntax a harness default.
- Enabling optional input correction for every product.
- Moving camelCase SDK aliases into harness.
