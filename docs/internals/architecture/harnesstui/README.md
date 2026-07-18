# Loushang Harness TUI

`loushang.harnesstui` is the product-neutral composition layer between Harness
conversation contracts and the generic terminal UI framework. Its dependency
direction is:

```text
`loushang.coding.ui` -> `loushang.harnesstui` -> `loushang.tui`
                                             -> `loushang.harness`

`loushang.coding.testing.tui` -> `loushang.harnesstui.testing`
                              -> `loushang.harnesstui`
                              -> `loushang.tui`
```

The reverse dependencies are forbidden. In particular, `loushang.harnesstui`
must not import `loushang.coding`, `loushang.agent`, AI message/model/provider
packages, or product-specific policy.

## Responsibilities

This layer owns reusable Harness-oriented terminal interaction, including:

- adapting neutral conversation snapshots and actions to TUI records and
  surfaces;
- coordinating product-neutral conversation projection state such as tool
  timing and duplicate-result suppression;
- neutral tool-result views, transcript blocks, and deterministic presentation
  projection;
- product-neutral plain-terminal conversation rendering and projection targets
  over presentation-ready records and facts;
- shared Harness status profiles that product shells can populate and present;
- reusable settings pages, Harness status configuration, surface framing, and
  model-selection interaction over neutral TUI items;
- reusable conversation reading, pending/working presentation, and input
  coordination;
- UI-side approval presentation and decision routing after the neutral Harness
  approval lifecycle has defined the corresponding ports.

`loushang.tui` continues to own terminal mechanics, rendering, layout, input
decoding, host clipboard-image acquisition, generic widgets, and transcript
presentation primitives.
`loushang.harness` continues to own neutral runtime and durable conversation
contracts. Product adapters such as `loushang.coding.ui` continue to own raw
product-event interpretation, commands, policy, branding, and runtime assembly.

## Conversation Attachments

`loushang.harnesstui.conversation.attachments` owns product-neutral prompt-image
attachment coordination after the host clipboard has been read. It persists a
neutral `ClipboardImage` into a caller-supplied directory, derives a composer
marker relative to a caller-supplied display root, and tracks pending
attachments so submission order follows marker order in the composed text.
Read, unsupported-type, and persistence failures are returned as neutral
outcomes; products supply their own status copy.

The host clipboard backend and MIME detection remain in
`loushang.tui.clipboard_image`. Products continue to choose workspace and
storage-directory policy and adapt a neutral prompt attachment into model-facing
values such as `ImagePart`. Harnesstui does not import AI message types or
hard-code a Coding workspace layout.

The explicit module path
`loushang.harnesstui.conversation.attachments` is the stable entrypoint for this
capability. The conversation package initializer does not add a convenience
re-export.

## Conversation State, Queue, and Reader

`loushang.harnesstui.conversation.screen_state` owns reusable screen
conversation presentation state: retained display records, record revisions,
window generations, live assistant buffers, tool-record replacement, pending
input queues, and presentation-ready status facts. This is UI projection state,
not Harness Session lifecycle, persistence, or runtime orchestration.

The reusable transcript source protocol, active-window source,
record-composition helpers, and modal conversation reader also live here.
Record composition may merge history with a live window, preserve
presentation-only decorations, deduplicate the projected history suffix shared
with the active-window prefix, and select recent assistant text, but it only
operates on product-supplied `DisplayRecord` values. Coding retains the
Session-backed source because it still materializes Coding Session history and
AI message shapes.

`loushang.harnesstui.conversation.queue` owns defensive queue reads, cleared
queue normalization, draft restoration, and `PendingQueueView` composition over
a session-like port. Products retain queue availability policy, tracing sinks,
and the decision about when to present or restore queued input.

This slice does not own session lifecycle, persistence, runtime orchestration,
or raw Agent/Coding event projection. It does not enter the render hot path.
The state and active-window algorithms retain their existing semantics after
moving here. Incremental transcript segmentation, render caches, committed and
draft segments, and frame composition remain untouched in their current owner.

