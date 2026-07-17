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
