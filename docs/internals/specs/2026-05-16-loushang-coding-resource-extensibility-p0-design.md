# Loushang Coding Resource And Extensibility P0 Design

## Goal

Define the first platform-focused P0 for `loushang-coding` before expanding tool families or deeper session behaviors.

This P0 exists to improve:

- architecture flexibility
- extensibility
- alignment with `pi-coding-agent`
- future usability without premature rework

The core decision is:

```text
loader/resource hub -> extension runner -> control/settings surface
```

This P0 does not try to make `loushang-coding` feature-complete. It creates the stable substrate that later tooling, compaction, retry, diagnostics, and richer SDK surfaces will build on.

## Scope

### In Scope

- expand `ResourceBundle` into a real resource aggregation object
- evolve `DefaultResourceLoader` from `AGENTS.md` discovery to resource discovery + normalization + caching
- introduce a minimal `ExtensionRunner` subsystem
- expand `ControlConfig` and `SettingsManager` to carry stable configuration slices needed by later subsystems
- keep all three boundaries mode-neutral
- add focused tests for resource discovery, extension lifecycle, and settings propagation

### Out Of Scope

- new mode work
- interactive UI context for extensions
- extension command palette, keybindings, widgets, or TUI integration
- full `pi` extension API surface
- core tool family expansion (`read/grep/find/ls/write/edit`)
- compaction orchestration
- auto-retry orchestration
- diagnostics service implementation

## Why This Comes First

`loushang-coding` already has the runtime spine:

- `AgentSession`
- `SessionManager`
- `AgentSessionRuntime`
- entry family / event family / prompt assembly / basic tool registry

But it is still thin where `pi-coding-agent` becomes a product platform:

- resource discovery
- extension binding
- stable control/config slices

If tool families are expanded first, the project becomes more usable, but the architecture remains shallow and later feature work is more likely to be restructured. This P0 instead prioritizes substrate.

## Alignment With Pi

This design aims to align with these `pi` subsystems:

- `DefaultResourceLoader`
- `ExtensionRunner`
- `SettingsManager`

Relevant references:

- [resource-loader.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/resource-loader.ts)
- [extensions/runner.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/extensions/runner.ts)
- [extensions/types.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/extensions/types.ts)
- [settings-manager.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/settings-manager.ts)

The target is not a literal port. The target is semantic alignment:

- `loader` remains the resource hub
- `ExtensionRunner` remains the execution-side extension coordinator
- `control` remains the aggregate configuration boundary

## Bootstrap Model

This P0 uses explicit two-phase discovery.

### Phase 1: Static Loader Discovery

`DefaultResourceLoader.discover_resources(cwd)` performs only static discovery and normalization:

- `AGENTS.md`
- local prompt fragments
- local skill descriptors
- local extension descriptors
- loader diagnostics

The output of this phase is enough to construct the first `ResourceBundle` and, if needed, an `ExtensionRunner`.

### Phase 2: Extension-Contributed Discovery

After static discovery, bootstrap may construct an `ExtensionRunner` from the discovered extension descriptors. The runner may emit `resources_discover` and contribute additional resource descriptors.

Those contributed descriptors are merged back into the original `ResourceBundle` to produce the final bundle used by prompt assembly and session construction.

### Boundary Rule

- `loader` does not depend on `ExtensionRunner`
- `ExtensionRunner` does not replace `loader`
- `bootstrap` owns the two-phase sequencing
- `AgentSession` consumes the final merged bundle

## Architecture

### Backbone Position

This P0 should reinforce the following shape:

```text
Bootstrap
  -> DefaultResourceLoader
  -> SettingsManager / ModelRegistry

AgentSession
  -> DefaultResourceLoader
  -> ExtensionRunner
  -> ToolRegistry
  -> PromptAssembler
```

Constraints:

- `AgentSession` remains the business center
- `DefaultResourceLoader` remains the resource hub
- `ExtensionRunner` is a collaborator, not a replacement center
- `SettingsManager` remains mode-neutral and session-neutral

### Responsibility Split

#### `DefaultResourceLoader`

Owns:

- resource discovery
- resource normalization
- lightweight resource diagnostics
- resource caching / reload

Does not own:

- extension lifecycle execution
- prompt assembly
- session orchestration

