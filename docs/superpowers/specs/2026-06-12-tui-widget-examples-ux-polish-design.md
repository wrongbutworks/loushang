# TUI Widget Examples UX Polish Design

## Status

Draft for spec review.

## Context

The widget catalog now has runnable examples for the P0/P1 controls:

- `43_widgets_foundation.py`
- `44_widgets_small_controls.py`
- `45_widgets_light_controls.py`
- `46_widgets_table.py`
- `47_widgets_textarea.py`
- `48_widgets_question_dialog.py`
- `49_widgets_tree.py`
- `50_widgets_toast.py`

Example `43_widgets_foundation.py` was recently improved into a clearer
two-column field layout. It now separates field-level Tab navigation from
option-level arrow navigation. This should become the visual baseline for later
widget examples.

Playback snapshots for examples `44-50` show that the examples are functional
but still read like control inventories instead of small real interfaces:

- `44` shows progress, key-value rows, and toolbar controls, but the screen has
  little task context.
- `45` currently lets tabs and menu both render as focused, so users can see
  two `>` markers at once.
- `46` shows a table, but lacks enough surrounding context to explain what the
  row selection means.
- `47` renders a textarea and several blank rows, but the empty editor area has
  weak visual boundaries.
- `48` renders a question dialog as the whole page, so it does not demonstrate
  how the dialog would appear in a real workflow.
- `49` renders a tree, but has no detail pane to explain the selected node.
- `50` renders toasts as the main page body, so it demonstrates toast rows but
  not toast notifications in context.

This slice should polish the examples into coherent, learnable mini
applications while keeping the underlying widget APIs stable.

## Goals

- Redesign examples `44-50` as small realistic TUI screens rather than raw
  widget inventories.
- Keep example `43` as the style reference for clear field labels, focus
  markers, and concise footer copy.
- Make each example clearly show:
  - what scenario it represents;
  - which region currently has focus;
  - which keys affect region focus versus item navigation;
  - what happens after activation.
- Remove confusing simultaneous focus cues, especially in `45`.
- Use deterministic playback-like snapshots to verify the first screen and key
  interaction frames for every polished example.
- Keep examples public-facing and readable. They should teach usage patterns
  without requiring knowledge of internal render plumbing.
- Keep implementation local to examples and tests unless a very small existing
  widget fix is required to make an example honest.

## Non-Goals

- Do not introduce a general layout engine.
- Do not extract public `FieldGrid`, `ShortcutBar`, `Panel`, `SplitPane`, or
  `ToastManager` APIs in this slice.
- Do not change `SurfaceHost`, `RenderLoop`, `InputRouter`, or terminal runtime
  behavior.
- Do not redesign widget internals unless a playback test exposes a real widget
  bug.
- Do not add mouse interactions.
- Do not make examples visually decorative at the expense of clarity. These are
  technical learning examples, not marketing screens.
- Do not change the already landed widget public API contracts except for small
  backwards-compatible rendering options if they already exist on the branch.

## Design Principles

### Scenario First

Each example should answer “what tool am I looking at?” in the first viewport.
Titles should be literal and task-oriented:

- `Indexing Job`
- `View Switcher`
- `Job Queue`
- `Release Note Draft`
- `Notes Inbox`
- `Project Explorer`
- `Deploy Console`

### One Primary Interaction Model Per Example

Each example should emphasize one interaction pattern:

| Example | Primary pattern |
| --- | --- |
| `44` | Horizontal toolbar actions |
| `45` | Region focus: tabs versus action menu |
| `46` | Table row navigation and activation |
| `47` | Multiline editing |
| `48` | Modal question dialog over application context |
| `49` | Tree navigation with detail projection |
| `50` | Toast notifications over application context |

### Region Boundaries

Interactive regions should be visually separated with simple headings or
spacing. A user should not have to infer whether two controls belong to the
same focus scope.

Use plain ASCII and existing widgets. Avoid heavy borders unless a widget
already renders them.

### Footer Copy

Every example should end with one concise key hint row. Footer text should
describe current example behavior, not every possible key in the widget system.

Recommended shape:

```text
[tab] region  [up/down] item  [enter] select  [q] quit
```

When an example has only one region, omit `[tab] region`.

### Playback As Design Contract

Every polished example should have tests that render:

- the initial screen;
- at least one navigation frame;
- at least one activation or state-change frame.

Tests should assert stripped visible text for stable rows and, where useful,
cursor position or focused-row output.

## Example Designs

### 44 Widgets Small Controls: Indexing Job

Current screen:

```text
Small Controls  [beta]  (ready)

Indexing [#####-------] 42%

Model: Kimi
Mode : safe  current
Queue: 3 pending

> [Refresh]  [Cancel]
Ready
```

Proposed screen:

```text
Indexing Job  [beta]  (ready)

Progress      Indexing [#####-------] 42%

Details
Model         Kimi
Mode          safe  current
Queue         3 pending

Actions       > [Refresh]  [Cancel]
Status        Ready

[left/right] action  [enter] run  [q] quit
```

Interaction:

- Left/right moves toolbar focus.
- Enter activates the focused toolbar action.
- Refresh increases progress and sets `Status Refreshed`.
- Cancel sets `Status Cancelled`.

Implementation notes:

- Keep `Toolbar` as the only focusable region.
- Use example-local label formatting for `Progress`, `Actions`, and `Status`.
- Do not add a new public field-grid control in this slice.

### 45 Widgets Light Controls: View Switcher

Current issue: tabs and menu can both display `>` at the same time.

Proposed screen:

```text
View Switcher

Views         > [Overview]    [Logs 3]    [Settings]
Activity      | Syncing

Actions
                Open      current view
                Refresh
                Archive   disabled

Status        Ready

[tab] region  [left/right] view  [up/down] action  [enter] run  [q] quit
```

After Tab to the actions region:

```text
Views           [Overview]    [Logs 3]    [Settings]
Activity      | Syncing

Actions
              > Open      current view
                Refresh
                Archive   disabled
```

Interaction:

- The app owns a two-region focus state: `views` or `actions`.
- Tab switches between tabs and menu.
- When `views` is active:
  - left/right moves selected tab;
  - up/down does not move menu;
  - menu must not render focused.
- When `actions` is active:
  - up/down moves menu item;
  - left/right does not move tabs unless the user tabs back to views;
  - tabs must not render focused.
- Enter on action runs the selected menu item.

Implementation notes:

- Do this in the example app with explicit region focus, not by adding a global
  focus manager.
- Call `tabs.focus()/blur()` and `menu.focus()/blur()` when region focus
  changes.
- `spinner_frame` can still advance on Refresh.

### 46 Widgets Table: Job Queue

Current screen is functional but too generic.

Proposed screen:

```text
Job Queue  (3 jobs)

  Job           Status                                                     Runs
> Build         ready                                                        12
  Deploy        blocked                                                       3
  Archive       disabled                                                      0

Selected      Build is ready, 12 runs

[up/down] row  [enter] select  [q] quit
```

Interaction:

- Up/down moves the active row.
- Enter selects the active enabled row.
- Footer and selected detail update after selection.

Implementation notes:

- Keep `Table` as the only focusable widget.
- Example-local row metadata can generate the selected detail line.
- Disabled row should remain visibly disabled according to existing table
  behavior.

### 47 Widgets TextArea: Release Note Draft

Current screen has weak structure because the empty textarea appears as several
blank rows.

Proposed screen:

```text
Release Note Draft

Title         Weekly deploy notes

Notes
Write notes




Status        0 lines / unsaved

[enter] newline  [type] edit  [q] quit
```

`Write notes` is placeholder text, not initial textarea content. The initial
draft has zero user-entered lines.

After typing:

```text
Status        2 lines / unsaved
```

Interaction:

- Text input edits the textarea.
- Enter inserts a newline.
- Status reflects line count and unsaved state.

Implementation notes:

- Keep `Form([FormRow("notes", TextArea(...))])` as the focus owner.
- Add surrounding labels and a status line.
- The textarea itself should remain the editor; do not fork editing behavior.

### 48 Widgets Question Dialog: Notes Inbox

Current screen renders the dialog as the whole page. The polished example should
show the dialog inside a workflow.

Proposed initial screen:

```text
Notes Inbox

Recent
  Cache deploy checklist
  Follow up on flaky test

New Note
Add note
What should be remembered?
Write a multi-line answer



Enter adds a line. Ctrl+Enter submits.
  [Submit]  [Cancel]

Status        Drafting

Escape cancels. [tab] actions  [ctrl+enter] submit  [q] quit
```

Interaction:

- Dialog remains focused.
- Typing edits the answer.
- Tab moves to dialog actions.
- Submit adds the answer to recent notes and sets
  `Status        Submitted: <answer>`.
- Cancel keeps recent notes unchanged and sets `Status        Cancelled`.

Implementation notes:

- This can remain inline rather than requiring a real overlay, because the
  example runner is minimal. The important improvement is background context.
- If an overlay is used, tests must still be deterministic and should assert the
  composed visible screen.

### 49 Widgets Tree: Project Explorer

Current screen shows only the tree and a message.

Proposed screen:

```text
Project Explorer

Tree
> - src
      widgets
      runtime
  + tests

Details
Path          src
Kind          folder
Status        expanded

[up/down] node  [enter] select/toggle  [q] quit
```

Interaction:

- Up/down moves the active tree node.
- Enter selects leaf nodes and toggles expandable nodes according to current
  `TreeView` behavior.