Compatibility modules in `loushang.coding.ui` may temporarily re-export moved
symbols. They must depend inward on `loushang.harnesstui`; this package must
never depend back on those compatibility modules.

The stable imports introduced by this slice are the explicit module paths
`loushang.harnesstui.conversation.screen_state`,
`loushang.harnesstui.conversation.queue`,
`loushang.harnesstui.conversation.reader` and
`loushang.harnesstui.conversation.source`. The conversation package does not
yet expose a broader convenience API.

## Tool Transcript and Status Profile

This migration slice adds two reusable presentation capabilities without
moving product event interpretation into this package.

`loushang.harnesstui.conversation.tool_transcript` owns the neutral tool-result
view and the display contracts used to project tool activity into conversation
records. Its inputs describe presentation-ready facts rather than Agent or
provider objects. Deterministic transcript status, block construction, and
record projection belong here because they are reusable across Harness-backed
terminal products.

`loushang.coding.ui` remains responsible for adapting raw `AgentToolResult`
instances and runtime events into that neutral view. It also retains product
policy: which events are visible, product-specific labels and commands,
redaction, and any decision that requires Coding runtime state. This keeps the
dependency pointing from Coding into Harnesstui and prevents Agent event types
from becoming presentation contracts.

`loushang.harnesstui.status.line` owns a shared Harness status profile and its
product-neutral presentation rules. A product shell supplies the profile's
values and decides when those values change. This capability is not the generic
`loushang.tui` status-bar mechanism: TUI continues to own the widget, layout,
styling primitives, invalidation, and frame rendering. Harnesstui must not
reach into those mechanics or introduce a second status-bar runtime.

`loushang.harnesstui.status.snapshot` owns the neutral status facts.
`loushang.harnesstui.status.provider` owns the callback-fed status profile and
product-neutral status-line setting transitions.
`loushang.harnesstui.status.plain` owns the compact, line-oriented toolbar
projection over presentation-ready status values. Coding continues to own live
Session reads, SettingsManager adaptation and persistence, and provider update
timing; its former status and toolbar imports are direct compatibility aliases.

These explicit module paths are the stable imports for this slice. The package
initializers do not need to provide convenience re-exports.

## Conversation Event Projection

`loushang.harnesstui.conversation.projection` owns the reusable state machine
that projects neutral conversation facts into a `ConversationProjectionTarget`.
It coordinates run starts, queue snapshots, assistant streaming, tool-call
snapshots and elapsed time, duplicate tool results, and duplicate assistant
errors. Its inputs are strings, timestamps, neutral tool views, and other
presentation-ready values; raw Agent/Coding event dictionaries and AI message
objects are not part of this contract.

Product adapters keep ownership of raw event interpretation. In Coding,
`loushang.coding.ui.conversation_event_adapter` reads product event shapes,
extracts message and compaction values, applies Coding cancellation policy,
and converts tool events through the Coding tool adapter before invoking the
neutral projector. `loushang.harnesstui.conversation.plain_target` owns the
reusable Plain projection target and its generic retry/compaction status copy.
Coding keeps the raw-event facade and decides which events reach that target.
The Screen implementation remains a product target and decides how projected
facts mutate its app and product-specific status copy.

Surface-interest checks happen in the Coding adapter before queue reads, text
joins, or tool rendering. This preserves Plain and Screen's distinct event
interests and prevents ignored or duplicate events from mutating the product
tool-render runtime. The neutral projector exposes only cheap state probes and
a tool-finish context for this purpose; Coding event dictionaries still never
cross the package boundary. Tool elapsed time brackets result adaptation and
neutral projection, while each target keeps its prior cleanup behavior if
projection fails.

Assistant text deltas form a strict pass-through hot path. The Coding adapter
must call `ConversationProjector.assistant_delta` directly, and that method
must call the target directly without constructing an intermediate event,
action list, tuple, mapping, generator, or concatenated buffer. Render caching,
segmentation, invalidation, frame composition, and terminal writes remain in
`loushang.tui` and the product renderer; this projection layer does not replace
or bypass the frozen TUI render-performance contract. A marked Coding adapter
test exercises the complete adapter-to-projector-to-target delta path, so the
existing `make test-tui-render-contract` gate covers this new boundary.

