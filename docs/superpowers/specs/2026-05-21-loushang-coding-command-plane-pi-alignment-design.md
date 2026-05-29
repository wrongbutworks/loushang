# Loushang Coding Command Plane Pi Alignment Design

## Goal

Bring `loushang-coding` closer to `pi-coding-agent` on the user-facing command plane, without pulling in TUI or interactive-mode implementation work.

This design adds a `pi`-aligned command surface for:

- extension-registered commands
- extension-registered CLI flags
- extension-registered shortcuts
- unified command discovery across:
  - extension commands
  - prompt templates
  - skills

It also defines how those capabilities should be exposed through:

- `ExtensionAPI`
- `LoadedExtension`
- `ExtensionRunner`
- `AgentSession`
- `RpcMode`
- `CLI`

## Scope

### In Scope

- extension author API for:
  - `register_command(...)`
  - `register_flag(...)`
  - `register_shortcut(...)`
- loaded extension data model expansion
- extension runner registration, resolution, and diagnostics
- unified session-level command discovery
- session-level command execution contract
- RPC `get_commands` alignment
- CLI two-pass parsing for extension flags
- collision policy for commands, flags, and shortcuts
- compatibility and migration strategy

### Out Of Scope

- TUI shortcut consumption
- extension UI request/response protocol
- message renderer expansion
- plugin marketplace / package manager work
- new RPC command for direct command execution
- broad refactors of existing prompt/skill expansion flow

## Why This Comes Next

`loushang-coding` now has most of the non-interactive core substrate in place:

- session/runtime lifecycle
- persistent settings
- package-aware resource loading
- extension runtime rebinding
- print/json/rpc shells
- model projection and RPC state normalization

The remaining gap with `pi` is no longer primarily in `session` or `runtime`. The main gap is now the product-facing command plane:

- `get_commands` currently lists prompts and skills, but not extension commands
- extensions can register tools, but not user-facing commands, flags, or shortcuts
- CLI cannot yet consume extension-registered flags
- there is no unified session-owned command discovery and execution surface

Current `loushang` references:

- [ExtensionAPI](/home/dev/workspace/loushang/src/loushang/coding/extensions/api.py)
- [Extension types](/home/dev/workspace/loushang/src/loushang/coding/extensions/types.py)
- [Extension runner](/home/dev/workspace/loushang/src/loushang/coding/extensions/runner.py)
- [RPC get_commands](/home/dev/workspace/loushang/src/loushang/coding/mode/rpc_mode.py)
- [CLI parse/run](/home/dev/workspace/loushang/src/loushang/coding/cli/args.py)

Relevant `pi` references:

- [extensions/types.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/extensions/types.ts)
- [extensions/loader.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/extensions/loader.ts)
- [extensions/runner.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/extensions/runner.ts)
- [agent-session.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/core/agent-session.ts)
- [rpc-mode.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/modes/rpc/rpc-mode.ts)
- [cli/args.ts](/home/dev/workspace/pi-mono/packages/coding-agent/src/cli/args.ts)

## Approaches Considered

### Approach 1: Registry Only, No Execution Path

Add registration and `get_commands`, but do not define how commands execute.

Pros:

- smallest immediate change

Cons:

- creates a "discoverable but not product-complete" command plane
- would require a second design round to add dispatch semantics
- makes examples and RPC semantics unstable

Rejected.

### Approach 2: Pi-Aligned Command Plane Through Existing Boundaries

Add registration, resolution, session aggregation, session execution, RPC export, and CLI flag support, while keeping `ExtensionRunner` as the extension registration center and `AgentSession` as the product surface.

Pros:

- closest to `pi`
- preserves existing `loushang` boundaries
- avoids a second round of structural work
- keeps `session` as the user-facing business center

Cons:

- broader than a pure metadata registry

Recommended.

### Approach 3: Introduce A New Central CommandRegistry Service

Create a brand-new service object that owns all command/flag/shortcut state.

Pros:

- conceptually pure

Cons:

- too heavy for current needs
- overlaps with `ExtensionRunner` and `AgentSession`
- risks needless restructuring before there is enough surface pressure

Rejected for now.

## Design Summary

Use the existing `loushang` split and extend it in a `pi`-aligned way:

- `ExtensionAPI`
  - author-facing registration surface
- `ExtensionLoader`
  - load-time capture of registered commands/flags/shortcuts
- `ExtensionRunner`
  - extension-owned registry and conflict resolution
- `AgentSession`
  - unified product-facing command discovery and execution
- `RpcMode`
  - export unified command discovery
- `CLI`
  - consume resolved extension flags during startup

This keeps:

- tools for model invocation
- commands for user/host invocation

explicitly separate.

## Core Distinction: Tools vs Commands

This design must preserve a hard boundary between tools and commands.

### Tools

Tools are model-callable runtime capabilities:

- `bash`
- `read`
- `edit`
- extension-provided tool definitions

They belong to the tool substrate and are invoked by the model through agent/tool execution flow.

### Commands

Commands are user/host-facing invocation surfaces:

- extension commands
- prompt templates
- skills

