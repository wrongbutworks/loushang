# Loushang Harness TUI

`loushang.harnesstui` is the product-neutral composition layer between Harness
conversation contracts and the generic terminal UI framework. Its dependency
direction is:

```text
`loushang.coding.ui` -> `loushang.harnesstui` -> `loushang.tui`
                                             -> `loushang.harness`
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
- shared Harness status profiles that product shells can populate and present;
- reusable conversation reading, pending/working presentation, and input
  coordination;
- UI-side approval presentation and decision routing after the neutral Harness
  approval lifecycle has defined the corresponding ports.

`loushang.tui` continues to own terminal mechanics, rendering, layout, input
decoding, generic widgets, and transcript presentation primitives.
`loushang.harness` continues to own neutral runtime and durable conversation
contracts. Product adapters such as `loushang.coding.ui` continue to own raw
product-event interpretation, commands, policy, branding, and runtime assembly.

## First Slice: Conversation Reader

The first migration slice is deliberately narrow: the reusable transcript
source protocol and modal conversation reader move here while Coding-specific
session-backed source adapters remain in `loushang.coding.ui`.

This slice does not own session lifecycle, persistence, runtime orchestration,
or raw Agent/Coding event projection. It does not enter the render hot path.
Incremental transcript segmentation, streaming buffers, revision/window
generation, trimming, caching, and frame composition remain where they are.

Compatibility modules in `loushang.coding.ui` may temporarily re-export moved
symbols. They must depend inward on `loushang.harnesstui`; this package must
never depend back on those compatibility modules.

The stable imports introduced by this slice are the explicit module paths
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
neutral projector. Plain and Screen implementations remain product targets:
they decide how a projected fact mutates their renderer or screen app and keep
their product-specific status copy.

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
