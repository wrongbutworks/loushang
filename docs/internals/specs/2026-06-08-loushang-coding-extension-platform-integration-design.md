# Loushang Coding Extension Platform Integration Design

## Goal

Turn the existing `loushang-coding` extension substrate into a coherent
extension platform.

The platform should make extensions a first-class product surface across:

- commands
- tools
- prompts and skills
- model/provider contributions
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
Authors and users need a unified mental model, and the runtime needs a single
place to project extension contributions, conflicts, permissions, and
diagnostics.

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
- command/tool/UI/model/prompt/skill contributions
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
what loader, registry, and runtime enforcement should use.

Recommended default mapping:

- `safe`: read-only metadata, prompts, skills, passive UI, observe hooks
- `standard`: `safe` plus model access, filesystem reads, commands, tools that
  still use normal tool permission gates
- `powerful`: `standard` plus exec, network, session mutation, tool mutation, or
  provider/model mutation

Policy should be evaluated before contributions become active. A denied
extension should remain visible in diagnostics and management surfaces, but its
runtime contributions should not be exposed.

Add a policy switch equivalent in meaning to:

```toml
[extensions]
enabled = true
allow_managed_hooks_only = false
```

When `allow_managed_hooks_only` is true, user/project/session hook definitions
are ignored while managed extension hooks remain eligible.

## Contribution Registry

Introduce a `ContributionRegistry` as the central projection of extension
capabilities.

It should store normalized contributions with:

- contribution id
- contribution type
- extension id
- source info
- scope
- priority
- permission requirements
- conflict policy
- diagnostics

The registry should not execute extension code. It is a projection and
arbitration layer between extension loading and product/runtime surfaces.

### Contribution Types

Initial contribution types:

- command
- tool
- prompt
- skill
- hook
- model_provider
- ui
- autocomplete
- resource_root

### Conflict Policy

Use contribution-type-specific policies:

- commands: allow duplicate display names; disambiguate in UI and diagnostics;
  allow user-configured default winner later
- tools: reject duplicate tool names unless an explicit override is configured
- prompts and skills: use existing resource precedence and collision
  diagnostics
- hooks: chain in deterministic order
- UI/autocomplete: merge by placement/trigger with diagnostics on incompatible
  targets
- model/provider entries: require explicit override for duplicate ids

Never drop an entire extension solely because one contribution conflicts. Drop
or disable the conflicting contribution and keep the rest of the extension
visible.

## Tools

Extension tools must pass through policy filtering before they are exposed to
the model.

The required order is:

1. load extension
2. normalize tool contribution
3. evaluate extension policy and permission capabilities
4. resolve tool conflicts
5. filter denied tools
6. expose active tools to the model/tool registry

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

## Diagnostics And Management Surface

The platform should expose extension state through diagnostics and a management
surface.

Minimum visible fields:

- extension id
- display name
- source
- enabled/disabled state
- permission level
- active contributions
- inactive contributions with reasons
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
