# Renderer Spec Inventory

Renderers convert display records or content blocks into UI parts, renderables,
or logical lines. They do not write to the terminal.

## Initial Renderers

| Renderer | Purpose |
| --- | --- |
| MarkdownRenderer | Terminal-safe markdown rendering and wrapping. |
| CodeRenderer | Code block styling and optional syntax highlighting adapter. |
| DiffRenderer | Diff line classification and theme styling. |
| ThinkingRenderer | Thinking block visible/collapsed/hidden rendering. |
| ToolRenderer | Tool execution record rendering. |
| ErrorRenderer | Concise error rendering with optional verbose details. |
| ImageRenderer | Text fallback plus optional terminal image protocol adapter. |

Image protocol adapters must declare any non-text terminal resources they create
and any line ranges that require expanded invalidation. The render loop must not
assume protocol image output can always be treated as ordinary text-line diff.

## Import Boundary

Optional libraries such as markdown parsers or syntax highlighters must be lazy
or adapter-level imports. Importing the raw runtime core must not require them.