The explicit module path above is the stable import for this capability. The
package initializer does not provide a convenience re-export.

## Conversation Interaction Control

The reusable control plane for a full-screen conversation lives behind five
explicit entrypoints:

- `loushang.harnesstui.conversation.input` coordinates decoded input,
  completion, surfaces, running-submit modes, and neutral attachments;
- `loushang.harnesstui.conversation.control` coordinates abort, steer, and
  follow-up actions over caller-supplied controllers and status callbacks;
- `loushang.harnesstui.conversation.dispatch` owns product-neutral dispatch,
  result-presentation, and stable event-stream lifecycles;
- `loushang.harnesstui.conversation.run_context` owns UI subscription cleanup,
  stable emission, tracing, and context-exit ordering;
- `loushang.harnesstui.conversation.screen_runner` owns the reusable terminal
  read/route/run loop over explicit screen, router, and result ports.

These modules build conversation interaction from neutral UI values. They do
not own a Harness Session, persistence, runtime construction, raw product
events, Coding intents, model-facing image types, workspace paths, command
policy, or product copy. A product facade supplies those decisions and adapts
neutral attachments to its runtime-facing values. In particular, Coding keeps
`PromptIntent` and `BashIntent`, `ImagePart`, Session and observability setup,
raw-event interpretation, `.loushang` storage policy, and its interruption,
queue, and error messages.

The screen runner coordinates existing rendering calls but does not move or
replace transcript segmentation, invalidation, render caches, frame
composition, or terminal writes. Those hot-path responsibilities and the
independent render-performance contract remain unchanged. The conversation
package initializer intentionally does not re-export these entrypoints.

## Conversation Playback Testing

`loushang.harnesstui.testing` is opt-in test support for exercising the
product-neutral interaction ports above. Its dependency direction is
`loushang.coding.testing.tui` -> `loushang.harnesstui.testing` ->
`loushang.harnesstui` / `loushang.tui`. The reverse direction is forbidden:
production Harnesstui must never import its testing package, and the generic
TUI remains independent of both Harnesstui layers.

The shared testing package must not import Coding, AI, Agent, or Harness
runtime packages. It owns only reusable terminal test mechanics over neutral
ports:

- `loushang.harnesstui.testing.ports` defines the application, router,
  snapshot, result, and factory protocols used by playback drivers;
- `loushang.harnesstui.testing.input_playback` owns decoded-input playback,
  neutral routed results, state snapshots, artifacts, and the fluent input
  scenario;
- `loushang.harnesstui.testing.screen_loop_playback` owns scripted TTY chunks,
  real screen-loop playback, captured output and state artifacts, and the
  fluent loop scenario;
- `loushang.harnesstui.testing.scenarios.factory` binds those drivers to a
  product-supplied app, router, screen runner, artifact adapters, and frame
  contracts;
- the `composer`, `lifecycle`, `terminal`, `transcript`, and `surface` modules
  under `loushang.harnesstui.testing.scenarios` provide reusable recipe
  builders. They do not construct a product catalog at import time.

These explicit modules are the stable testing entrypoints. The testing package
initializer intentionally does not re-export them. Coding binds the neutral
recipes into its concrete catalog under `loushang.coding.testing.tui.scenarios`
and retains the app/router adapters, product-only scenarios, fakes, CLI runner,
product copy, fixture volumes, and render-performance budgets. The former
`loushang.coding.ui.playback*` modules remain temporary compatibility facades
only; production UI modules do not own playback implementations.

## Plain Conversation Presentation

`loushang.harnesstui.plain.renderer` owns the reusable plain-terminal renderer:
stdout flushing, assistant buffering, transcript-buffer projection, Markdown
and terminal blocks, status/error/tool presentation, width handling, and a
neutral presentation profile. It consumes only TUI records, neutral tool
blocks, and presentation-ready status values.