#### `ExtensionRunner`

Owns:

- extension lifecycle coordination
- extension event emission
- extension tool registration / collection
- extension resource-discover hook

Does not own:

- resource discovery as a whole
- session lifecycle itself
- UI-specific extension affordances in P0

#### `SettingsManager`

Owns:

- stable configuration slices
- settings updates and subscriptions

Does not own:

- session orchestration
- tool execution policy
- extension runtime state

## P0.1 ResourceLoader v2

### Goal

Turn `ResourceBundle` into a stable carrier for resource-plane information.

### Current Problem

Today [ResourceBundle](/home/dev/workspace/loushang/src/loushang/coding/loader/types.py:7) and [DefaultResourceLoader](/home/dev/workspace/loushang/src/loushang/coding/loader/default_resource_loader.py:8) effectively only cover:

- `cwd`
- `AGENTS.md`
- prompt fragments derived from `AGENTS.md`

That is too narrow to serve as the substrate for extensions, richer prompts, or future skills/themes.

### Required Shape

`ResourceBundle` should at least carry:

- `cwd`
- `agents_path`
- `agents_md`
- `prompt_fragments`
- `skills`
- `extensions`
- `diagnostics`

It should also reserve optional slots for later evolution:

- `prompts`
- `themes`

Each category should be represented by resolved descriptors, not opaque raw objects.

Each resolved descriptor should carry enough provenance for later conflict handling and reload safety. P0 does not need every final field, but the descriptor model should support at least:

- `kind`
- `name`
- `source_path`
- `source`
- `enabled`
- `metadata`
- `diagnostics`

Examples:

- `PromptFragmentDescriptor`
- `ExtensionDescriptor`
- `SkillDescriptor`

### Loader Behavior

`DefaultResourceLoader.discover_resources(cwd)` should:

1. discover `AGENTS.md`
2. discover resource directories or files for:
   - skills
   - prompts
   - extensions
3. normalize them into a `ResourceBundle`
4. emit diagnostics for invalid, unreadable, conflicting, or unsupported resources
5. cache the resulting bundle

`reload_resources()` should preserve the same contract and simply refresh discovery.

### Merge Behavior

P0 should also define a stable merge step for extension-contributed resources.

The merge contract should:

- preserve static loader results
- append or overlay extension-contributed descriptors by category
- preserve provenance so later diagnostics can explain where a resource came from
- keep prompt assembly independent from the merge logic

### P0 Simplification

P0 does not need full `pi` parity for:

- prompt dedupe rules
- theme loading
- extension conflict resolution
- package-managed resource sources

But the loader API should be shaped so these can be added later without changing the main boundary.

## P0.2 ExtensionRunner MVP

### Goal

Create a minimal extension subsystem that is useful to the architecture before it is rich for users.

### Required Capabilities

The first runnable `ExtensionRunner` should support:

- `session_start`
- `session_shutdown`
- `before_agent_start`
- `resources_discover`
- extension-provided tool registration

This is enough to establish:

- runner lifecycle
- runner-to-session integration
- runner-to-loader integration
- runner-to-tools integration

### Failure And Isolation Rules

P0 must define explicit failure boundaries.

- extension load failure becomes a diagnostic by default and does not fail session construction
- `resources_discover` failure becomes a diagnostic for that extension and does not discard already discovered static resources
- `before_agent_start` failure is extension-local by default; the failing extension is skipped for that event and the turn may continue
- tool registration conflicts are rejected with diagnostics in P0; they are not silently last-write-wins

This keeps the first runner small without making failure behavior ambiguous.

### Session Integration Rule

`AgentSession` should:

- own the runner
- emit lifecycle events into it
- consume any extension-contributed tools or prompt-affecting data through explicit handoff

It should not:

- let extensions mutate core session internals directly
- let the runner replace prompt assembly or resource loading

### P0 Simplification

Do not implement in this phase:

- UI context
- command context
- keybindings
- slash commands
- widgets
- custom editors
- mode-specific rendering hooks

The MVP should be usable from programmatic or print-oriented flows without assuming an interactive shell.

## P0.3 ControlConfig And SettingsManager v2

### Goal

Stabilize configuration slices before the corresponding heavy behaviors land.

