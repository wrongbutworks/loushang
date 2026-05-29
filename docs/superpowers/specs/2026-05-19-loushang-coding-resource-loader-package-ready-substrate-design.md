# Loushang Coding Resource Loader Package-Ready Substrate Design

## Goal

Upgrade `loushang-coding`'s `loader` from a project-local resource discoverer into a package-ready resource substrate.

This design should:

- make `built_in + project_local` sources production-ready now
- reserve stable model slots for future `external/package` sources
- align `loader` semantics with `pi`'s resource plane
- avoid pulling `plugin` or package-manager scope into this iteration

## Scope

### In Scope

- upgrade resource descriptor models to carry stable identity, provenance, scope, enablement, and diagnostics
- introduce a first-class `ResourceSnapshot` representing one atomic loader result
- define source-aware merge, precedence, and conflict handling rules
- make `DefaultResourceLoader.reload_resources()` an atomic snapshot replacement operation
- keep `built_in` and `project_local` as the only implemented source kinds in this iteration
- reserve `external_package` source semantics in the model without implementing package installation or resolution

### Out Of Scope

- `plugin` / package manager implementation
- extension runtime changes
- prompt assembly redesign
- session orchestration changes
- new resource types beyond the current `prompts / skills / extensions / themes / AGENTS.md`
- marketplace, git, registry, or install flows

## Why This Comes Next

`loushang-coding` already has:

- `ExtensionAPI v1`
- `DiagnosticsService`
- `compaction`, `branch summary`, and `retry` session deep behavior
- a functional built-in tool family

The next bottleneck is no longer `session` depth. It is the resource plane.

Today [DefaultResourceLoader](/home/dev/workspace/loushang/src/loushang/coding/loader/default_resource_loader.py:1) still behaves like a project-local scanner:

- find `AGENTS.md`
- find prompt markdown files
- find skill directories
- find extension entry files
- emit a flat `ResourceBundle`

That is enough for local development, but not enough to support:

- stable override rules
- future package/plugin resource integration
- source-aware diagnostics
- reliable reload semantics

This design upgrades the loader substrate without expanding into `plugin`.

## Pi Alignment

This design intentionally aligns with `pi` at the resource-plane level, not by literal source parity.

Relevant `pi` references:

- [resource-loader.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/resource-loader.ts:1)
- [package-manager.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/package-manager.ts:1)

The alignment target is:

- `loader` remains a standalone resource aggregation boundary
- resources are represented as typed descriptors before runtime consumption
- diagnostics are structured output, not side-effect logging
- runtime consumers observe snapshots, not partial in-flight mutation

This iteration does **not** attempt full `pi` package/resource parity. It only makes `loushang` package-ready at the substrate level.

## Architecture

### Loader Position

The intended shape is:

```text
built-in sources
project-local sources
future external/package sources
        -> DefaultResourceLoader
        -> ResourceSnapshot
        -> ResourceBundle (active consumption view)
        -> bootstrap / prompt / extensions / session
```

### Boundary Rule

`DefaultResourceLoader` owns:

- discovery
- parsing
- normalization
- source-aware merge
- atomic snapshot replacement
- resource diagnostics

`DefaultResourceLoader` does **not** own:

- package installation
- extension execution
- prompt rendering
- session lifecycle

## Design Decisions

### 1. Implemented Sources vs Reserved Sources

This iteration fully implements:

- `built_in`
- `project_local`

This iteration reserves model support for:

- `external_package`

Reserved means:

- descriptors can already carry `source_kind="external_package"`
- precedence and scope rules already account for it
- snapshots can represent it

But no package discovery or installation is implemented yet.

### 2. Source Fields Exist Now

All resource descriptors and snapshots should carry:

- `source_kind`: `built_in | project_local | external_package`
- `source_scope`: `builtin | project | package`
- `enabled`

Even though only `built_in` and `project_local` are implemented now, these fields must exist now so later package work does not require re-modeling the loader substrate.

For this iteration, `enabled` should come from descriptor resolution metadata, with a default of `True` for discovered resources unless discovery or future source policy marks them disabled.

