# TabGroup And SearchableList UI Parts

## Purpose

`TabGroup` composes a tab header with persistent page content. `SearchableList`
provides a reusable searchable long-list page widget. `ContentSwitcher` remains
an internal helper for fixed-height selected-content rendering.

## Inputs And State

- `TabPage(value, label, content, disabled=False, badge="")`
- `TabGroup(pages, value="", level=0, content_height=None, focused=False)`
- `SearchableListItem(key, label, value="", description="", disabled=False)`
- `SearchableList(items, query="", focus_region="search", focused=False)`

## Render Constraints

Both widgets must respect `RenderConstraints.width` and
`RenderConstraints.max_height`. Long logical lists render only the visible slice.

## Focus Behavior

`TabGroup` switches between header focus and selected content focus.
`SearchableList` switches between search focus and list focus.

## Events

`TabGroup` value changes return a local structured tab-change object unless an
`on_change` callback is supplied. `SearchableList` activation returns
`SearchableListSelect` unless `on_select` is supplied.

## Theme Tokens

Tab theme resolution must preserve legacy `widget.tabs.tab` fallback while
supporting level-aware selected header/content focus tokens.

## Test Obligations

Unit tests cover selection, focus, fixed-height rendering, nested tabs,
search/filter repair, viewport scrolling, disabled items, and exports. Playback
tests cover settings-style search, nested tabs, long-list scroll keys, footer
stability, and state preservation across tab switches.
