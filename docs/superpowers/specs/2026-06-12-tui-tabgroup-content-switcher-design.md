# TUI TabGroup And ContentSwitcher Design

## Status

Draft for spec review.

This document is the temporary execution spec for the next TUI widget slice.
The long-term internal architecture document should live at:

`docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`

After implementation stabilizes, the durable architecture content should move
there, while this file can remain as the development record for the slice.

## Context

`loushang.tui` already has a useful widget catalog: buttons, choices, text
fields, forms, dialogs, menu, toolbar, tabs, table, textarea, tree view, toast,
and command palette view.

The current `Tabs` widget is a horizontal selected-value control. It renders a
single tab header row and supports left/right/home/end navigation. It does not
own the content area below the tabs, page focus, fixed-height page layout,
nested tabs, or long settings-style lists.

The next missing foundation is tabbed content:

- a tab header that chooses the active page
- a content canvas that renders exactly one page
- stable layout when pages have different heights
- page-local focus that can contain editors, lists, forms, charts, and nested
  tabs
- theme tokens that distinguish selected tabs at different nesting levels
- playback scenarios that prove the interaction model without copying another
  product's exact visual design

## Prior Art

### Existing Loushang Tabs

`src/loushang/tui/ui_parts/widgets/tabs.py` contains:

- `TabItem(value, label, disabled=False, badge="")`
- `Tabs(tabs, value="", wrap=True, on_change=None, theme=None, focused=False)`

This is the correct primitive for tab headers. It should remain small and should
not become a page container.

### Textual

Textual separates the same responsibilities into three layers:

- `Tabs`: selectable tab header
- `TabbedContent` / `TabPane`: tab header plus associated content panes
- `ContentSwitcher`: shows exactly one immediate child

The useful lesson is the split, not the DOM/reactive/message architecture.
Loushang should adopt the layered model while keeping terminal-pure renderables.

### Prompt Toolkit

Prompt Toolkit does not provide a high-level tabbed content widget, but it
separates container layout, controls, and focus tracking. The useful lesson is
that a tabbed widget should compose focusable content instead of becoming a
global focus manager.

### Claude Code Settings

Claude Code's settings screen demonstrates useful behavior:

- top-level tabs with page content below
- search field plus long filtered settings list
- arrow-key transitions between tab header, search, and list
- stable content height with overflow hints
- nested tabs under a stats page

Loushang should match or exceed these capabilities, but it does not need to
copy the exact settings fields, visual layout, colors, or text.

## Goals

- Add a reusable `TabGroup` for tabbed content.
- Keep the existing `Tabs` and `TabItem` primitive intact.
- Add a page model that binds a tab item to a renderable page.
- Render exactly one selected page at a time.
- Support fixed-height content canvases so tab switching does not move footers.
- Support recursive composition for nested tabs.
- Explicitly model focus between tab header and selected page content.
- Distinguish tab state with semantic theme tokens, including nested levels.
- Support settings-style pages with long searchable lists through composable
  page content.
- Emit structured events for tab changes and page-level actions.
- Add playback scenarios for tab switching, nested tabs, filtering, long list
  scrolling, and focus transitions.

## Non-Goals

- Do not replace `Tabs` with a large retained widget.
- Do not add a Textual-style DOM, CSS system, reactive property model, or
  message bus.
- Do not add a Prompt Toolkit-style global `Layout` focus stack.
- Do not make `TabGroup` responsible for arbitrary long-list virtualization.
- Do not copy Claude Code's settings visual design or exact settings data.
- Do not require mouse support in the first slice.
- Do not support draggable tabs, closable tabs, tab reordering, lazy async page
  loading, or dynamic add/remove in the first slice.
- Do not make unlimited tab nesting a primary UX. Recursive composition should
  work, but first-class playback coverage should focus on levels 0 and 1.

## Terminology

- `Tabs`: existing horizontal selected-value tab header primitive.
- `TabGroup`: composed widget that owns a tab header and selected page content.
- `TabPage`: data object that binds a tab value/label to page content.
- `ContentSwitcher`: small helper that renders the selected content and applies
  fixed-height clipping or padding.
- `Header focus`: the tab header handles navigation keys.
- `Content focus`: the selected page handles input first.
- `Level`: nesting depth for visual semantics. Top-level tabs are level 0,
  nested tabs are level 1, and advanced nested tabs may use level 2.

## Proposed Public API

Add `src/loushang/tui/ui_parts/widgets/tab_group.py`.

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.widgets.tabs import TabItem


@dataclass(frozen=True, slots=True)
class TabPage:
    value: str
    label: str
    content: object
    disabled: bool = False
    badge: str = ""