Minimal contract for this iteration:

- each descriptor carries a resolved boolean `enabled`
- the boolean is derived by the source adapter during discovery/normalization
- when a source does not provide any enablement metadata, the loader resolves `enabled=True`
- future package-backed sources may populate the same field from package or manifest metadata without changing the descriptor model

Disabled resources should:

- remain present in the full snapshot as candidates
- not appear in the active bundle
- still emit diagnostics when relevant
- still participate in collision reporting so operators can understand why an active candidate was or was not selected

### 3. Reload Uses Atomic Snapshot Replacement

`reload_resources()` must produce a complete new `ResourceSnapshot`.

Consumers should only ever observe:

- the old snapshot
- or the new snapshot

They must never observe:

- a partially refreshed bundle
- category-by-category replacement
- transient mixed-state results

### 4. Conflict Strategy Is Type-Specific

Conflict handling is intentionally different by resource type.

#### `prompts` and `skills`

Use strict precedence:

- only one active descriptor for a given logical identity
- lower-priority collisions are preserved in diagnostics

#### `extensions` and `themes`

Preserve more context:

- retain collision information and non-winning candidates in the snapshot
- still compute only one active descriptor per logical identity
- diagnostics must explain the conflict and winner

This keeps future package/plugin scenarios debuggable without making the active runtime set ambiguous.

### 5. Identity Rules Are Type-Specific

Identity must not be globally path-only.

#### `extensions` and `themes`

Support explicit identifiers now.

Identity resolution order:

1. explicit declared `id`
2. fallback path-derived identity

#### `prompts` and `skills`

Use path-derived identity in this iteration.

These resource kinds do not need inline-id parsing yet.

Path-derived identity must be canonicalized from a stable source-relative path, not from an absolute path spelling or unresolved discovery input.

For this iteration, canonicalization should be:

- relative to the owning source root
- normalized to POSIX-style separator form in identity strings
- based on the logical resource path, not the raw unresolved input string

The goal is stable precedence and diagnostics behavior across reloads and source kinds.

## Resource Model

### Base Descriptor

Each resource descriptor should conceptually carry:

- `id`
- `resource_type`
- `name`
- `source_kind`
- `source_scope`
- `enabled`
- `source_path`
- `diagnostics`
- `metadata`

Resource-specific payload remains per type:

- prompt text
- skill content
- extension entry path
- theme payload

This can be implemented either through a shared base dataclass plus typed variants, or through repeated typed dataclasses that all satisfy the same contract. The important point is semantic consistency, not inheritance style.

### Resource Snapshot

Introduce a first-class `ResourceSnapshot` that represents one resolved loader pass.

It should carry:

- `cwd`
- implemented sources included in the snapshot
- active descriptors by category
- all candidate descriptors by category
- diagnostics
- merge metadata sufficient to explain precedence decisions

`ResourceBundle` remains the active consumption view used by current runtime consumers, but it should now be derived from a snapshot rather than acting as the only loader state object.

Compatibility mapping for current `ResourceBundle` fields:

| `ResourceBundle` field | Derived from `ResourceSnapshot` |
|---|---|
| `cwd` | snapshot `cwd` |
| `agents_path` | active `AGENTS.md` prompt-context descriptor source path |
| `agents_md` | active `AGENTS.md` prompt-context descriptor text |
| `prompt_descriptors` | active prompt-context descriptor + active prompt asset descriptors |
| `prompt_fragments` | active prompt bundle text in deterministic prompt order |
| `skills` | active winning skill descriptors only |
| `extensions` | active winning extension descriptors only |
| `prompts` | active ordinary prompt asset descriptors only |
| `themes` | active winning theme descriptors only |
| `diagnostics` | snapshot diagnostics view |

`ResourceBundle.merge(...)` remains an active-view operation for current extension contribution flow. In this iteration it should continue producing a bundle-shaped active view, while the loader-owned snapshot remains the authoritative discovery result underneath.

### Active View vs Full Snapshot

The loader should distinguish between:

- **full snapshot**
  - all discovered candidates
  - collision context
  - provenance
  - diagnostics