They belong to the product surface and are discovered by humans, RPC clients, or future interactive consumers.

`ToolRegistry` and command discovery must remain separate systems.

## Data Model

### Extension Commands

Add a command model aligned with `pi`:

- `RegisteredCommand`
  - author-declared command
  - fields:
    - `name`
    - `description`
    - `handler`
    - `get_argument_completions` optional
    - `hidden` optional
- `ResolvedCommand`
  - runner-resolved command
  - fields:
    - all `RegisteredCommand` fields
    - `invocation_name`
    - `source_info`
    - `extension_name`

The key distinction:

- `RegisteredCommand` is author intent
- `ResolvedCommand` is the stable product-facing view after collision resolution

### Extension Flags

Add:

- `RegisteredFlag`
  - `name`
  - `description`
  - `type`: `"boolean"` or `"string"`
  - `default` optional
- `ResolvedFlag`
  - `RegisteredFlag`
  - `source_info`
  - `extension_name`

Unlike commands, flags should not be renamed during collision handling.

### Extension Shortcuts

Add:

- `RegisteredShortcut`
  - `shortcut`
  - `description`
  - `handler`
- `ResolvedShortcut`
  - `RegisteredShortcut`
  - `source_info`
  - `extension_name`

Shortcuts are included in this design, but current consumption remains future-facing because `loushang-tui` is not yet the target of this phase.

### Loaded Extension

Extend `LoadedExtension` so it stores:

- `commands`
- `flags`
- `shortcuts`

alongside existing:

- `hooks`
- `tool_definitions`
- `diagnostics`

## ExtensionAPI Additions

Extend [ExtensionAPI](/home/dev/workspace/loushang/src/loushang/coding/extensions/api.py) with:

- `register_command(name, *, description=None, handler, get_argument_completions=None, hidden=False)`
- `register_flag(name, *, type, description=None, default=None)`
- `register_shortcut(shortcut, *, description=None, handler)`

Design rules:

- keep the existing `register(api)` protocol
- do not require a new authoring style
- keep registration synchronous at load time
- keep `register_tool(...)` unchanged

### Command Handler Shape

Recommended command handler shape:

- `handler(args: str, ctx: ExtensionCommandContext) -> None | object`

The first version should allow either sync or async handlers at runtime if the runner can already support async dispatch. Load-time registration remains synchronous.

This command context is narrower than full event-hook context and should be purpose-built for command execution.

## ExtensionRunner Responsibilities

`ExtensionRunner` should become the extension-owned registry for:

- commands
- flags
- shortcuts

### New Responsibilities

- collect registered commands from loaded extensions
- collect registered flags from loaded extensions
- collect registered shortcuts from loaded extensions
- resolve extension command invocation names
- provide command diagnostics
- provide lookup/query methods for session and CLI consumption

### Required Query Surface

Add:

- `get_registered_commands() -> list[ResolvedCommand]`
- `get_command(invocation_name: str) -> ResolvedCommand | None`
- `get_flags() -> list[ResolvedFlag]` or equivalent map view
- `get_shortcuts(...) -> list[ResolvedShortcut]` or equivalent map view
- `get_command_diagnostics()`
- `get_flag_diagnostics()`
- `get_shortcut_diagnostics()`

## Collision Policy

### Commands

Command names should follow the same basic direction as `pi`.

Policy:

- collect commands in extension declaration order
- if a name is unique, keep it unchanged
- if a name appears multiple times, resolve to:
  - `name:1`
  - `name:2`
  - ...
- if a generated `name:N` is itself already taken, keep incrementing until unique

This is product-safe because command names are discoverable and invokable through the resolved `invocation_name`.

### Flags

Flags must be stable public names, so they must not be renamed.

Policy:

- builtin flags always win
- if an extension flag collides with a builtin flag:
  - skip the extension flag
  - record a diagnostic
- if two extensions register the same flag name:
  - first one wins
  - later ones are skipped with diagnostics

This matches `pi`'s more conservative flag behavior.

### Shortcuts

Shortcuts also should not be renamed.

Policy:

- reserved builtin shortcuts win
- extension collisions produce diagnostics
- first acceptable registration wins

Current consumption is deferred, but collision policy should still be defined now so extension behavior is predictable.

## Session-Level Product Surface

`AgentSession` should become the unified command-plane owner for callers.

### New Session Queries

Add:

- `get_commands() -> list[SlashCommandInfo]`

This aggregates:

- extension commands from `ExtensionRunner`
- prompt templates from loaded resources
- skills from loaded resources

The return shape should remain product-facing and source-aware:

- `name`
- `description`
- `source`
- `source_info`

### New Session Command Execution Contract

Add:

- `execute_command(invocation_name: str, args: str) -> CommandExecutionResult | None`

This is an internal product surface for:

- prompt preflight
- future interactive command dispatch
- tests
- future RPC expansion if needed

### Important Rule

Do **not** invent a new heavy RPC `execute_command` command in this phase.

The primary user-facing execution path should remain:

- user enters `/command ...`
- prompt/session preflight identifies command type
- session dispatches through the unified command execution surface