@dataclass(slots=True)
class TabGroup:
    pages: Sequence[TabPage]
    value: str = ""
    level: int = 0
    wrap: bool = True
    content_height: int | None = None
    focused: bool = False
    header_focused: bool = True
    on_change: Callable[[str], object] | None = None
    theme: ThemeResolver | None = None
```

The public surface should expose:

- `selected_value -> str`
- `selected_page -> TabPage | None`
- `focus() -> None`
- `blur() -> None`
- `focus_header() -> None`
- `focus_content() -> bool`
- `handle_input(event) -> object`
- `editor_input_target() -> EditorInputTarget | None`
- `render(constraints) -> RenderResult`

`content` is intentionally typed as `object` in the dataclass sketch because
existing UI parts use structural render/focus protocols rather than a single
nominal base class. Implementation should use local helpers to detect:

- `render(constraints)`
- `handle_input(event)`
- `focus()`
- `blur()`
- `editor_input_target()`

## Component Boundaries

### Tabs Remain Primitive

`Tabs` should continue to render one line and own only selected-value navigation.
It may receive theme-token improvements to support selected/header/content
states, but it should not learn about page content.

### TabGroup

`TabGroup` owns:

- normalization of selected page value
- header/content focus state
- construction or synchronization of an internal `Tabs` header
- delegation of selected-page rendering
- delegation of selected-page input when content has focus
- structured tab-change results from `on_change`

`TabGroup` does not own:

- list filtering
- list scrolling
- arbitrary page data models
- global focus routing
- overlay lifecycle

### ContentSwitcher

`ContentSwitcher` is a small internal or public helper that renders one selected
content object. It should be deterministic and terminal-pure.

Responsibilities:

- render the selected content
- apply width and height constraints
- pad short content to a fixed content height when requested
- clip long content to the fixed height when requested
- optionally surface overflow counts through helper functions or page-level
  render conventions

Non-responsibilities:

- keyboard handling
- focus routing
- page state creation or destruction

### Settings-Style Long Lists

Long settings lists should be implemented by a page content widget such as
`SearchableList` or `SettingsList`, not by `TabGroup` itself.

That page content should own:

- query text
- filtered items
- active row
- scroll offset
- viewport slicing
- overflow hints
- row activation intents

This keeps `TabGroup` reusable for pages that are not lists.

## Focus Model

`TabGroup` has two focus layers:

- group focus: whether the group is active in a larger surface
- header/content focus: which part of the group handles input

When `focused=False`, the group renders selected state without active focus
tokens and does not consume navigation keys.

When `focused=True` and `header_focused=True`:

- `left` / `right` move between enabled tabs
- `home` / `end` jump to the first or last enabled tab
- `down` attempts to focus selected page content
- `enter` also attempts to focus selected page content when the content is
  focusable; otherwise it returns the selected value or tab-change callback
  result according to existing `Tabs` semantics

When `focused=True` and `header_focused=False`:

- input is delegated to selected page content first
- if delegated content returns a non-`None` result, the group returns it
- `up` may return to the header when selected content does not consume it
- `shift+tab` may return to the header when supported by the event normalizer
- `ctrl+tab` and `ctrl+shift+tab` are reserved for future global tab cycling
  and should not be required in the first slice

Selected page content receives `focus()` when content focus enters and `blur()`
when content focus leaves or the group loses focus.

When switching pages:

- blur the old selected content if content focus is active
- update the selected value
- focus the new selected content if content focus is active and it supports
  focus
- preserve page object state; do not recreate page content

## Nested TabGroups

`TabGroup` should support recursive composition because a page can contain
another `TabGroup`.

Recommended UX:

- level 0 and level 1 are normal
- level 2 is technically supported for advanced screens
- deeper nesting is discouraged

Focus traversal is recursive:

```text
level 0 header
  level 0 content
    level 1 header
      level 1 content
        level 2 header
          level 2 content
```

`up` from content returns to the current level header. `up` from a nested header
can bubble to the parent content, allowing the parent to move focus back to its
own header when appropriate. The first implementation should verify top-level
and one nested level with playback. Level 2 can rely on API and theme fallback
coverage unless a product screen requires it.

## Theme Tokens

Two-level tab coloring must be semantic, not only indentation-based. The theme
resolver should support state and level.

Suggested tokens:

```text
widget.tabs.level0.normal
widget.tabs.level0.selected_content_focus
widget.tabs.level0.selected_header_focus
widget.tabs.level0.disabled

widget.tabs.level1.normal
widget.tabs.level1.selected_content_focus
widget.tabs.level1.selected_header_focus
widget.tabs.level1.disabled

