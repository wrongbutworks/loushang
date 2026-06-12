# Loushang Coding Extension Platform Integration Design

## Goal

Turn the existing `loushang-coding` extension substrate into a coherent
extension platform.

The platform should make extensions a first-class product surface across:

- commands
- tools
- prompts and skills
- model/provider runtime surfaces
- runtime hooks
- TUI UI and autocomplete
- plugin/package distribution
- diagnostics and policy

This design is a consolidation spec. It does not replace the accepted
package/plugin/extension boundary, and it does not attempt to implement all
capabilities in one phase.

## Current Baseline

`loushang-coding` already has the important lower layers:

- `package` as the resource distribution unit
- `plugin` as a manifest-backed package source view
- `extension` as the executable runtime programmability surface
- `ExtensionAPI`, `ExtensionLoader`, `ExtensionRunner`, and runtime bindings
- extension-contributed tools
- resource discovery hooks
- command registration
- TUI extension host primitives
- unified diagnostics with an `extensions` source

The current gap is not whether extensions can run. The gap is that extension
capabilities are still registered and surfaced through several separate paths.
Authors and users need a unified mental model, and management surfaces need a
single read model for extension surfaces, conflicts, permissions, and
diagnostics. Runtime activation remains owned by each surface-specific
controller or dispatcher.

## Relationship To Existing Designs

This design consolidates and extends existing accepted designs. It does not
supersede them.

- Extension API v1 remains the author-facing runtime API baseline.
- Extensions Runtime V2 remains the binding and rebinding lifecycle baseline.
- The package/plugin boundary remains authoritative for distribution and source
  management.
- The command-plane design remains authoritative for built-in command
  registration and command execution semantics.
- Resource loader precedence and collision rules remain authoritative for
  prompts, skills, themes, and resource roots.

This design adds the missing platform layer above those documents: a manifest,
policy, extension inventory projection, diagnostics projection, and staged
integration plan that tie the existing subsystems together without replacing
surface-specific runtime owners.

## Boundary Decisions

### Package

`package` remains the distribution and materialization layer.

It owns:

- package roots
- remote materialization
- update/remove lifecycle
- package resource summaries
- package trust and source policy

It does not own runtime extension APIs.

### Plugin

`plugin` remains a manifest-backed source view.

It owns:

- plugin source registration
- plugin manifest parsing
- plugin enable/disable state
- plugin identity and metadata
- package root resolution

A plugin may carry extensions, but not every plugin is an extension.

### Extension

`extension` remains the runtime programmability surface.

It owns:

- author-facing registration APIs
- runtime hooks
- command/tool/UI/model/prompt/skill runtime surfaces
- extension diagnostics
- extension policy and permissions

Packages and plugins deliver extensions. They do not replace the extension
boundary.

## Manifest

### Author Format

Use `loushang-extension.toml` as the extension author manifest.

The manifest is separate from plugin/package manifests. `plugin.json` continues
to describe plugin source identity and package root resolution. It should not
become the extension capability manifest.

The loader should parse TOML into an internal structured model such as a
dataclass or Pydantic model. Runtime code should consume the structured model,
not raw TOML dictionaries.

### Initial Manifest Areas

The manifest should reserve stable areas for:

- metadata
- permissions
- dependencies
- commands
- tools
- prompts
- skills
- hooks
- models/providers
- UI/autocomplete
- configuration

The first implementation may support only a subset, but unsupported sections
must produce clear diagnostics rather than being silently ignored.

### Example Shape

```toml
[extension]
id = "acme.review"
name = "Acme Review"
version = "0.1.0"
description = "Adds project-specific review commands and hooks."

[permissions]
level = "standard"
capabilities = ["filesystem", "model"]

[[commands]]
name = "acme-review"
description = "Run the Acme review workflow."

[[hooks]]
event = "before_agent_start"
kind = "augment"
handler = "extension:before_agent_start"

[[tools]]
name = "acme_lookup"
description = "Look up Acme domain metadata."

[dependencies.python]
packages = ["acme-sdk>=0.3"]
```

