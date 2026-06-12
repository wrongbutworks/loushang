# TUI Widgets P2A Command Palette Design

## Status

Draft for spec review.

## Context

`loushang.tui` now has a practical widget catalog: forms, dialogs, toolbar,
menu, tabs, table, textarea, question dialog, tree view, toast, and polished
examples for widgets `43-50`.

The next missing layer is a reusable searchable action picker. Product code
already has command/model palette data in `loushang.tui.compat`:

- `CommandPaletteItem(value, label="", description="")`
- `CommandPalette(items, title="Commands")`
- `CommandPalette.from_completion_provider(...)`

That existing type is a data transfer object used by coding UI adapters. It is
not a renderable widget. P2A should add a focusable widget around that data
shape without breaking the existing chooser contract.

## Goals

- Add a reusable command palette widget for searchable command/model/action
  selection.
- Reuse existing `CommandPalette` and `CommandPaletteItem` data objects instead
  of inventing an incompatible item model.
- Preserve existing top-level `loushang.tui.CommandPalette` semantics for
  coding UI chooser tests and adapters.
- Support case-insensitive substring filtering over item value, label, and
  description.
- Support keyboard navigation over filtered results with disabled items skipped.
- Return structured selection/cancel intents instead of requiring callers to
  parse rendered text.
- Keep the widget terminal-pure: no stdout writes, no hardware cursor moves, no
  overlay opening, no scheduling, and no global key registration.
- Add focused tests, docs, and a runnable example.

## Non-Goals

- Do not replace `compat.CommandPalette` with a mutable renderable class.
- Do not remove or rename the existing top-level `CommandPalette` export.
- Do not add fuzzy scoring, ranking weights, highlighting matched characters, or
  tokenized query parsing in this slice.
- Do not add async item loading or provider refresh.
- Do not add multi-select.
- Do not add nested groups, command categories, icons, shortcut columns, or
  preview panes.
- Do not add a `Tui.show_command_palette()` helper or any automatic
  `SurfaceHost` integration.
- Do not change coding command/model workflows in the first PR. They can adopt
  the widget in a later integration slice.

## Naming And Compatibility

Because `loushang.tui.CommandPalette` already exists as a frozen data object,
the first widget should use a distinct name:

```python
CommandPaletteView(...)
```

This avoids a breaking API replacement while still making the relationship
clear:

- `CommandPalette` remains the data model.
- `CommandPaletteItem` remains the item model.
- `CommandPaletteView` is the renderable/focusable UI part.

`CommandPaletteItem` should gain a backward-compatible `disabled: bool = False`
field. Existing construction and equality tests that omit the field still pass
because the default is stable.

## Public API

Add `src/loushang/tui/ui_parts/widgets/command_palette.py`.

```python
from collections.abc import Sequence
from dataclasses import dataclass

from loushang.tui import CommandPalette, CommandPaletteItem
from loushang.tui.input import InputIntent
from loushang.tui.theme import ThemeResolver
from loushang.tui.ui_parts.text_input import TextInput


@dataclass(slots=True, init=False)
class CommandPaletteView:
    _items: tuple[CommandPaletteItem, ...]
    _title: str
    _query_input: TextInput
    placeholder: str = "Search commands"
    max_visible: int = 8
    empty_text: str = "No commands"
    close_on_select: bool = True
    close_on_cancel: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False

    def __init__(
        self,
        palette: CommandPalette | Sequence[CommandPaletteItem],
        *,
        title: str | None = None,
        placeholder: str = "Search commands",
        query: str = "",
        max_visible: int = 8,
        empty_text: str = "No commands",
        close_on_select: bool = True,
        close_on_cancel: bool = True,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None: ...
```

The constructor accepts either an existing `CommandPalette` object or a sequence
of `CommandPaletteItem` values:

- When passed a `CommandPalette`, copy `palette.items` into private `_items`.
  Use `palette.title` when `title is None`; use the supplied title otherwise,
  including an explicitly blank `title=""`.
- When passed a sequence, normalize it into private `_items`. Use
  `"Command Palette"` when `title is None`; use the supplied title otherwise,
  including an explicitly blank `title=""`.

`CommandPaletteView` should not keep the original `palette` object as public
mutable state. The widget owns a private item tuple and private title string so
render/input behavior is deterministic after construction.

The public surface should expose:

- `focus() -> None`
- `blur() -> None`
- `title -> str`
- `query -> str`
- `filtered_items -> tuple[CommandPaletteItem, ...]`
- `active_value -> str`
- `set_query(query: str) -> None`
- `handle_input(event) -> object`
- `editor_input_target() -> EditorInputTarget | None`
- `render(constraints) -> RenderResult`

