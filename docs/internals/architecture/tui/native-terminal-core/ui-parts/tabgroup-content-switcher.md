# TabGroup And Content Switcher UI Parts

## Purpose

`TabGroup` composes a tab header with persistent page content.
`ContentSwitcher` remains an internal helper for fixed-height selected-content
rendering. Searchable long-list content is covered by
[SearchableList](./searchable-list.md).

## Inputs And State

- `TabPage(value, label, content, disabled=False, badge="")`
- `TabGroup(pages, value="", level=0, content_height=None, focused=False)`

## Render Constraints

Both widgets must respect `RenderConstraints.width` and
`RenderConstraints.max_height`. Long logical lists render only the visible slice.

## Focus Behavior

`TabGroup` switches between header focus and selected content focus. When a
selected content widget returns `None` for upward navigation, the parent
TabGroup can move focus back to the tab header.

## Tab Marker Contract

Tabs reserve one fixed marker cell before the bracketed label:

| Marker | Meaning |
| --- | --- |
| `>` | selected tab header has keyboard focus |
| `*` | selected tab page is current, but header is not focused |
| space | enabled normal tab or disabled tab |

The marker is immediately adjacent to the label, so `>[Config]` and
`*[Config]` are valid while `> [Config]` is not.

## Tab Focus States

`Tabs.selected_focus` maps to rendering as:

| `selected_focus` | `focused` | Render state |
| --- | --- | --- |
| `auto` | `False` | selected unfocused |
| `auto` | `True` | selected header focus |
| `header` | any | selected header focus |
| `content` | any | selected content focus |
| `none` | any | selected unfocused |

Only one `TabGroup` in a nested active focus path should render `>`.

## Events

`TabGroup` value changes return a local structured tab-change object unless an
`on_change` callback is supplied. Selected content owns its own structured
intents; for SearchableList content, see [SearchableList](./searchable-list.md).

## Theme Tokens

Tab theme resolution must preserve legacy `widget.tabs.tab` fallback while
supporting level-aware selected header/content focus tokens.

Normal tabs preserve legacy `widget.tabs.tab`, then apply newer and
level-specific tokens:

```text
widget.tabs.tab
widget.tabs.normal
widget.tabs.nested.normal
widget.tabs.levelN.normal
```

Selected header focus uses:

```text
widget.tabs.selected
widget.tabs.focus
widget.tabs.nested.selected_header_focus
widget.tabs.levelN.selected_header_focus
```

Selected content focus uses:

```text
widget.tabs.selected
widget.tabs.nested.selected_content_focus
widget.tabs.levelN.selected_content_focus
```

## Test Obligations

Unit tests cover selection, focus, fixed-height rendering, nested tabs,
search/filter repair, viewport scrolling, disabled items, and exports. Playback
tests cover settings-style search, nested tabs, long-list scroll keys, footer
stability, and state preservation across tab switches.
