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
