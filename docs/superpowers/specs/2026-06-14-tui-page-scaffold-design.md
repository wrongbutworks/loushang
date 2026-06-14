# TUI PageScaffold Design

## Status

Ready for implementation planning.

This is a TUI-lane design for a reusable page-level scaffold widget. It is
intentionally limited to generic page layout and focus orchestration. It does
not migrate existing product settings pages in this slice.

## Package Scope

Implement the reusable widget in:

`src/loushang/tui/ui_parts/widgets/page_scaffold.py`

Expose public imports through:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- `src/loushang/tui/__init__.py`

Primary tests:

- `tests/tui/test_widgets_page_scaffold.py`
- existing public export/import-boundary tests where applicable

Primary example:

- create `examples/tui/53_widgets_page_scaffold.py`

Do not modify `examples/tui/52_widgets_tabgroup_searchable_list.py` in this
slice. Do not migrate `src/loushang/coding/ui/settings_page.py` in this slice.

## Problem

Settings-like TUI pages now repeatedly hand-roll the same page shell:

- a focusable header, commonly tabs
- a focusable body, commonly `SearchableList` or nested page content
- an optional separator after the header
- a footer with focus-sensitive help text
- height reservation so long bodies do not push the footer away
- cursor row offset when chrome lines are inserted above focused content
- fallback focus movement between header and body

Existing lower-level layout utilities such as `ScreenRegionStack` are useful
for screen composition, but they do not model page-level focus flow. Existing
widgets such as `TabGroup` and `SearchableList` should keep owning their own
domain behavior; the missing piece is a small page-level shell that composes
them consistently.

## Goals

- Add a reusable `PageScaffold` widget for page-level header/body/footer layout.
- Keep the API generic and slot-based, not settings-specific.
- Manage focus between `header` and `body`.
- Preserve body-owned behavior such as `SearchableList` query editing,
  filtering, scrolling, overflow hints, and boxed search rendering.
- Reserve footer height so body overflow cannot displace the footer.
- Correctly offset cursors when separator/footer/page chrome changes line
  positions.
- Provide a new `examples/tui/53_widgets_page_scaffold.py` example as the first
  integration consumer.
- Keep `examples/tui/52_widgets_tabgroup_searchable_list.py` untouched as the
  existing TabGroup/SearchableList regression example.

## Non-Goals

- Do not migrate coding `SettingsPageView`.
- Do not migrate example 52.
- Do not add settings-specific row/value/status-line APIs.
- Do not replace `ScreenRegionStack`, `TabGroup`, `Tabs`, or `SearchableList`.
- Do not create a grid/layout DSL.
- Do not introduce a global theme registry.
- Do not make `PageScaffold` responsible for business actions or selected tab
  content switching.

## Concept

`PageScaffold` is a page-level layout and focus shell:

```text
header
separator
body
padding
footer
```

It sits above concrete widgets and below product pages. It should feel like a
layout widget, but it is not a pure layout primitive because it owns focus
movement between page regions.

## Public API

First version:

```python
@dataclass(frozen=True, slots=True)
class PageScaffoldContext:
    focus_region: Literal["header", "body"]
    header_focused: bool
    body_focused: bool


PageScaffoldFooter = str | Callable[[PageScaffoldContext], str]


@dataclass(slots=True)
class PageScaffold:
    body: object
    header: object | None = None
    footer: PageScaffoldFooter = ""
    theme: ThemeResolver | None = None
    focused: bool = False
    focus_region: Literal["header", "body"] = "body"
    separator_after_header: bool = False
    body_padding_top: int = 0
    body_padding_bottom: int = 0
    reserve_footer: bool = True
```

`body` is required because a page without body content is better represented by
a smaller static widget.

`header` is optional because some pages may only need a body and footer.

`footer` can be a fixed string or a callable. The callable receives
`PageScaffoldContext` and returns a string for the current focus state.

`theme` applies only to scaffold-owned chrome. It must not style child-rendered
header or body lines.

`body_padding_top` and `body_padding_bottom` add best-effort blank rows inside
the body region. Padding yields to at least one body row and to reserved footer
space when height is tight.

The supported scaffold theme tokens are:

- `widget.pageScaffold.separator`
- `widget.pageScaffold.footer`

## Focus Behavior

`focus()`:

- sets `focused=True`
- focuses `body` by default when `focus_region == "body"`
- focuses `header` when `focus_region == "header"`
- if requested region cannot focus, falls back to the other region when possible

`blur()`:

- sets `focused=False`
- blurs both header and body when they expose `blur()`

`focus_header()`:

- returns `False` if no focusable header exists
- blurs body
- focuses header
- sets `focus_region="header"`
- returns `True`

`focus_body()`:

- returns `False` if body cannot be focused
- blurs header
- focuses body
- sets `focus_region="body"`
- returns `True`

`editor_input_target()`:

- delegates only to the currently focused region
- normally this means `SearchableList.editor_input_target()` while body search
  is focused

## Input Behavior

If `focused=False`, `handle_input()` returns `None`.

When `focus_region == "header"`:

- if key is `down` or `enter`, attempt `focus_body()` and return `True` or
  `False`
- otherwise delegate input to header
- if header handles the event, return its result
- otherwise return `None`