## Permissions And Policy

Use a hybrid permission model:

- user-facing level: `safe`, `standard`, `powerful`
- internal capabilities: `exec`, `filesystem`, `network`, `model`,
  `session_mutation`, `ui_mutation`, `tool_mutation`

The level is what users and management UI should display. The capabilities are
what loader, inventory projection, and runtime enforcement should use.

Recommended default mapping:

- `safe`: read-only metadata, prompts, skills, passive UI, observe hooks
- `standard`: `safe` plus model access, filesystem reads, commands, tools that
  still use normal tool permission gates
- `powerful`: `standard` plus exec, network, session mutation, tool mutation, or
  provider/model mutation

Policy should be evaluated before runtime surfaces are exposed. A denied
extension should remain visible in diagnostics and management surfaces, but its
tools, commands, hooks, provider registrations, resources, and UI surfaces
should be filtered by their owning runtime controllers or dispatchers.

Add a policy switch equivalent in meaning to:

```toml
[extensions]
enabled = true
allow_managed_hooks_only = false
```

When `allow_managed_hooks_only` is true, unmanaged hook definitions are ignored
while managed extension hooks remain eligible.

For this policy:

- managed hooks are hook declarations loaded from enabled extensions delivered
  by accepted plugin/package sources or managed configuration
- unmanaged hooks are local project, user, or session hook definitions that are
  not tied to a loaded extension declaration

## Extension Inventory Projection

Introduce an `ExtensionInventory` or equivalent read model as the central
projection of extension runtime surfaces.

It should store normalized surface records with:

- surface id
- surface type
- extension id
- source info
- scope
- priority
- permission requirements
- conflict policy
- diagnostics

The inventory must not execute extension code, activate runtime behavior, or
arbitrate winners directly. It is a management and diagnostics projection over
decisions made by the owning runtime surfaces:

- tools remain owned by the tool registry and extension runner
- commands remain owned by the command resolver
- prompts, skills, themes, and resource roots remain owned by the resource
  loader and resource refresh pipeline
- hooks remain owned by the hook dispatcher
- model/providers remain owned by provider-specific controllers
- UI and autocomplete remain owned by the TUI bridge and action/autocomplete
  registries

If an interim implementation keeps the `ContributionRegistry` name for
compatibility, its contract is still inventory-only. It must not become the
activation path for tools, commands, hooks, resources, providers, or UI.

### Surface Record Types

Initial surface record types:

- command
- tool
- prompt
- skill
- hook
- model_provider
- ui
- autocomplete
- resource_root

### Conflict Visibility

Use surface-specific policies in the owning resolver or dispatcher:

- commands: allow duplicate display names; disambiguate in UI and diagnostics;
  allow user-configured default winner later
- tools: reject duplicate tool names unless an explicit override is configured
- prompts and skills: use existing resource precedence and collision
  diagnostics
- hooks: chain in deterministic order
- UI/autocomplete: merge by placement/trigger with diagnostics on incompatible
  targets
- model/provider entries: require explicit override for duplicate ids

The inventory records the resulting winner, rejection, inactive reason, or
diagnostic. Never drop an entire extension solely because one surface conflicts.
The owning resolver may reject or disable the conflicting surface while the rest
of the extension remains visible.

## Tools

Extension tools must pass through policy filtering before they are exposed to
the model.

The required order is:

1. load extension
2. collect runtime tool registrations and manifest tool declarations
3. evaluate extension policy and permission capabilities
4. resolve tool conflicts in the tool surface
5. filter denied tools
6. expose allowed tools to the model/tool registry
7. project the resulting tool state into the extension inventory

Call-time permission checks remain necessary, but they are not sufficient. A
tool denied by policy should not appear in the model-visible tool list.

## Hooks

Keep existing lifecycle event names for compatibility. Add hook metadata that
declares the hook capability class.

Hook classes:

- `observe`: read event state, cannot mutate or block
- `transform`: returns a modified input/output payload
- `intercept`: may block, approve, deny, or replace an operation
- `augment`: may add context, messages, diagnostics, or side effects