Coding retains a thin `PlainCodingUiRenderer` profile adapter. That adapter
owns the `Loushang TUI` title, `/feedback` interruption copy, Coding glyphs,
line mapping, and the Ran/Tested legacy command fallback. Coding also retains
`PlainCodingEventRenderer`, `CodingConversationEventAdapter`, raw event and AI
message interpretation, tool-result adaptation, and event-interest policy.

The shared Plain renderer and target do not participate in the Screen pipeline's
transcript segmentation, invalidation, caching, frame composition, or terminal
writes. Those frozen hot-path responsibilities remain in the Screen product
renderer and `loushang.tui`.

The stable imports are the explicit module paths
`loushang.harnesstui.plain.renderer` and
`loushang.harnesstui.conversation.plain_target`; their package initializers do
not provide convenience re-exports.

## Settings, Selection, and Surface Composition

Generic settings vocabulary belongs to the terminal framework.
`loushang.tui.settings` owns `ConfigRow`, the shared settings theme, value
formatting, row lookup, input helpers, and the reusable `SettingsListPage`.
It has no Harness or product dependency and can be used by any terminal
application.

Harnesstui owns the reusable interaction assembled from those generic widgets:

- `loushang.harnesstui.settings.page` provides the compatibility name
  `ConfigSettingsPage` for the generic TUI settings list;
- `loushang.harnesstui.settings.dashboard` owns the tabbed settings shell,
  static information pages, focus/footer interaction, and neutral status and
  usage view-models;
- `loushang.harnesstui.settings.model` owns model-settings interaction over
  product-supplied neutral choices;
- `loushang.harnesstui.status.settings` owns status-line settings rows, preview,
  and interaction over the neutral status profile;
- `loushang.harnesstui.surface.view` owns the framed bottom-surface view and its
  information-panel scrolling behavior;
- `loushang.harnesstui.surface.factory` owns pure information and command
  surface builders over presentation-ready text and neutral `SelectItem`
  values;
- `loushang.harnesstui.selection.model` owns scoped/all model selection over
  product-supplied `SelectItem` values;
- `loushang.harnesstui.selection.catalog` owns the opaque `ModelChoice` and its
  text, completion, palette, matching, settings-list, and selector-row
  projections;
- `loushang.harnesstui.commands.presentation` owns duck-typed command text,
  completion, palette, matching, display ordering, and selector-row
  projection.

These modules own interaction mechanics, layout, existing copy, and visual
behavior, but not product data or decisions. Coding continues to own settings
manager persistence, model and command discovery, model application, command
catalog and slash-command policy, status-provider updates, approval routing,
surface lifecycle, and adaptation of product data into neutral labels and
choices. Generic
`Surface`, `SurfaceHost`, `SelectionSurface`, and `SearchableList` mechanics
remain in `loushang.tui`.

The model settings page emits the shared UI intent
`InputIntent(kind="setting", text="model.current", note=<choice value>)`.
Products decide how that opaque choice value is resolved, applied, and
persisted; Harnesstui never calls a Session or settings manager.

Compatibility modules in `loushang.coding.ui` re-export the moved class objects
without subclassing or wrapping them. The explicit module paths above are the
stable imports; package initializers do not add convenience re-exports.

## Quality Gate

Run `make check-harnesstui` for the product-neutral composition boundary. The
gate lints and type-checks Harnesstui, its shared TUI settings vocabulary, and
the explicit Coding adapters, then runs Harnesstui, import-boundary, and direct
Coding integration tests. Marked render-contract cases are excluded from this
behavior gate and remain owned by the independent render-performance job.
Known dynamic dataclass-replacement typing limitations are suppressed only at
the exact expressions involved; the enclosing adapters remain under the normal
mypy gate so new diagnostics are enforced.

The deterministic render-performance contract remains a separate gate. Run
`make test-tui-render-contract` independently when changing render-path code or
moving a marked contract test; `check-harnesstui` does not change or duplicate
its thresholds.
