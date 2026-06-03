# Loushang Coding Resource Loader Phase 2 Precedence And Collision Design

## Goal

Define the second-stage `resource / loader` rules that decide:

- which resource wins when multiple sources provide the same logical resource
- which collisions only produce diagnostics
- which collisions disable only the conflicting resource id
- which resources remain outside the normal named-resource model

This design deepens the existing package-ready loader substrate. It does not introduce `plugin`, methodology runtime behavior, or new package installation flows.

## Why This Comes Next

`loushang-coding` now has:

- snapshot-aware loader models
- source-aware resource descriptors
- atomic resource reload semantics
- deeper session/runtime behavior
- hardened tool substrate

The next bottom-layer gap is no longer "how to discover files." It is "how to resolve conflicts predictably once multiple sources and resource types coexist."

Without stable precedence and collision policy:

- reload can be deterministic but still semantically unclear
- future package/plugin integration will remain fragile
- diagnostics cannot explain why a resource is active or inactive
- new resource families such as future methodologies will have no stable place to attach

## Scope

### In Scope

- source precedence rules across `project_local`, reserved `external_package`, and `built_in`
- type-specific collision policies for:
  - `prompts`
  - `skills`
  - `themes`
  - `extensions`
  - reserved future `methodologies`
- special treatment of `AGENTS.md`
- snapshot-level representation of active winners, losing candidates, and diagnostics
- deterministic tie-breaking rules where `pi` relies on sorted order and `first wins`

### Out Of Scope

- `plugin` implementation
- package installation or resolution logic
- methodology runtime/session behavior
- prompt assembly redesign
- extension runtime redesign
- mode-specific presentation
- new per-resource `priority/order` fields

## Pi Alignment

This phase should align with `pi`'s resource-plane semantics, not invent a new override system.

Relevant `pi` references:

- [package-manager.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/package-manager.ts:123)
- [resource-loader.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/resource-loader.ts:320)
- [resource-loader.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/resource-loader.ts:788)
- [skills.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/skills.ts:413)
- [packages.md](/home/dev/workspace/pi-mono/packages/coding-agent/docs/packages.md:214)
- [skills.md](/home/dev/workspace/pi-mono/packages/coding-agent/docs/skills.md:189)

The key `pi` semantics to preserve are:

- source precedence is centralized
- name-collision resolution for most resources is effectively `first wins`
- losing candidates remain visible through diagnostics
- extensions stay loaded even when their tools or flags conflict

This phase should therefore make `loushang` more explicit, but not more conceptually exotic, than `pi`.

## Architecture Position

The loader should continue to be the authoritative resource arbitration boundary:

```text
sources
  -> discovery / normalization
  -> source precedence ordering
  -> resource-type collision policy
  -> ResourceSnapshot
  -> ResourceBundle active view
```

The loader owns:

- precedence ranking
- candidate ordering
- winner selection
- losing-candidate diagnostics
- active-set derivation

The loader does not own:

- plugin management
- methodology activation
- session phase switching
- prompt rendering
- extension execution

## Source Precedence Model

### Precedence Order

The unified source precedence order is:

1. `project_local`
2. `external_package`
3. `built_in`

This order should exist now even though `external_package` remains reserved rather than implemented.

### Meaning

- `project_local` always has the strongest authority because project code and project-owned resources should override all shared defaults.
- `external_package` sits between project-local and built-in because packages are intentionally added but remain less authoritative than the project itself.
- `built_in` is the lowest-precedence baseline.

### No Per-Resource Priority

This phase should **not** introduce resource-local `priority` or `order` fields.

The arbitration model should stay aligned with `pi`:

- first sort by source precedence
- then apply resource-type policy
- then use stable first-wins tie-breaking where applicable

## Collision Framework

This phase should use a two-layer arbitration model:

1. **Source precedence layer**
   - order candidates by `project_local > external_package > built_in`
2. **Resource-type policy layer**
   - decide how a given resource family resolves same-name collisions

This keeps the main loader pipeline stable while allowing future resource families to attach a new policy without rewriting the loader core.

## Resource-Type Policies

### `prompts`

Policy:

- named resource
- source precedence applies
- first winning candidate becomes active
- losing candidates emit collision diagnostics
- if a same-precedence collision occurs, the conflicting `id` is disabled from the active set
- other prompt ids continue loading normally

Impact scope:

- only the conflicting prompt identity is affected
- the snapshot still succeeds

Rationale:

- prompt identity should be deterministic and debuggable
- prompt collisions should not invalidate unrelated prompts

### `skills`

Policy:

- same as `prompts`
- named resource
- first winner after precedence ordering
- losing candidates produce diagnostics
- same-precedence collisions disable only the conflicting skill identity

Rationale:

- aligns with `pi`'s "first skill found wins" behavior
- keeps collisions local instead of failing the whole resource type