`editor_input_target()` should delegate to an internal `TextInput` or
`TextField` adapter instead of forking text editing behavior.

`query` is a read-only property backed by the internal editor. The internal
editor is the single source of truth for query text. Constructor `query` and
`set_query()` both update that editor, then repair the active result. Tests
should not mutate a public `query` field because no such field exists.

## Intents

Add two `InputIntentKind` values:

- `command_select`
- `command_cancel`

Selection returns an `InputIntent`:

```python
InputIntent(kind="command_select", text=item.value, note=item.display_label())
```

Cancel returns:

```python
InputIntent(kind="command_cancel")
```

When `close_on_select=True`, selection returns:

```python
(
    InputIntent(kind="command_select", text=item.value, note=item.display_label()),
    InputIntent(kind="surface_close"),
)
```

When `close_on_cancel=True`, cancel returns:

```python
(
    InputIntent(kind="command_cancel"),
    InputIntent(kind="surface_close"),
)
```

This mirrors `QuestionDialog`, where a semantic intent can be paired with a
surface close intent. Embedded callers can set the close flags to `False`.
`SurfaceHost` already handles tuple intent returns. Coding `NativeSurfaceView`
does not currently flatten tuple returns, which is acceptable because coding UI
adoption is explicitly outside P2A.

## Filtering

Filtering is intentionally simple in P2A.

Normalize the query with `casefold().strip()`. A blank query matches all items.
For a non-blank query, an item matches if the normalized query is a substring of
any of:

- `item.value`
- `item.display_label()`
- `item.description`

Filtering preserves original item order. It does not sort or score matches.

Disabled items remain visible when they match, but navigation skips them and
activation ignores them. In P2A, `disabled` is honored only by
`CommandPaletteView`. Existing coding UI adapters that convert
`CommandPaletteItem` to legacy `SelectItem` keep their current behavior and do
not gain disabled selection semantics in this slice.

## Active Result Repair

`CommandPaletteView` owns a local active result index within filtered results.

Rules:

- Initial active item is the first enabled filtered item.
- `up/down` move among enabled filtered items.
- `ctrl+home` and `ctrl+end` jump to the first and last enabled filtered item.
- If `query` changes and the previous active item remains enabled and visible,
  keep it active.
- If the previous active item disappears or becomes disabled, move to the first
  enabled filtered item.
- If there are no enabled filtered items, `active_value == ""` and activation
  consumes nothing.

No-match and all-disabled states should be deterministic and renderable.

## Input Handling

`CommandPaletteView` is a single focus target. There is no separate tab stop for
the query and result list in P2A.

Input behavior:

| Input | Behavior |
| --- | --- |
| text / paste | Insert into query through the internal editor target. |
| backspace/delete/left/right/home/end/cursor editing | Delegate to the internal editor target. |
| up/down | Move active result. |
| ctrl+home / ctrl+end | Jump to the first/last enabled result. |
| enter | Select active enabled result. |
| escape / esc / ctrl+c | Cancel. |

If the internal editor target consumes input and changes query text, repair the
active result after the edit.

Plain `home` and `end` belong to query editing. They must not also navigate
result rows because the existing `TextInput` consumes line-start and line-end
editing keys even when the cursor position does not change.

Printable space is query text, not activation.

## Rendering

Default render shape:

```text
Command Palette

Search        dep

Results
> Deploy service        Run deployment pipeline
  Open logs             Show latest logs

[up/down] command  [enter] run  [esc] close
```

Rendering rules:

- Respect `constraints.width` and `constraints.max_height`.
- Use `autowrap_safe_width()` and `truncate_to_width(..., ellipsis="")`.
- Render title only when height permits.
- Render query row as `Search        <query-or-placeholder>`.
- Placeholder is visually distinct through theme but strips to plain text.
- Render a `Results` label before result rows when height permits.
- Render at most `max_visible` result rows and never exceed remaining height.
- Render `empty_text` when the filter has no matching rows.
- Render disabled rows visibly disabled and without a focus marker.
- Render footer only when height permits.
- Preserve stripped-text playback stability: focus marker remains `>`.
- Return a cursor declaration on the query row when the query editor is focused
  and the query row is visible.

Result row shape:

```text
> Label                 Description
  Disabled command      unavailable
```

Description is shown only when there is enough width, matching `Menu` behavior.

## Theme Tokens

`CommandPaletteView` accepts `ThemeResolver | None`.

Initial tokens:

| Token | Applies to |
| --- | --- |
| `widget.commandPalette.title` | Title row. |
| `widget.commandPalette.queryLabel` | Search label. |
| `widget.commandPalette.queryText` | Query text. |
| `widget.commandPalette.placeholder` | Placeholder text. |
| `widget.commandPalette.section` | `Results` section label. |
| `widget.commandPalette.item` | Enabled non-active result row. |
| `widget.commandPalette.focus` | Active enabled result row. |
| `widget.commandPalette.disabled` | Disabled result row. |
| `widget.commandPalette.description` | Result description. |
| `widget.commandPalette.empty` | Empty result row. |
| `widget.commandPalette.footer` | Footer row. |

The default example theme should use the same convention as recent examples:
cyan + bold for focused rows, bright black for placeholder/disabled/description,
and white for ordinary item text.

## Exports

Update exports:

- `src/loushang/tui/ui_parts/widgets/__init__.py`
- `src/loushang/tui/ui_parts/__init__.py`
- top-level `src/loushang/tui/__init__.py`

Export the new widget as `CommandPaletteView`.

Do not alter the top-level `CommandPalette` and `CommandPaletteItem` exports
except for the backward-compatible `disabled` field on `CommandPaletteItem`.

## Example

Add `examples/tui/51_widgets_command_palette.py`.

Scenario: `Operations Console`.

Initial commands:

- `Deploy service` - Run deployment pipeline
- `Open logs` - Show latest logs
- `Run tests` - Execute test suite
- `Clear cache` - Invalidate local cache
- `Restart worker` - Restart background worker
- `Archive release` - disabled, unavailable

Example behavior:

- Typing filters results.
- `up/down` moves the active command.
- `enter` updates a status row with the selected command.
- `escape` updates status to cancelled.
- `q` quits the example.

The example should use `Tui.show_overlay()` only if that remains simple and
deterministic. Otherwise, embed the palette directly in a compact app layout and
leave overlay composition to docs. P2A is about the widget behavior, not overlay
lifecycle.

## Tests

Add `tests/tui/test_widgets_command_palette.py`.

Coverage should include:

- Public re-exports from `loushang.tui.ui_parts.widgets`,
  `loushang.tui.ui_parts`, and top-level `loushang.tui`.
- Existing `CommandPalette.from_completion_provider()` still works and existing
  coding UI tests remain compatible.
- `CommandPaletteItem.disabled` defaults to `False`.
- Palette title inheritance, sequence default title, and explicitly blank
  `title=""` all behave distinctly.
- Constructor `query`, `set_query()`, text input, and paste stay synchronized
  through the internal editor-backed `query` property.
- Blank query shows all items.
- Text input filters by value, label, and description.
- Filtering is case-insensitive and preserves original order.
- Active result is repaired when query changes.
- Disabled items render but are skipped by navigation.
- Existing coding palette adapters keep current behavior when a compat item has
  `disabled=True`; disabled selection semantics are not silently promised there.
- `enter` returns `command_select` and optional `surface_close`.
- `escape`, `esc`, and `ctrl+c` return `command_cancel` and optional
  `surface_close`.
- `close_on_select=False` and `close_on_cancel=False` suppress surface close
  intents.
- Plain `home/end` edit the query cursor; `ctrl+home/ctrl+end` move the active
  result to the first/last enabled item.
- Width and height constraints are respected.
- Cursor maps to the query row.
- Theme tokens apply without changing visible width.
- Example import and playback snapshots for initial, typing, navigation,
  selection, and cancel.

## Documentation

Update:

- `docs/en/reference/tui-widgets.md`
- `docs/zh-CN/reference/tui-widgets.md`

Document that:

- `CommandPalette` is the data model.
- `CommandPaletteView` is the focusable widget.
- The widget can be embedded directly or used as a `SurfaceHost` overlay content.
- First-match filtering is simple substring matching, not fuzzy ranking.
- Selection returns `command_select`; cancel returns `command_cancel`; optional
  `surface_close` intents are emitted according to the close flags.
- Disabled commands stay visible in `CommandPaletteView` but are skipped and not
  activatable. Legacy coding palette adapters do not consume the disabled flag
  in P2A.

## Success Criteria

- Existing coding UI `CommandPalette` tests pass without API churn.
- The widget can render and handle input as a standalone focus target.
- Selection/cancel return structured intents.
- Disabled commands are visible, skipped, and not activatable.
- Playback tests show stable plain-text output and a single focus marker.
- No RenderLoop, SurfaceHost, InputRouter, or Composer changes are required.