widget.tabs.level2.normal
widget.tabs.level2.selected_content_focus
widget.tabs.level2.selected_header_focus
widget.tabs.level2.disabled
```

Fallback tokens:

```text
widget.tabs.nested.normal
widget.tabs.nested.selected_content_focus
widget.tabs.nested.selected_header_focus
widget.tabs.nested.disabled
widget.tabs.normal
widget.tabs.selected
widget.tabs.focus
widget.tabs.disabled
```

Rules:

- top-level tabs should read stronger than nested tabs
- nested tabs should use indentation plus weaker semantic colors
- only one tab header in the active focus path should use a
  `selected_header_focus` token at a time
- a parent selected tab should use `selected_content_focus` when focus is inside
  a child tab group
- disabled tabs should remain visible but skipped by navigation

Example state matrix:

```text
Focus at top-level header:
  level0 Stats -> selected_header_focus
  level1 Overview -> selected_content_focus or normal, never header focus

Focus at nested header:
  level0 Stats -> selected_content_focus
  level1 Overview -> selected_header_focus

Focus inside nested content:
  level0 Stats -> selected_content_focus
  level1 Overview -> selected_content_focus
```

## Long List Requirements

Settings-style tab pages must support long logical lists while rendering only a
bounded visible slice.

The long-list page content should provide:

- `items`: logical item list, potentially hundreds of rows
- `query`: text filter state
- `filtered_items`: filtered logical list
- `active_index`: selected item within `filtered_items`
- `scroll_offset`: first visible filtered item index
- `max_visible`: visible row count derived from the content canvas height
- `more_above` and `more_below` counts

Behavior:

- blank query shows all items in stable original order
- non-blank query filters case-insensitively
- filtering preserves original order unless a future fuzzy scorer is explicitly
  introduced
- after filtering, clamp active index and scroll offset
- for an empty result, render a stable empty state such as
  `No settings match "query"`
- `down` moves active row and scrolls when active row reaches the viewport
  bottom
- `up` moves active row; when the active row is the first visible item and
  scroll offset is zero, `up` can return focus to the search field
- `pagedown` and `pageup` move by a viewport
- `home` and `end` jump to list boundaries when the list has focus
- switching away from and back to the tab preserves query, active row, and
  scroll offset because page content objects are persistent

Hard requirement:

```text
logical list length must not imply rendered line count
```

A page with 200 settings should still render only the content canvas height.

## Settings-Style Example

Add or update an example that demonstrates capability without copying another
product's visual design.

Suggested page set:

```text
Workspace   Models   Permissions   Activity
```

Suggested `Workspace` page:

```text
Search settings...

Default model             kimi-for-coding
Approval mode             confirm
Theme                     system
Compact history           true
```

Suggested `Activity` page with nested tabs:

```text
Overview   Models

tokens/day chart or dense summary rows
```

The example should exercise:

- top-level tab switching
- search field focus
- long settings list focus and scrolling
- nested tab switching
- fixed-height content canvas
- footer stability

## Structured Events

`TabGroup` should return structured data when it has a semantic action. It can
use callbacks first, and only add global `InputIntentKind` values if a concrete
surface integration needs them.

Initial event shape can be a small dataclass local to the widget module:

```python
@dataclass(frozen=True, slots=True)
class TabChange:
    value: str
    previous_value: str
    level: int = 0
```

If `on_change` is provided, `TabGroup` should return the callback result. If no
callback is provided, it may return `TabChange` for a selected-value change or
`True` for consumed focus movement. This should be decided in implementation
planning based on existing widget conventions.

Page content such as `SettingsList` can return its own structured events, for
example:

```python
@dataclass(frozen=True, slots=True)
class SettingSelect:
    key: str
    label: str
    value: object