### Future `methodologies`

Policy:

- reserve this family now as a **named resource family**
- do not implement it in this phase
- when introduced later, it should follow the same loader-side collision model as `skills/prompts`

That means:

- methodology is a named resource
- not an `AGENTS.md`-like append-only context file
- collisions should be local to the methodology id

This leaves runtime methodology selection for a future session-level design without polluting the loader now.

### `themes`

Policy:

- named resource
- source precedence applies
- active theme candidate is selected by stable first-wins ordering
- losing candidates remain visible in diagnostics and snapshot candidate sets
- same-precedence collisions do not fail reload

Rationale:

- this matches `pi` more closely than introducing explicit per-theme priority
- themes benefit from deterministic choice plus collision visibility

### `extensions`

Policy:

- align fully with `pi`
- extensions remain loaded even if their tools, commands, or flags conflict
- slot conflicts emit diagnostics
- effective precedence is determined by resolved load order

This means the loader should distinguish:

- **extension resource collision**
  - extension entry identity itself
- **extension slot collision**
  - tool name
  - command name
  - flag name
  - similar extension-owned runtime slots

For this phase:

- extension entries should remain in the active extension set
- conflicting slots should be reported, not silently hidden
- no entire extension should be dropped purely because a slot collides

Rationale:

- this is the closest match to `pi`
- extension packages often contribute overlapping capabilities that still have value outside the conflicting slot

## Same-Precedence Conflict Handling

### `prompts / skills / future methodologies`

When the collision occurs within the same precedence tier:

- only the conflicting resource identity is disabled from the active set
- diagnostics must identify:
  - resource type
  - logical identity
  - winner
  - loser
  - precedence tier
- the rest of the snapshot remains valid

This avoids overly broad fallout while still treating same-tier ambiguity as stricter than ordinary lower-priority override.

### `themes`

When two same-tier themes collide:

- choose the winner via stable deterministic order
- emit collision diagnostics
- preserve both candidates in the snapshot
- expose only the winner in the active bundle

### `extensions`

When two same-tier extensions collide at runtime slots:

- keep both extension descriptors active
- emit slot collision diagnostics
- let runtime resolution continue to follow load order

## Deterministic Tie-Breaking

Where a type policy uses first-wins semantics, the ordering must be deterministic.

Within the same source precedence tier, tie-breaking should use:

1. canonical source root
2. canonical source-relative logical path
3. stable discovery order only as a final fallback when two inputs are otherwise identical

The goal is:

- reload produces the same winner given unchanged inputs
- diagnostics are explainable
- future package-backed sources can participate without changing the rule shape

This is especially important for:

- `themes`
- prompt/skill collisions surfaced only as diagnostics
- extension load order

## `AGENTS.md` Special Status

`AGENTS.md` must remain a **special loader-managed context resource**.

It should not enter the normal named-resource collision model used by:

- prompts
- skills
- themes
- extensions
- future methodologies

That means:

- it is not deduped by resource id/name
- it keeps its dedicated discovery and ordering rules
- it continues to feed prompt-context assembly as a special context layer

Rationale:

- `AGENTS.md` is locality-oriented guidance, not a catalog resource
- treating it like a named prompt would blur an important semantic distinction

## Snapshot And Bundle Semantics

`ResourceSnapshot` should become the authoritative place to represent:

- all candidates
- active winners
- disabled conflicting identities
- diagnostics explaining each arbitration outcome

`ResourceBundle` should remain the active runtime-facing projection.

Bundle getters should expose:

- only active winning resources
- never losing same-name candidates
- never disabled conflicting identities

Those losing or disabled candidates belong in:

- snapshot candidate sets
- collision diagnostics
- snapshot-specific query surfaces

## Diagnostics Requirements

Collision diagnostics should be structured enough to answer:

- what resource type collided
- what logical identity collided
- which candidate won
- which candidate lost
- what source kind each candidate came from
- whether the loser lost because of lower precedence or same-tier ambiguity

For extensions, diagnostics should additionally distinguish:

- extension resource identity
- conflicting runtime slot kind

This phase does not require redesigning the `DiagnosticsService`. It requires loader diagnostics to be explicit enough for future runtime consumers and debugging surfaces.

## Non-Goals

This phase should not:

- invent a separate methodology runtime model
- introduce explicit per-resource ordering knobs
- fold `AGENTS.md` into prompt collision handling
- make extension conflicts fatal
- make reload fail because one resource family has a localized collision

## Result

After this phase:

- loader precedence is explicit and future-package-ready
- collision rules are stable and type-specific
- `pi` alignment is stronger without copying `pi` blindly
- future methodology resources have a clear loader-side home
- `AGENTS.md` remains clearly special

That gives `loushang-coding` a bottom-layer arbitration model strong enough to support later package/plugin work without reopening core loader semantics.
