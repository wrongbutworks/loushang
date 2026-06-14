# PageScaffold

`PageScaffold` is a widget-level page shell for reusable TUI page content. It
composes caller-owned header, body, and footer slots, reserves footer space,
offsets body cursors through inserted chrome, and owns focus movement between
header and body.

It is not a product settings page, command surface, or screen-level frame.
Concrete pages still own selected tab state, business actions, data loading,
and product-specific intents.

## Inputs And State

- `body`: required renderable or focusable part.
- `header`: optional renderable or focusable part.
- `footer`: fixed string or callable receiving `PageScaffoldContext`.
- `focused`: whether the scaffold exposes a cursor/editor target.
- `focus_region`: `"header"` or `"body"`.
- `separator_after_header`: renders a full-width rule when a header rendered.
- `body_padding_top` / `body_padding_bottom`: best-effort blank rows inside the
  body region.
- `reserve_footer`: keeps one row available for footer text when possible.
- `theme`: optional `ThemeResolver` for scaffold-owned chrome.

`PageScaffoldContext` exposes `focus_region`, `header_focused`, and
`body_focused` so footers can switch hint text without inspecting child widgets.

## Layout Behavior

Rendering order is:

1. header slot
2. optional separator
3. top body padding
4. body slot
5. bottom body padding
6. footer

Body padding is decorative and yields when height is tight. If a body region is
available, PageScaffold keeps at least one body row before allocating requested
padding. Footer reservation also wins over padding when `reserve_footer=True`.

Footer text is truncated to the visible width before theme styling is applied.
Inserted separator and padding rows are full-width or blank; they do not ask
child widgets to account for external chrome.

## Focus Behavior

`focus()` targets the configured `focus_region`, falling back to the other
region when the preferred child cannot be focused.

When the header is focused, `down` and `enter` move focus into the body before
delegating to the header. When the body is focused, unhandled `up` and
`shift+tab` move focus back to the header. Other input is delegated to the
currently focused child.

`editor_input_target()` delegates to the focused child only when the scaffold
itself is focused.

## Theme Tokens

PageScaffold only themes chrome it owns:

| Token | Applies to |
| --- | --- |
| `widget.pageScaffold.separator` | Separator inserted after the header |
| `widget.pageScaffold.footer` | Footer text after width truncation |

Header and body styling remain owned by child widgets such as `Tabs`,
`SearchableList`, or page-specific renderables.

## Test Obligations

Changes to PageScaffold should cover:

- header/body/footer layout and height constraints
- footer reservation with long body content
- body padding allocation under normal and tight heights
- cursor offsets through separator and body padding
- focus routing between header and body
- footer callable context
- theme tokens preserving visible text
- public exports and example playback
