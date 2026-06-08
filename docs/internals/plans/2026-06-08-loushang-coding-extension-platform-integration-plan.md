# Loushang Coding Extension Platform Integration Plan

## Goal

Implement the extension platform in phases, using
`docs/internals/specs/2026-06-08-loushang-coding-extension-platform-integration-design.md`
as the source of architectural decisions.

This plan intentionally starts with design and projection layers before
expanding runtime behavior. The aim is to avoid coupling extension loading,
package management, hook execution, and TUI integration into one large change.

## P0: Inventory And Design Lock

### Objective

Create the baseline inventory and decision record that later PRs use as their
contract.

### Implementation

- Add or update an extension platform inventory document covering:
  - `src/loushang/coding/extensions`
  - `src/loushang/coding/plugin`
  - `src/loushang/coding/package`
  - `src/loushang/coding/commands`
  - `src/loushang/coding/tools`
  - `src/loushang/tui/extensions.py`
- Record the contribution matrix:
  - current support
  - target support
  - owner subsystem
  - diagnostics source
  - policy gate
- Record final decisions for:
  - manifest format
  - permission model
  - contribution conflicts
  - hook classes
  - UI bridge boundary
  - dependency scope
  - future-only capabilities

### Tests

- Documentation review against the design spec.
- No runtime tests required unless code changes are introduced.

### Not In Scope

- New runtime behavior.
- New manifest parser.
- New UI.

## P1: Manifest, Policy, And Contribution Registry Skeleton

### Objective

Add structured extension metadata and contribution projection without changing
user-visible runtime behavior.

### Implementation

- Add an internal extension manifest model for `loushang-extension.toml`.
- Add parser diagnostics for invalid TOML, unknown required fields, unsupported
  contribution sections, and invalid permission levels.
- Add `ExtensionPolicy` or equivalent evaluation object with:
  - `enabled`
  - permission level
  - internal capabilities
  - managed-hooks-only decision
- Add `ContributionRegistry` or equivalent projection with contribution
  descriptors for commands, tools, prompts, skills, hooks, models/providers,
  UI, autocomplete, and resource roots.
- Wire the loader to produce contribution descriptors in addition to existing
  loaded extension data.
- Keep existing `register(api)` runtime compatibility.

### Tests

- Manifest parser accepts minimal valid TOML.
- Invalid manifest produces extension diagnostics, not an uncaught exception.
- Policy-disabled extension remains visible but contributes no active entries.
- Registry records source info and inactive reasons.

### Not In Scope

- Installing dependencies.
- Reworking hook dispatch.
- TUI management UI beyond diagnostics projection.

## P2: Commands, Tools, Prompts, And Skills Mounting

### Objective

Route the main user-facing contribution types through the registry.

### Implementation

- Mount extension commands through the command catalog using contribution
  metadata and source diagnostics.
- Mount extension tools only after policy evaluation, conflict resolution, and
  denied-tool filtering.
- Preserve existing prompt and skill resource loader precedence; add registry
  diagnostics that explain collisions and inactive resources.
- Add `/extensions` as the first management surface.
  - It should list active tools, commands, hooks, prompts, skills, permissions,
    conflicts, and load warnings.
  - It should not install, update, or remove extensions in this phase.

### Tests

- Duplicate extension tool name is rejected unless explicit override support
  exists.
- Denied tool does not appear in model-visible tool list.
- Duplicate command names are visible with disambiguation diagnostics.
- `/extensions` prints active tools and inactive reasons without the
  `? thinking:` transcript artifact.

### Not In Scope

- `/plan` command work.
- Full plugin management UI.
- Marketplace behavior.

## P3: Hook Semantics Consolidation

### Objective

Make hook semantics explicit and centrally dispatched while preserving current
event names.

### Implementation

- Add hook metadata classes:
  - `observe`
  - `transform`
  - `intercept`
  - `augment`
- Split hook concerns into:
  - schema/manifest declarations
  - event payload definitions
  - hook registry
  - dispatcher/engine
  - result parsing
  - diagnostics
- Route existing session/tool/provider hook calls through the dispatcher.
- Preserve current event names and compatibility wrappers.
- Add policy support for managed-hooks-only mode.

### Tests

- Observe hook cannot mutate or block.
- Transform hook result is applied in deterministic order.
- Intercept hook can block with a diagnostic reason.
- Augment hook can append context/diagnostics.
- Managed-hooks-only mode ignores unmanaged hook sources.

### Not In Scope

- New large hook catalog.
- Extension-to-extension communication.
- Shell-level hook command runner unless explicitly required by existing hooks.

## P4: UI And Autocomplete Bridge

### Objective

Expose extension UI integration through controlled bridge APIs.

### Implementation

- Extend the existing TUI extension host into an `ExtensionUiBridge`-style
  runtime surface.
- Allow extension contributions for:
  - status
  - footer/header
  - surfaces/modals
  - notifications
  - select/confirm/input/editor prompts
  - autocomplete
  - action/command palette entries
  - message renderers
- Route keyboard and command palette integration through an action registry.
- Keep raw screen/layout/key access private to the TUI implementation.
- Surface UI contribution diagnostics in `/extensions`.

### Tests

- Extension status/footer widgets dispose cleanly on unload/reload.
- Autocomplete provider failure records diagnostics without breaking editor
  input.
- Extension action appears only in allowed UI contexts.
- Raw key/listener APIs are not part of the public extension bridge.

### Not In Scope

- A visual marketplace.
- Arbitrary TUI layout mutation.
- Direct render-loop control.

## P5: Dependency Productization

### Objective

Add dependency semantics with conservative installation boundaries.

### Implementation

- Add manifest dependency sections for:
  - Python packages
  - external binaries
  - system capabilities
- Implement Python package installation only into Loushang-managed isolated
  targets.
- Add binary detection with actionable diagnostics.
- Add system capability checks as diagnostic-only.
- Project the dependency state in `/extensions`.

### Tests

- Python dependency install target is not the project venv, active venv, or
  global environment.
- Missing binary produces a non-fatal diagnostic.
- Unsupported system capability produces diagnostic-only status.
- Dependency failures disable dependent contributions without hiding the whole
  extension.

### Not In Scope

- Automatic OS package installation.
- Arbitrary shell install scripts.
- Network access unless package policy explicitly allows it.

## Future

Future designs may add:

- marketplace and signing
- extension-to-extension bus
- LSP lifecycle
- app/channel connectors
- richer managed enterprise policy
- stronger sandboxing

These should not block P0-P5.

## Rollout

Use one PR per phase after this documentation PR.

Each implementation PR should include:

- behavior-focused tests
- diagnostics snapshots or assertions where applicable
- compatibility notes for existing extension APIs
- updates to examples only after the API surface is stable for that phase

## Acceptance Criteria

The platform integration work is complete when:

- `/extensions` can explain enabled extensions, inactive contributions,
  permissions, conflicts, dependencies, and hook declarations.
- Extension tools are filtered before model exposure.
- Hook semantics are centrally declared and dispatched.
- UI integration goes through a bridge/action registry.
- Dependency handling respects Loushang-managed isolation.
- Existing package/plugin/extension boundaries remain intact.