```

`TabGroup` should pass page-level events through unchanged.

## Rendering Rules

- Header consumes exactly one rendered line.
- A blank spacer line between header and content is optional and controlled by
  the composed example or a `header_gap` parameter only if needed.
- Content width equals the incoming width unless the caller indents the group
  externally.
- Content height is:
  - remaining height when `content_height is None`
  - `min(content_height, remaining height)` when fixed
- Fixed content height pads short content with blank lines.
- Fixed content height clips long content to the visible height.
- Footer lines should be owned by the page or parent surface, not by
  `TabGroup`, unless a later product-specific shell composes them.
- Rendering should never write to stdout, move the hardware cursor, or depend
  on terminal scrollback.

## Playback Scenarios

### 1. Initial Settings Page

Initial state:

- top-level tabs render
- selected page is `Workspace` or `Config`
- focus is inside the page search field
- selected top-level tab uses `selected_content_focus`
- search field uses focused style
- visible settings rows render
- footer line stays at a stable row

Assertions:

- header text is present
- selected top-level tab token is not header-focused
- search field is focused
- list has no active row until `down`

### 2. Query Filters A Single Item

Input:

```text
m o d e l
```

Assertions:

- query text is `model`
- filtered rows contain only matching items
- search still has focus
- selected tab and footer remain stable

### 3. Query Filters Multiple Items

Input:

```text
m o d e
```

Assertions:

- matching rows preserve stable order
- no non-matching row is rendered
- active row is clamped to the first match if the list owns active selection

The matching rule should be explicit in tests. The first implementation should
use case-insensitive substring matching over labels and keys. Fuzzy scoring can
be a later slice.

### 4. Search Down Enters List

Input:

```text
down
```

Assertions:

- focus moves from search to list
- first visible row is active
- search loses focus style
- selected top-level tab remains `selected_content_focus`

### 5. First List Row Up Returns To Search

Input:

```text
up
```

Assertions:

- focus returns to search
- list active cursor clears or becomes inactive according to list design
- footer returns to search-context hints

### 6. Search Up Returns To Top-Level Tabs

Input:

```text
up
```

Assertions:

- focus moves to top-level header
- selected top-level tab uses `selected_header_focus`
- page content remains unchanged

### 7. Top-Level Tab Switching

Input:

```text
right
right
left
```

Assertions:

- selected top-level value changes correctly
- only one top-level tab has selected state
- content switches to the selected page
- footer row remains stable

### 8. Nested Tabs

State:

- top-level `Activity` or `Stats` page is selected
- content contains nested `Overview` and `Models` tabs

Assertions:

- parent selected tab uses `selected_content_focus`
- nested selected tab uses nested-level tokens
- focus at nested header uses nested `selected_header_focus`
- switching nested tabs does not change the top-level selected value

### 9. Long List Initial Viewport

State:

- page has 200 logical settings
- content canvas can show 12 rows

Assertions:

- only visible rows render
- `more below` count is correct
- offscreen rows are not present in the rendered frame

### 10. Long List Scrolling

Input:

```text
down repeated past the visible viewport
```

Assertions:

- active row remains visible
- scroll offset increases
- `more above` and `more below` counts update
- footer row remains stable

### 11. PageUp And PageDown

Input:

```text
pagedown
pageup
end
home
```

Assertions:

- active row and scroll offset move by expected amounts
- movement clamps at boundaries
- no rendered frame exceeds the content canvas height

### 12. Long List State Preserved Across Tabs

Input:

```text
scroll to row 40
switch to Activity
switch back to Workspace
```

Assertions:

- query is preserved
- active row is preserved
- scroll offset is preserved
- page content object was not recreated

## Testing Plan

Unit tests:

- `TabPage` normalization into header `TabItem` values
- `TabGroup` selected-value normalization
- disabled tabs skipped by header navigation
- header/content focus transitions
- selected content input delegation
- selected content `editor_input_target()` delegation
- fixed content height pads short pages
- fixed content height clips long pages
- nested level theme token selection

Playback tests:

- settings-style example initial render
- search filtering
- search/list/header focus transitions
- top-level tab switching
- nested tab switching
- long-list scrolling and viewport bounds
- state preservation across tab switches

Regression tests:

- existing `Tabs` tests remain valid
- existing widget examples render unchanged unless intentionally updated
- command palette, table, tree, textarea, dialog, and toast tests remain green

## Implementation Phases

### Phase 1: Core Tabbed Content

- add `TabPage`
- add `ContentSwitcher`
- add `TabGroup`
- reuse existing `Tabs`
- add unit tests for rendering, selection, fixed height, and focus transition

### Phase 2: Theme Semantics And Nested Tabs

- add level-aware tab theme token resolution
- add nested `TabGroup` tests
- update reference docs for tab state tokens

### Phase 3: Settings-Style Long List Example

- add or update a runnable example with search, long list, top-level tabs, and
  nested tabs
- add playback tests for the scenario matrix
- document manual verification steps

### Phase 4: Internal Architecture Migration

- move stable architecture guidance into
  `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`
- update the UI part inventory
- keep this superpowers spec as the development record

## Open Questions

- Should the public name be `TabGroup` / `TabPage`, or should it mirror Textual
  with `TabbedContent` / `TabPane`? This spec recommends `TabGroup` / `TabPage`
  because it matches the user's vocabulary and keeps `Tabs` as the primitive.
- Should first-slice `TabGroup` return a `TabChange` dataclass by default, or
  only return callback results and `True` for consumed navigation? This should
  follow existing widget conventions during implementation planning.
- Should long-list support be a reusable `SearchableList` widget in the same
  PR, or should the first PR add `TabGroup` only and use a small example-local
  page object? This spec recommends `TabGroup` first, then a long-list page
  widget if the implementation stays small enough.