- **active bundle**
  - the final descriptors the runtime should currently consume

This distinction is important because strict runtime consumption and rich diagnostics need different views of the same discovery pass.

## Source Semantics

### Built-In Source

`built_in` is reserved for resources shipped with `loushang-coding` itself.

This source kind should be modeled now even if the first iteration only contributes a small or empty built-in set.

The loader substrate should not assume that "no built-ins exist today" means "no built-in source concept is needed."

For planning purposes, `built_in` should have an explicit loader-owned source root inside `loushang-coding`, with the same logical categories as project-local resources:

- built-in prompt assets
- built-in skills
- built-in themes
- later built-in extension descriptors only if `loushang` chooses to ship them

This spec does not require a large built-in catalog. It requires the built-in source root and discovery contract to exist explicitly so precedence, scope, and diagnostics can already account for it.

For this iteration, the built-in root should be the logical package resource namespace:

```text
src/loushang/coding/resources/
  prompts/
  skills/
  themes/
  extensions/
```

Discovery rules should mirror project-local category discovery where applicable:

- `prompts/*.md`
- `skills/*/SKILL.md`
- `themes/*`
- `extensions/*.py` or `extensions/*/(extension.py|__init__.py)`

It is acceptable for some built-in categories to be empty in the first implementation. The root and discovery contract still need to exist.

Built-in discovery must not rely on repo-relative working-directory assumptions. The planned implementation should resolve built-in resources through package-owned resource loading semantics, concretely using Python package resource lookup for `loushang.coding.resources` as the authoritative built-in source mechanism. In source checkout, a filesystem fallback may be used only as a development/testing implementation detail behind the same package-resource contract.

### Project-Local Source

`project_local` is the currently implemented filesystem source rooted at the current project context.

This includes:

- `AGENTS.md`
- `prompts/`
- `skills/`
- `extensions/`
- later `themes/` when implemented

### `AGENTS.md` Handling

`AGENTS.md` remains a special loader-managed prompt-context resource.

In this design it should be treated as:

- a first-class prompt-context descriptor in the full snapshot
- a contributor to the active prompt bundle
- distinct from ordinary `prompts/*.md` assets

This keeps current behavior intact while still giving `AGENTS.md` explicit provenance, diagnostics, and source-kind metadata.

For this iteration:

- project-local `AGENTS.md` is discovered by upward search from `cwd`
- built-in sources do not define their own `AGENTS.md` equivalent
- `AGENTS.md` therefore does not participate in ordinary prompt collision resolution

It remains a dedicated prompt-context channel with its own descriptor type or a clearly distinguished prompt descriptor flavor.

`AGENTS.md` identity contract for this iteration:

- the active `AGENTS.md` descriptor uses a reserved logical identity such as `project.agents`
- only the nearest discovered upward-search file becomes the active candidate
- shadowed ancestor `AGENTS.md` files are not separate active prompt assets
- if needed, shadowed ancestors may be surfaced as diagnostics/context metadata, but not as competing prompt descriptors

`AGENTS.md` diagnostics contract for this iteration:

- unreadable discovered file -> diagnostic
- invalid parse/normalization -> diagnostic
- no ordinary prompt collision diagnostics, because `AGENTS.md` is outside the ordinary prompt asset merge path

Ordering rule for the active prompt bundle in this iteration:

1. project-local `AGENTS.md` prompt-context descriptor first
2. active built-in prompt assets
3. active project-local prompt assets

Future package prompts should slot between built-in and project-local prompt assets, matching the global precedence order.

Prompt assembly precedence rule for this iteration:

- later prompt fragments in the active prompt bundle have higher effective precedence than earlier ones

That makes the bundle order above deterministic:

- `AGENTS.md` provides the base project prompt context
- built-in prompts layer on top of that
- higher-precedence project-local prompts come last
- future package prompts would sit between built-in and project-local prompts

### Future External/Package Source

`external_package` is reserved for future plugin/package-provided resources.

The loader must be package-ready for this source kind, but the source itself is not implemented in this spec.

## Merge And Precedence

