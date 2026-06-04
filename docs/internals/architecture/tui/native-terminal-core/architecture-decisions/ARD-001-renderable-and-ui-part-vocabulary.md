# ARD-001: Renderable And UI Part Vocabulary

## Status

Accepted for the native terminal core draft.

## Context

The reference terminal UI we studied uses `Component` for both framework-level render
nodes and product-level visible widgets. That is concise in code, but it is
ambiguous in loushang architecture documents because the same word can mean:

- a low-level render protocol
- a concrete visible UI building block
- a transcript display record renderer
- a product-specific coding UI element

The native terminal core needs terminology that keeps framework contracts,
visible UI pieces, and transcript data separate.

## Decision

Use these canonical terms:

- `Renderable`: the framework-level render protocol. It accepts constraints,
  returns render results, and has no terminal writer access.
- `Container`: a renderable that lays out child renderables.
- `Focusable`: a renderable that can receive keyboard input and declare a cursor.
- `UI Part`: a concrete visible UI building block built from renderables, such as
  composer, status bar, pending queue view, tool execution view, or approval
  prompt.
- `Display Record`: stable or draft transcript data before rendering.
- `Content Block`: nested message content inside a display record, such as text
  or thinking content.
- `Renderer`: logic that converts display records or content blocks into
  renderables, UI parts, or logical lines.
- `Surface`: a temporary interactive renderable hosted by the surface host.
- `Overlay`: a surface presentation mode, not a separate kind of product widget.

Avoid `Component` as a canonical loushang term. It may appear only when quoting
or mapping an external reference system.

## Reference TUI Mapping

This mapping is for migration and implementation guidance. It records conceptual
correspondence; it is not a public product claim and does not require source-level
compatibility. It is based on observed behavior as of 2026-05-23 and is not a
compatibility contract.

| Reference TUI concept | Loushang term | Notes |
| --- | --- | --- |
| Framework render/input protocol | `Renderable` | Framework render/input protocol. |
| `Container` | `Container` | Same broad concept: ordered child renderables. |
| Combined terminal owner and root container | `Runtime` + `ScreenRoot` | Loushang separates terminal ownership from screen composition. |
| Ordered root layout | `Screen Region Stack` | Ordered region containers composed before diffing. |
| Product components in interactive mode | `UI Part` | Visible pieces such as composer, footer, selector, or tool view. |
| Header region | header area | Optional startup/onboarding region; not fixed chrome by default. |
| Chat/transcript region | transcript render area | Backed by display records and transcript UI parts. |
| Pending-message region | pending queue area / pending queue view | Transient bottom-frame UI. |
| Status/loading region | working line area / transient status region | Runtime-owned transient progress or loader UI. |
| Widget slot above composer | widget slot above composer | Optional product or extension transient UI. |
| Editor region | composer area / composer UI part | Focused input UI. |
| Widget slot below composer | widget slot below composer | Optional product or extension transient UI above footer/status. |
| Footer region | footer area / status area / status bar UI part | Bottom status row in the default coding layout. |
| overlay stack / `showOverlay` | surface host / overlay stack | Runtime-owned temporary UI layer. |
| `AssistantMessageComponent` | assistant message view UI part | Renders an assistant message record. |
| thinking rendering inside assistant message | thinking block + thinking view | Content block with visible/collapsed policy. |
| `ToolExecutionComponent` | tool execution record + tool execution view | Record owns lifecycle data; UI part renders it. |

## Consequences

- Architecture documents can distinguish render contracts from product-visible UI
  without overloading "component."
- Implementation can still use classes or protocols named however the codebase
  prefers, but public architecture docs should use `Renderable` and `UI Part`.
- Native terminal core spec directories reflect the split:
  - `render-framework/` for renderable, container, focus, surface host, overlay
    stack, and terminal writer contracts
  - `ui-parts/` for composer, status bar, pending queue, selection, approval,
    transcript, and tool execution views
  - `display-records/` for transcript data shapes
  - `renderers/` for markdown, thinking, tool, error, diff, and image rendering

## Rejected Alternatives

### Keep `Component`

Rejected because it would blur framework abstractions and product UI pieces.

### Use `RenderUnit`

Rejected because `Unit` is too generic and would add another overloaded word to
an architecture already using render pass, render operation, and render result.

### Use `UIPort` Or `UIInterface`

Rejected because `Port` is better reserved for external adapters such as
terminal or provider ports, and `Interface` describes programming language shape
rather than a render-tree participant.