### Current Problem

Today [ControlConfig](/home/dev/workspace/loushang/src/loushang/coding/types.py:12) only carries:

- `default_model`
- `thinking_level`
- `system_prompt`

That is too small for the next planned layers.

### Required Slices

P0 should add stable configuration objects for:

- `compaction`
- `retry`
- `images`

The exact field set can remain narrow in P0, but the slices should exist as explicit config boundaries.

Recommended initial shape:

- `CompactionSettings`
  - `enabled`
  - `reserve_tokens`
  - `keep_recent_tokens`

- `RetrySettings`
  - `enabled`
  - `max_retries`
  - `base_delay_ms`

- `ImageSettings`
  - `auto_resize`
  - `block_images`

### SettingsManager Behavior

`SettingsManager` should evolve from a flat helper into a stable slice manager:

- update multiple slices coherently
- expose typed getters where appropriate
- continue supporting subscription

This should still remain small compared with `pi`. The key is stable shape, not full breadth.

### Ownership Rule

These slice types belong to `control`, not to top-level shared utility types.

P0 should move the concrete settings types under a control-owned module such as:

- `src/loushang/coding/control/types.py`
- or `src/loushang/coding/control/configs.py`

`ModelSelection` may remain shared if needed, but `ControlConfig` and its slice types should be owned by `control`.

## Proposed File Plan

### Expand Existing

- [src/loushang/coding/loader/types.py](/home/dev/workspace/loushang/src/loushang/coding/loader/types.py)
- [src/loushang/coding/loader/default_resource_loader.py](/home/dev/workspace/loushang/src/loushang/coding/loader/default_resource_loader.py)
- [src/loushang/coding/control/types.py](/home/dev/workspace/loushang/src/loushang/coding/control/types.py)
- [src/loushang/coding/control/settings_manager.py](/home/dev/workspace/loushang/src/loushang/coding/control/settings_manager.py)
- [src/loushang/coding/bootstrap.py](/home/dev/workspace/loushang/src/loushang/coding/bootstrap.py)
- [src/loushang/coding/session/agent_session.py](/home/dev/workspace/loushang/src/loushang/coding/session/agent_session.py)

### Add New Subsystem

- `src/loushang/coding/extensions/__init__.py`
- `src/loushang/coding/extensions/types.py`
- `src/loushang/coding/extensions/runner.py`

### Tests

- extend [tests/coding/test_resource_loader.py](/home/dev/workspace/loushang/tests/coding/test_resource_loader.py)
- extend [tests/coding/test_control_services.py](/home/dev/workspace/loushang/tests/coding/test_control_services.py)
- add `tests/coding/test_extension_runner.py`

## Execution Order

Recommended implementation order:

1. config slice types + `SettingsManager v2`
2. `ResourceBundle` + `DefaultResourceLoader v2` static descriptors
3. `ExtensionRunner` MVP types and lifecycle
4. two-phase `bootstrap` wiring
5. `AgentSession` integration
6. focused tests and contract cleanup

This order keeps the session integration last, which lowers rework while the substrate types are still moving.

## Success Criteria

This P0 is successful when:

- `DefaultResourceLoader` can discover and normalize more than `AGENTS.md`
- `ResourceBundle` is stable enough to carry loader results into prompt/session code without ad hoc growth
- `ExtensionRunner` exists as a real subsystem and can participate in session lifecycle
- `SettingsManager` carries explicit slices for future compaction/retry/image behavior
- no mode-specific assumptions are embedded into these components

## Contract Tests

P0 should cover these architecture contracts, not just module existence:

- static loader discovery returns stable typed descriptors with provenance
- two-phase discovery merges extension-contributed resources without losing static resources
- extension tool contribution flows through explicit handoff before prompt/tool activation
- settings slice updates propagate coherently through `SettingsManager` subscriptions
- extension failures downgrade to diagnostics according to the runner rules above

## What Comes Next

Once this P0 lands, the next development phase should be:

- `read / grep / find / ls`
- then `write / edit`

Only after that should the project invest in:

- `CompactionCoordinator`
- auto-retry orchestration
- `DiagnosticsService`

That sequencing maximizes:

- architecture flexibility
- extensibility
- alignment with `pi`
- near-term usability