This order is intentional. Primitive `Tabs` treats `enter` as activation, but
inside `PageScaffold` header focus, `enter` means "enter the page body",
matching `TabGroup` header behavior. A caller that needs header-level enter
activation should use a custom header/body composition instead of this first
version's default header/body focus contract.

When `focus_region == "body"`:

- delegate input to body first
- if body handles the event, return its result
- if key is `up` or `shift+tab`, attempt `focus_header()` and return `True` or
  `False`
- otherwise return `None`

This lets `SearchableList` keep its own search/list behavior:

- `up` from list first moves back to search inside `SearchableList`
- only an unhandled `up` from body search bubbles to `PageScaffold`, which can
  move focus to the header

## Rendering Behavior

`render()` must respect `RenderConstraints.width` and
`RenderConstraints.max_height`.

Line order:

1. header, if present
2. separator, if `separator_after_header=True` and header rendered at least one
   line
3. body
4. blank padding until footer can sit at the bottom, when `reserve_footer=True`
5. footer, if non-empty and height allows

Footer reservation:

- if `reserve_footer=True` and footer is non-empty, body gets at most
  `max_height - header_height - separator_height - 1`
- footer should still render when body content is long
- if height is too small, header/body take priority in that order and footer may
  be omitted

Cursor handling:

- if the focused delegated render result has a cursor, offset its row by the
  number of lines inserted before that region
- if both header and body somehow return cursors, prefer the currently focused
  region cursor
- if the focused region cursor would fall outside `max_height`, omit the cursor

Width handling:

- separator uses `-` repeated to the target width
- footer text is truncated with existing `truncate_to_width(..., ellipsis="")`
- body/header render with the full target width
- delegated header/body renders preserve `RenderConstraints.visible_height`
  from the scaffold render call

## Error Handling And Boundaries

`PageScaffold` should not raise when a slot does not expose focus, blur,
handle_input, or editor_input_target. It should use duck typing:

- call method only when callable
- treat missing render method as empty content for optional header
- body must be renderable; if body has no callable `render`, render one blank
  line rather than crashing

No slot should be recreated during render or focus changes. Page object state
must remain owned by the caller.

## New Example 53

Create `examples/tui/53_widgets_page_scaffold.py`.

The example demonstrates `PageScaffold` directly and must not replace example
52.

Suggested scenario:

- top header uses primitive `Tabs` with `Config`, `Models`, `Activity`
- app code switches the body object when header `Tabs` changes
- `Config` body is a `SearchableList(search_box=True, detail_column=...)`
- `Models` body can be a `SearchableList` with current/model metadata
- `Activity` body can be a static or simple nested widget; it does not need to
  prove `TabGroup` behavior again
- footer is a callable based on scaffold context:
  - header focus: `←/→ to switch · ↓ to enter · q to quit`
  - body focus: `Type to filter · ↑ to tabs · q to quit`

Example validation should prove:

- initial render starts in body focus
- `up` from body search moves to header
- left/right in header switches tabs through primitive `Tabs`
- down/enter from header moves back to body
- footer remains on the last visible line while the body list scrolls
- cursor row remains aligned with search/header focus and never drifts to the
  footer

## Tests

Create `tests/tui/test_widgets_page_scaffold.py`.

Unit tests must cover:

- renders body-only pages
- renders header, separator, body, and footer in stable order
- reserves footer height under long body content
- omits footer under tiny heights according to header/body/footer priority
- offsets body cursor after header and separator
- offsets header cursor without applying body offset
- `focus()` / `blur()` delegate to active slots
- `down` / `enter` from header focuses body when body can focus
- unhandled `up` / `shift+tab` from body focuses header
- handled body input is not stolen by scaffold
- `editor_input_target()` delegates only to current focused region
- footer callable receives context and changes output between header and body
  focus
- missing optional methods do not crash
- public exports from `loushang.tui`, `loushang.tui.ui_parts`, and
  `loushang.tui.ui_parts.widgets`

Example playback tests should cover `examples/tui/53_widgets_page_scaffold.py`:

- initial body focus
- up to header
- right to switch selected tab
- down back to body
- long-list footer stability
- no cursor below footer

## Documentation

After implementation, add PageScaffold to:

`docs/internals/architecture/tui/native-terminal-core/ui-parts/README.md`

Add a short internals page or section explaining that:

- `ScreenRegionStack` is screen-level region allocation
- `PageScaffold` is widget-level page layout and focus orchestration
- concrete product pages remain responsible for business state and actions

## Rollout

1. Add `PageScaffold` tests first.
2. Implement `page_scaffold.py` minimally.
3. Add public exports.
4. Add example 53 and playback tests.
5. Update internals docs.
6. Run focused tests, TUI tests, and lint.

## Open Decisions

Resolved: PageScaffold supports scaffold-owned chrome theme tokens for the
separator and footer. Header and body styling remain owned by child widgets.

Resolved: PageScaffold supports top and bottom body padding as a small layout
hook. It does not yet support title bands, fixed body regions, or specialized
search/footer widgets.

The first implementation should not add specialized `SearchBox`, `PageFooter`,
or `OverflowHint` widgets. `SearchableList` already covers boxed search and
overflow; footer can start as a string/callable. Those helpers can be added
later if repeated call sites justify them.
