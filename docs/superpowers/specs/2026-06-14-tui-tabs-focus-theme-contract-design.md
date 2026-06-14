# TUI Tabs Focus And Theme Contract Design

## Status

Draft for spec review.

This is a TUI-lane design for hardening the reusable `Tabs` and `TabGroup`
visual/focus contract. It intentionally avoids product behavior in
`src/loushang/coding/...` so the code lane can continue the real `/settings`
status-line work without merge pressure.

## Package Scope

Primary implementation scope:

- `src/loushang/tui/ui_parts/widgets/tabs.py`
- `src/loushang/tui/ui_parts/widgets/tab_group.py`

Primary validation scope:

- `tests/tui/test_widgets_light_controls.py`
- `tests/tui/test_widgets_tab_group.py`
- `tests/tui/widget_example_playback.py`
- `examples/tui/52_widgets_tabgroup_searchable_list.py`
- `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`

No product settings implementation should be added in this slice.

## Problem

Recent settings-style TUI work exposed ambiguous tab states:

- selected top-level tabs were sometimes not visually highlighted
- `>` was used as both a selected-page marker and a focus marker
- parent and child `TabGroup` headers could both appear focused
- spacing around the focus marker could drift into forms like `> [Config]`
- level-aware theme tokens were documented but only partially locked by tests

The result is confusing in settings pages: a user cannot reliably tell whether
arrow keys will switch tabs or whether focus is inside search/list/page content.

## Goals

- Define the exact tab visual states for selected page and header focus.
- Make `>` mean only "keyboard focus is on this tab header".
- Keep the selected page visible when focus is inside the page content.
- Preserve colorless readability by keeping a selected marker for non-header
  focus.
- Lock level-aware theme-token fallback, including legacy `widget.tabs.tab`.
- Verify nested `TabGroup` focus with level 0 and level 1 coverage.
- Verify level 2 as synthetic unit-test coverage for marker and theme fallback
  only; product examples do not need a three-level tab hierarchy.
- Keep the rendered marker width stable so navigation does not shift layout.

## Non-Goals

- Do not implement the real Status Line settings tab.
- Do not add `/config` or `/settings` command behavior.
- Do not extract a full reusable settings page scaffold yet.
- Do not introduce a global theme registry.
- Do not redesign all widget theme APIs.
- Do not require product pages to use three-level tab groups.

## Vocabulary

`selected page` means the tab whose content is currently displayed.

`header focus` means keyboard input is currently handled by the tab header, so
left/right/home/end operate on tabs.

`content focus` means keyboard input is inside the selected page content, such
as a search box, list, nested tab group, or static page.

`selected highlight` means the current page is visually identified even when
the tab header does not have focus.

`focus highlight` means the selected tab header is currently the keyboard
target.

## State Model

Each enabled tab renders in exactly one of these states:

| State | Meaning | Marker | Required theme state |
| --- | --- | --- | --- |
| `normal` | Enabled, not selected | space | normal |
| `selected_unfocused` | Selected, but this `TabGroup` is not focused | `*` | selected |
| `selected_content_focus` | Selected, focus is inside this page content | `*` | selected content focus |
| `selected_header_focus` | Selected, focus is on this tab header | `>` | selected header focus |
| `disabled` | Disabled, visible, skipped by navigation | space | disabled |

The marker is a fixed one-cell prefix immediately before the bracketed label:

```text
>[Config]
*[Config]
 [Config]
```

There must be no space between `>` or `*` and `[Label]`. The spacing between tab
segments remains controlled by the existing inter-tab separator.

The marker is not the only visual signal. Theme styling must provide the richer
selected/focused distinction, while the marker keeps the state readable when
colors are unavailable or stripped by tests.

## Marker Contract

`>` is reserved for `selected_header_focus`.

`*` is reserved for selected states that are not header-focused:

- `selected_unfocused`
- `selected_content_focus`

A selected tab must never render as plain unselected text unless a future
explicit visual variant opts out of markers. This slice does not add that
variant.

Disabled selected tabs cannot exist after value normalization. If a requested
value points at a disabled tab, selection normalizes to the next enabled tab or
the first enabled tab.

## Focus Matrix

For a single top-level `TabGroup`:

| Focus location | Selected tab marker | Selected tab token |
| --- | --- | --- |
| group blurred | `*` | `widget.tabs.selected` |
| header focused | `>` | `widget.tabs.level0.selected_header_focus` fallback chain |
| page content focused | `*` | `widget.tabs.level0.selected_content_focus` fallback chain |

For nested tab groups:

```text
Focus at level 0 header:
  level0 selected -> selected_header_focus, marker >
  level1 selected -> selected_unfocused, marker *, never header focus

Focus at level 1 header:
  level0 selected -> selected_content_focus, marker *
  level1 selected -> selected_header_focus, marker >

Focus inside level 1 content:
  level0 selected -> selected_content_focus, marker *
  level1 selected -> selected_content_focus, marker *
```

Only one `TabGroup` in the active focus path may render
`selected_header_focus` at a time.

Primitive `Tabs.selected_focus` maps to render states as follows:

| `selected_focus` | `focused` | Render state |
| --- | --- | --- |
| `auto` | `False` | `selected_unfocused` |
| `auto` | `True` | `selected_header_focus` |
| `header` | any | `selected_header_focus` |
| `content` | any | `selected_content_focus` |
| `none` | any | `selected_unfocused` |

## Theme Token Contract

The theme system already merges multiple token styles from left to right, with
later tokens overriding earlier ones. The tab renderer must use that behavior
as the fallback contract.

For enabled unselected tabs at `level = N`, resolve:

```text
widget.tabs.tab
widget.tabs.normal
widget.tabs.nested.normal        # only when level > 0
widget.tabs.levelN.normal
```

For `selected_unfocused`, resolve:

```text
widget.tabs.selected
widget.tabs.nested.selected      # only when level > 0, if added later
widget.tabs.levelN.selected      # if added later
```

This slice does not require adding `widget.tabs.nested.selected` or
`widget.tabs.levelN.selected`. `widget.tabs.selected` remains sufficient for
blurred selected tabs unless a later visual design needs level-specific blurred
selection styling.

For `selected_content_focus`, resolve:

```text
widget.tabs.selected
widget.tabs.nested.selected_content_focus   # only when level > 0
widget.tabs.levelN.selected_content_focus
```

For `selected_header_focus`, resolve:

```text
widget.tabs.selected
widget.tabs.focus
widget.tabs.nested.selected_header_focus    # only when level > 0
widget.tabs.levelN.selected_header_focus
```

For disabled tabs at `level = N`, resolve:

```text
widget.tabs.disabled
widget.tabs.nested.disabled       # only when level > 0
widget.tabs.levelN.disabled
```

`widget.tabs.tab` is the legacy public token for normal enabled tabs and must
remain in the fallback chain. A theme that only customizes `widget.tabs.tab`
must still style unselected tabs.

## Interaction Contract

Primitive `Tabs`:

- left/right/home/end move the selected enabled tab when focused
- enter/space return the selected value
- disabled tabs remain visible but are skipped by navigation
- render selected state even when not focused
- remain caller-dispatched: primitive `Tabs.handle_input()` continues to process
  events when called directly, even if `focused=False`; containers decide when
  to route input to a `Tabs` instance

`TabGroup`:

- when `focused=False`, it renders selected state but does not consume input
- when `header_focused=True`, left/right/home/end switch tabs
- down/enter from header attempts to focus selected page content
- when content is focused, input is delegated to selected page content first
- up/shift+tab from content returns to the current tab header if content does
  not consume the event
- switching tabs while content is focused blurs old content, changes value, and
  focuses new content when possible

Nested `TabGroup` content follows the same rules recursively.

## Example Rendering

Top-level header focus:

```text
 [Status]  >[Config]   [Model]   [Usage]   [Stats]
```

Top-level content focus inside the selected Config page:

```text
 [Status]  *[Config]   [Model]   [Usage]   [Stats]
```

Nested header focus inside Stats:

```text
 [Status]   [Config]   [Model]   [Usage]  *[Stats]
>[Overview]   [Models]
```

Nested content focus inside Stats / Models:

```text
 [Status]   [Config]   [Model]   [Usage]  *[Stats]
 [Overview]  *[Models]
```

Theme colors should make these states stronger than the plain examples show.

## Testing Requirements

Unit tests must cover:

- primitive `Tabs` selected markers for blurred, header-focused, and
  content-focus override states
- `>` never appears for `selected_content_focus`
- selected state remains visible when `TabGroup` content is focused
- level 0 and level 1 selected header/content focus token resolution
- synthetic level 2 marker and token fallback resolution
- legacy `widget.tabs.tab` still styles normal tabs
- disabled tabs are visible, styled, and skipped
- marker spacing has no gap between marker and bracket
- width truncation still respects visible width with ANSI styling

Nested `TabGroup` tests must cover:

- focus at parent header
- focus at child header
- focus inside child content
- only one selected tab renders `>` across the nested active path
- parent selected tab renders content-focus state while child has focus

Playback tests must cover:

- `examples/tui/52_widgets_tabgroup_searchable_list.py` initial content focus
- up from search to top-level tabs
- down from tabs back to search/content
- switching to Activity and entering nested tabs
- nested tab header focus shows `>` only on the nested selected tab
- footer and long-list layout do not move during focus transitions

## Documentation Requirements

After implementation, promote the stable contract to:

`docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`

The superpowers spec may remain as historical design input, but long-term
documentation should live under `docs/internals`.

## Implementation Notes

This design likely requires a small change in `tabs.py`: content-focus selected
tabs should no longer use the same `>` marker as header-focused tabs.

The public `Tabs.selected_focus` values can remain:

- `auto`
- `header`
- `content`
- `none`

The renderer should map them to the state model above. No new public API is
required for this slice.

## Rollout

1. Add focused unit tests for marker and token semantics.
2. Adjust `Tabs` rendering to satisfy the state matrix.
3. Add nested `TabGroup` focus-path tests.
4. Refresh the tabgroup searchable-list playback assertions.
5. Update internals documentation after tests pass.

## Open Decision

This design keeps `*` as the selected non-header marker for colorless
readability and backward compatibility. If product UX later wants CC-like
markerless selected tabs, that should be a separate visual variant rather than
silently changing the base contract.
