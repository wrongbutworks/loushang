# Contribution Inventory Migration Plan

## Goal

Move product-neutral contribution descriptors and registry indexing into
Harness while preserving Coding extension projection, public imports, class
identity, ordering, and duplicate-key behavior.

## Tasks

- [ ] Define contribution inventory ownership and Coding adapter boundaries.
- [ ] Implement `loushang.harness.contributions`.
- [ ] Preserve generic and extension-shaped alias identity.
- [ ] Reduce Coding contributions to projection and compatibility exports.
- [ ] Redirect Coding internal type imports to the Harness owner.
- [ ] Add Harness descriptor, registry, and duplicate-key tests.
- [ ] Add Coding compatibility and projection identity tests.
- [ ] Add architecture owner and documentation tests.
- [ ] Update the Harness architecture index and migration inventory.
- [ ] Run focused Harness, Coding extension, and architecture tests.
- [ ] Run Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving `LoadedExtension`, extension manifests, loaders, or policy.
- Moving runtime bindings, command handlers, hooks, or observers.
- Choosing contribution activation, precedence, or OEM override policy.
- Changing descriptor fields, registry ordering, or duplicate-key behavior.
- Adding contribution symbols to top-level `loushang.harness` exports.