- Details pane reflects the active or selected node.

Implementation notes:

- Keep `TreeView` as the only focusable widget.
- Example-local metadata can map node values to kind/status/detail lines.
- Ensure details update on navigation, not only on explicit selection, so users
  understand what focus currently means.

### 50 Widgets Toast: Deploy Console

Current screen renders `ToastStack` as the page body. The polished example
should show toasts as notifications alongside app content.

Proposed screen:

```text
Deploy Console

Pipeline      api-server
Status        waiting
Last event    none

Notifications
[success] Changes saved
[info] Loushang: Welcome

[i] info  [s] success  [w] warning  [d] danger  [x] dismiss  [c] clear  [q] quit
```

Interaction:

- `i/s/w/d` push toast notifications and update `Last event`.
- `x` dismisses the oldest visible dismissible toast.
- `c` clears all notifications.
- `Status` reflects the deploy console state and stays stable unless the
  example explicitly changes pipeline state in a later slice.
- `Last event` reflects toast actions, such as `warning toast added`,
  `dismissed oldest`, or `cleared notifications`.

Implementation notes:

- Keep `ToastStack` non-focusable and app-owned.
- Render notification rows below stable console context.
- Do not add timers or overlays in this slice.

## Testing Strategy

Add or update focused tests under existing widget test files:

- `test_widgets_small_controls.py`
- `test_widgets_light_controls.py`
- `test_widgets_table.py`
- `test_widgets_textarea.py`
- `test_widgets_question_dialog.py`
- `test_widgets_tree.py`
- `test_widgets_toast.py`

For each example:

1. Use `runpy.run_path(..., run_name="__test__")`.
2. Call `build_app()`.
3. Render with `RenderConstraints(width=80, max_height=20)`.
4. Assert stable visible rows after `strip_control_sequences`.
5. Drive one or more `InputEvent` interactions through `app.handle_input(...)`
   or `tui.handle_input(...)`.
6. Assert a focused/navigation frame and an activation/state-change frame.

Every polished example should have a playback-like test helper using
`TuiRuntime + FakeTerminalPort` or an equivalent direct `RenderLoop` setup. The
helper should capture stripped `current_logical_lines`, the logical cursor, and
the operation class for each scripted frame. Render-only assertions may still
cover small pure-widget details, but the example UX contract is the playback
snapshot because it catches confusing composed-screen states such as `45`'s
simultaneous tabs/menu focus.

For each example, the playback snapshot test must cover:

- initial frame;
- navigation frame;
- activation or state-change frame.

Run before completion:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py -q
uv --cache-dir .uv-cache run --extra dev pytest tests/tui -q
uv --cache-dir .uv-cache run --extra dev ruff check examples/tui/44_widgets_small_controls.py examples/tui/45_widgets_light_controls.py examples/tui/46_widgets_table.py examples/tui/47_widgets_textarea.py examples/tui/48_widgets_question_dialog.py examples/tui/49_widgets_tree.py examples/tui/50_widgets_toast.py tests/tui/test_widgets_small_controls.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_table.py tests/tui/test_widgets_textarea.py tests/tui/test_widgets_question_dialog.py tests/tui/test_widgets_tree.py tests/tui/test_widgets_toast.py
git diff --check
```

## Implementation Slices

### Slice 1: Examples 44-47

Polish:

- `44_widgets_small_controls.py`
- `45_widgets_light_controls.py`
- `46_widgets_table.py`
- `47_widgets_textarea.py`

This slice covers toolbar, tabs/menu focus regions, table details, and textarea
structure. It should also fix the most visible confusion: the double focus
marker in `45`.

### Slice 2: Examples 48-50

Polish:

- `48_widgets_question_dialog.py`
- `49_widgets_tree.py`
- `50_widgets_toast.py`

This slice covers dialog context, tree details, and toast-as-notification
composition.

Each slice should keep tests green independently.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Example helpers become accidental framework APIs. | Keep helpers private to examples. Extract public layout widgets only in a later spec. |
| Tests become too brittle to spacing. | Assert stable rows and important alignment, but avoid overspecifying every blank line unless it carries meaning. |
| `45` region focus duplicates future global focus manager work. | Keep the two-region state local to the example; do not generalize it. |
| Polished examples hide simple widget usage. | Keep construction code readable and avoid large abstractions. |
| Toast example implies automatic timers or overlays. | Explicitly keep `ToastStack` renderable and app-owned. |

## Success Criteria

- Examples `44-50` have clearer first screens with task-oriented titles.
- Each example has exactly one obvious active focus region at a time.
- Footer hints match actual example behavior.
- Playback or render snapshot tests cover initial, navigation, and state-change
  frames for each polished example.
- No public API churn is introduced solely for example polish.
- `tests/tui -q`, targeted widget tests, Ruff, and `git diff --check` pass.