`transform` and `augment` are mutually exclusive for one handler result.
`transform` is replacement-style: it returns the next payload for the pipeline.
`augment` is append-style: it may add messages, context, diagnostics, or
side-effect requests, but it must not replace the event payload. If both are
needed, they should be expressed as separate hook handlers so ordering remains
explicit.

The hook subsystem should be split into:

- hook schema and manifest parsing
- typed event payloads
- hook declarations and registry
- dispatcher/engine
- output/result parser
- diagnostics

Session and runner code should call into the hook dispatcher instead of owning
hook semantics directly.

## UI And Autocomplete Bridge

Extensions may integrate with UI only through an explicit bridge.

Allowed bridge capabilities:

- status fields
- footer/header widgets
- surfaces/modals
- notifications
- select/confirm/input/editor prompts
- autocomplete providers
- command/action palette entries
- message renderers
- controlled editor text actions

Message renderers are constrained renderers, not arbitrary output channels.
They should receive structured message data and return only renderer-approved
objects or an allowed markup subset. They must not emit raw terminal control
sequences, arbitrary ANSI, or executable markdown side effects.

Disallowed:

- direct screen buffer access
- direct layout tree mutation
- raw key listener registration as a public extension API
- direct ownership of render loop state
- mutation of TUI internals outside bridge methods

Keyboard and command palette integration should go through an action registry.
Extensions register actions; the UI decides whether and where actions are
invocable.

## Dependencies

Dependency support should be productized incrementally.

### V1 Commitment

V1 may define dependency metadata and diagnostics but should not promise full
automatic installation for every dependency class.

Supported semantics:

- Python packages: declared in manifest and installed only into
  Loushang-managed isolated targets when installation support lands
- external binaries: presence detection and friendly diagnostics
- system capabilities: diagnostic-only checks

Extensions must not install dependencies into the user's project virtualenv,
global Python environment, or active shell environment.

The preferred Python dependency installation candidate is
`uv pip install --target <loushang-managed-extension-site>`, with the target
owned by Loushang package state. Runtime import exposure should be explicit,
for example by adding the resolved target through a controlled import path
mechanism during extension loading. The author manifest declares dependencies;
resolved paths belong to internal package/extension state, not to the author
manifest.

## Performance Constraints

Extension platform plumbing sits near hot paths, so implementation phases should
keep these constraints visible:

- inventory lookup should use indexed maps rather than repeated linear scans over
  all extensions
- model-visible tool filtering should be computed when extension/tool state
  changes, not on every token or render event
- hook dispatch should run with deterministic ordering and explicit timeouts for
  blocking/intercept hooks
- UI bridge rendering should isolate extension failures and avoid blocking the
  main TUI render loop
- `/extensions` should be cheap enough for interactive use by reading projected
  state instead of reloading extensions

## Diagnostics And Management Surface

The platform should expose extension state through diagnostics and a management
surface.

Minimum visible fields:

- extension id
- display name
- source
- enabled/disabled state
- permission level
- exposed runtime surfaces
- inactive or rejected surfaces with reasons
- conflicts
- dependency diagnostics
- hook declarations
- load/runtime warnings

The initial product surface can be a slash command such as `/extensions` plus
CLI/JSON projection where appropriate.

## Out Of Scope For Mainline P0-P5

These capabilities should remain future work unless a later design promotes
them:

- extension marketplace
- extension signing
- automatic non-Python dependency installation
- unrestricted extension-to-extension import or RPC
- LSP server lifecycle
- background channel/app connector ecosystem
- raw TUI keybinding APIs
- sandbox isolation beyond current process and package isolation guarantees

## Acceptance Criteria

The integrated platform design is complete when:

- package/plugin/extension boundaries remain intact
- extension manifest, permission, conflict, hook, UI bridge, dependency, and
  diagnostics decisions are documented
- a phased implementation plan exists
- no runtime implementation is required to merge the design PR
- future implementation PRs can reference this design without re-deciding the
  platform boundaries
