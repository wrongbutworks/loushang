# Contribution Inventory Migration Plan

## Goal

Move product-neutral contribution descriptors and registry indexing into
Harness while preserving Coding extension projection, public imports, class
identity, ordering, and duplicate-key behavior.

## Tasks

- [x] Define contribution inventory ownership and Coding adapter boundaries.
- [x] Implement `loushang.harness.contributions`.
- [x] Preserve generic and extension-shaped alias identity.
- [x] Reduce Coding contributions to projection and compatibility exports.
- [x] Redirect Coding internal type imports to the Harness owner.
- [x] Add Harness descriptor, registry, and duplicate-key tests.
- [x] Add Coding compatibility and projection identity tests.
- [x] Add architecture owner and documentation tests.
- [x] Update the Harness architecture index and migration inventory.
- [x] Run focused Harness, Coding extension, and architecture tests.
- [x] Run Ruff, diff checks, and the full non-live test suite.

## Validation Record

- Focused Harness, Coding extension, and architecture suite: 113 passed.
- Full non-live suite: 4316 passed, 9 deselected.
- Changed-file Ruff and `git diff --check`: passed.
- Full suite with live tests: one Moonshot authentication failure from an
  invalid environment credential; 4316 passed and 8 skipped otherwise.
- Full-repository Ruff reports 61 pre-existing findings outside the files
  changed by this migration.

## Non-Goals

- Moving `LoadedExtension`, extension manifests, loaders, or policy.
- Moving runtime bindings, command handlers, hooks, or observers.
- Choosing contribution activation, precedence, or OEM override policy.
- Changing descriptor fields, registry ordering, or duplicate-key behavior.
- Adding contribution symbols to top-level `loushang.harness` exports.