### Precedence Order

The loader should define and centralize precedence now:

```text
project_local > external_package > built_in
```

Because `external_package` is not yet implemented, current behavior will effectively be:

```text
project_local > built_in
```

But the merge layer should already be written to accommodate the full order.

### Collision Handling

The merge layer should:

- compute the winning active descriptor
- preserve losing candidates in the full snapshot
- emit diagnostics describing the collision
- expose enough metadata for later UI/runtime explanation

The merge layer should not:

- silently drop lower-priority candidates
- mutate descriptors in place during merge

When two candidates have the same logical identity and the same precedence level, the winner must still be deterministic.

For this iteration, tie-break order should be:

1. stable source root order inside the same source kind
2. canonicalized source-relative path

That rule is not trying to express semantic preference. It only ensures stable merge results and stable diagnostics.

## Diagnostics

Diagnostics must become a first-class part of the snapshot contract.

The loader should emit diagnostics for:

- unreadable resources
- unsupported entries
- invalid descriptor declarations
- collisions / precedence overrides
- disabled resources

The important rule is:

- diagnostics are structured snapshot data
- not side-effect logging
- not prompt text
- not runtime exceptions unless discovery cannot continue at all

## Queries

The loader should support both current and future-friendly queries.

Current-friendly:

- `get_resource_bundle()`
- `get_skills()`
- `get_prompts()`
- `get_extensions()`

Future-friendly:

- `get_resource_snapshot()`
- `get_diagnostics()`

This spec does not require removing current bundle-style getters. It requires making them views over a more stable snapshot model.

Compatibility contract for this iteration:

| Method | Return Type | Backing Data |
|---|---|---|
| `discover_resources(...)` | `ResourceBundle` | active view derived from the newly committed `ResourceSnapshot` |
| `reload_resources(...)` | `ResourceBundle` | active view derived from the newly committed `ResourceSnapshot` |
| `get_resource_bundle()` | `ResourceBundle` | active view derived from the current committed `ResourceSnapshot` |
| `get_skills()` | skill query view | current committed `ResourceSnapshot` |
| `get_prompts()` | prompt query view | current committed `ResourceSnapshot` |
| `get_extensions()` | extension query view | current committed `ResourceSnapshot` |
| `get_resource_snapshot()` | `ResourceSnapshot` | current committed `ResourceSnapshot` |

This keeps current consumers stable while introducing snapshot semantics underneath.

Current query getters expose the active bundle only:

- `get_prompts()`
- `get_skills()`
- `get_extensions()`

They should return active winning descriptors, not disabled resources or collided losing candidates. Full candidate visibility belongs to `get_resource_snapshot()` and diagnostics/snapshot-specific query surfaces.

## Implementation Phasing

### Phase 1: Model Upgrade

- add source-aware descriptor fields
- add `ResourceSnapshot`
- keep `ResourceBundle` as derived active view

### Phase 2: Merge And Precedence

- centralize precedence
- implement type-specific collision handling
- emit structured collision diagnostics

### Phase 3: Atomic Reload

- replace in-place loader state mutation with atomic snapshot replacement
- ensure queries read from the current committed snapshot only

### Phase 4: Built-In Source Hook

- model built-in source explicitly
- define a concrete built-in source root and discovery contract
- even if initial built-in contribution is small or empty

### Phase 5: Package-Ready Contract

- expose reserved `external_package` source semantics in types and merge logic
- do not yet implement package discovery or install flows

## Non-Goals And Guardrails

- Do not implement `plugin` in this spec.
- Do not implement package installation.
- Do not make `loader` responsible for extension execution.
- Do not collapse `ResourceSnapshot` and `ResourceBundle` back into one flat object.
- Do not make reload incremental or partially visible.

## Expected Outcome

After this work:

- `loader` will still fully support current `project_local` workflows
- runtime consumers will still get a simple active bundle view
- the underlying resource plane will be stable enough to support future `plugin/package` integration without another loader rewrite

That is the intended `pi` alignment for this phase: not full package parity, but a package-ready resource substrate with clear boundaries and atomic semantics.