This keeps `loushang` aligned with `pi`'s command-plane mental model.

## Unified Discovery, Split Execution

Even though command discovery is unified, execution is intentionally not monolithic.

### Extension Commands

Execution path:

- `AgentSession.execute_command(...)`
- `ExtensionRunner.get_command(...)`
- resolved command handler dispatch

### Prompt Templates

Execution path:

- session prompt preflight / template expansion

These are not imperative extension commands. They are prompt assets.

### Skills

Execution path:

- session prompt preflight / skill expansion

These are also resource-backed expansion surfaces, not imperative extension commands.

So:

- discovery is unified
- backend execution remains source-specific

This mirrors how `pi` treats the command plane.

## RPC Surface

### `get_commands`

Change `RpcMode.get_commands` so it delegates to `session.get_commands()` instead of building its own prompt/skill list.

This makes RPC an adapter instead of a second command aggregation system.

### No New RPC Execute Command

Do not add a dedicated RPC command execution verb in this phase.

Reasons:

- it is not required for `pi`-style alignment
- it makes the wire protocol heavier
- it duplicates the `/command ...` prompt path

If future host integrations need direct command execution, that should be a later, explicit protocol design decision.

## CLI Flag Design

CLI flags require a staged parse flow.

### Why Two-Pass Parsing

Extension flags cannot be known until extensions are discovered and loaded.

That means static one-pass parsing is insufficient if CLI should support extension flags cleanly.

### Recommended Flow

1. parse builtin bootstrap args
2. determine project/resource loading context
3. discover/load extensions
4. collect resolved extension flags
5. run full parse with builtin + extension flags
6. bind parsed extension flag values into runtime/runner state

### Parsed Result Shape

Avoid stuffing extension flag values directly into the static builtin args object.

Recommended shape:

- builtin CLI args
- `extension_flag_values: dict[str, bool | str]`

This keeps the base CLI type stable as extension count grows.

### CLI Consumer Responsibilities

CLI should:

- include extension flags in help text
- validate boolean/string semantics
- pass resolved values into extension runtime state before command/session execution

## Shortcut Design

Shortcuts are part of this command-plane design, but they are not a blocker for the current non-interactive alignment work.

This phase should define:

- author registration
- loading
- collision handling
- resolved shortcut query surface

This phase should not require:

- immediate TUI integration
- immediate interactive-mode implementation

That keeps the design aligned with `pi` while respecting current `loushang` scope.

## Compatibility Strategy

This feature set should be additive and backward-compatible.

### Existing Extensions

Existing `register(api)` extensions should continue to work unchanged.

If an extension does not register:

- commands
- flags
- shortcuts

then its behavior should remain exactly as it is today.

### Existing RPC Clients

`get_commands` remains the same RPC command.

Only the returned command set expands:

- before: prompt + skill
- after: extension + prompt + skill

This is an additive change.

### Existing CLI Users

Builtin flags remain stable.

Extension flags must never override builtin ones.

## Rollout Plan

### Phase 1: Extension Authoring Surface

- extend `ExtensionAPI`
- extend `LoadedExtension`
- extend `ExtensionLoader`

### Phase 2: Runner Registry

- command registration/resolution
- flag aggregation
- shortcut aggregation
- diagnostics

### Phase 3: Session Product Surface

- `get_commands()`
- `execute_command(...)`
- prompt/skill/extension command routing

### Phase 4: RPC Alignment

- delegate `get_commands` to session

### Phase 5: CLI Alignment

- two-pass parse
- extension flag binding
- help text integration

### Phase 6: Examples And Docs

Only after the surface stabilizes:

- minimal RPC command-discovery example
- minimal CLI extension-flag example
- minimal extension command example

## Testing Strategy

The implementation plan should include tests for:

- extension command registration
- command collision resolution
- flag collision diagnostics
- shortcut collision diagnostics
- session command aggregation
- session command execution
- RPC `get_commands`
- CLI extension flag parsing and injection
- backward compatibility with existing extensions

## Acceptance Criteria

This work is complete when:

- extensions can register commands, flags, and shortcuts
- `ExtensionRunner` resolves extension commands into stable invocation names
- `AgentSession.get_commands()` returns extension + prompt + skill entries
- `AgentSession.execute_command(...)` can dispatch extension commands and route prompt/skill command paths
- `RpcMode.get_commands` delegates to session
- CLI can parse extension flags through a two-pass flow
- existing extensions continue working unchanged

## Non-Goals For This Phase

This phase intentionally does not include:

- extension UI request/response
- direct RPC command execution verb
- interactive-mode shortcut handling
- full plugin/package management
- large rework of prompt/template execution semantics beyond what command routing needs

## Recommendation

Proceed with the `pi`-aligned command-plane design through existing `loushang` boundaries:

- `ExtensionAPI` for registration
- `ExtensionRunner` for extension-owned registry and conflict resolution
- `AgentSession` for unified discovery and execution
- `RpcMode` for export
- `CLI` for flag consumption

This is the smallest design that closes the most valuable remaining non-interactive gap without prematurely dragging in TUI work.
