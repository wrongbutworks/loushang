# TUI Status Line Lane Split Design

## Status

Ready for TUI-lane implementation planning. Code-lane handoff contract defined.

This document is the temporary coordination spec for splitting status-line work
between the Native TUI lane and the coding/product lane. The long-term internal
architecture content should move to:

`docs/internals/architecture/tui/native-terminal-core/ui-parts/status-line.md`

after both lane slices stabilize.

## Context

The native coding TUI already has a bottom status line and a settings page:

- `StatusBar` in `src/loushang/tui/ui_parts/status.py` renders a single line by
  sorting `StatusField(text, priority)` values and joining selected fields with
  `" | "`.
- `NativeCodingTuiApp._status_bar()` builds product-specific fields for model,
  workspace, branch, session, runtime, queue state, and transient status
  message.
- `CodingTuiStatusProvider` owns the current status-line visibility flag and
  exposes a Config setting for `statusline`.
- `SettingsPageView` renders the current `Status line true/false` row in the
  Config tab.

Those concerns are currently interleaved in the broader status-line settings
idea. The reusable rendering enhancement belongs in the long-lived TUI lane;
the product settings surface belongs in the code lane.

## Decision

Use a two-PR lane split:

1. **TUI lane first.** Implement only reusable status-bar rendering support in
   `loushang.tui.ui_parts`.
2. **Code lane second.** After the TUI PR is merged and `main` is updated, the
   code lane implements the product-facing Status Line settings tab using the
   public TUI API.

The code lane must not start from the TUI feature branch. It should start from
`main` after the TUI rendering foundation is merged.

## Overall User Outcome

The final product goal remains:

- a first-level `Status Line` settings tab
- visible field toggles
- separator selection
- color style selection
- live preview
- compatibility with `/statusline on|off`

This document does not authorize implementing those product controls in the TUI
lane. It only defines the sequence and handoff.

## TUI Lane Scope

The TUI lane delivers a reusable, product-agnostic status-bar renderer:

- `StatusField` accepts an optional semantic `token`.
- `StatusBar` accepts `separator`, `style_mode`, and `theme`.
- `plain` mode preserves current unstyled behavior.
- Styled modes can resolve status-bar theme tokens through existing
  `ThemeResolver`.
- Width fitting and priority truncation continue to use unstyled text.
- Public imports remain stable:
  - `from loushang.tui import StatusBar, StatusField`
  - `from loushang.tui.ui_parts import StatusBar, StatusField`
  - `from loushang.tui.ui_parts.status import StatusBar, StatusField`

The detailed TUI-lane execution spec is:

`docs/superpowers/specs/2026-06-14-tui-statusbar-rendering-design.md`

## TUI Lane Non-Goals

The TUI lane must not implement product settings behavior:

- no `Status Line` settings tab
- no `StatusLineSettings`
- no `StatusLinePreviewSnapshot`
- no `status_line_fields(...)` product helper
- no `/statusline` command changes
- no `NativeCodingTuiApp._status_bar()` product rewrite beyond compatibility
  adjustments required by the renderer
- no persistence

Existing coding status-line behavior should remain effectively unchanged while
the TUI renderer defaults to `plain`.

## Code Lane Scope

After the TUI PR is merged, the code lane implements the product feature:

- add `src/loushang/coding/ui/status_line.py`
- define `StatusLineSettings`
- define `StatusLinePreviewSnapshot`
- define `status_line_fields(snapshot, settings)`
- add first-level Settings tab order:
  `Status, Config, Model, Status Line, Usage, Stats`
- remove the duplicate `Status line` row from Config when the new tab exists
- keep `/statusline on|off` compatible
- make Settings tab and `/statusline` share the same effective enabled state
- render the real status line and preview through the public TUI `StatusBar`
  and `StatusField(token=...)` API

The code lane must use the provider-owned status model described below. The
real bottom status line and preview must also use the same field-builder helper
to avoid divergent behavior.

## Code Lane Status Ownership

The code-lane slice should collapse status-line visibility into one effective
owner:

- `CodingTuiStatusProvider` owns the effective `StatusLineSettings`.
- `StatusLineSettings.enabled` replaces `_visible` as the canonical enabled
  value. `_visible` should either be removed or treated as derived
  compatibility state inside the provider.
- `NativeCodingTuiApp.state.statusline_visible` and future
  `NativeCodingTuiApp.state.statusline_settings` are render mirrors, not
  independent sources of truth.
- `NativeSurfaceManager` is the sync boundary between provider-owned settings
  and app-render state.

Required sync rules:

- `/statusline on|off` updates provider-owned settings first, then mirrors the
  effective `StatusLineSettings` into `NativeCodingTuiApp`.
- `/statusline` without an argument reports the provider-owned enabled value,
  then mirrors that value into app state.
- The Settings page reads its initial rows from the provider-owned
  `StatusLineSettings`.
- A Settings tab submit updates provider-owned settings, refreshes rows and
  preview from the provider, and returns enough result data for
  `NativeSurfaceManager` to mirror the effective settings into the app.
- The open Settings preview must use the same app preview snapshot provider as
  the real status line, so queue/message auto behavior reflects current app
  state.

## Code Lane Preview Snapshot

The code-lane `StatusLinePreviewSnapshot` must contain every live value needed
by both the real status line and the settings preview:

```python
@dataclass(frozen=True, slots=True)
class StatusLinePreviewSnapshot:
    model_label: str | None
    cwd: str
    branch: str | None
    session_label: str | None
    running: bool
    pending_followups: int = 0
    pending_steers: int = 0
    status_message: str | None = None
```

`StatusSnapshot` from `CodingTuiStatusProvider` is not sufficient for preview
by itself because queue counts and transient status messages currently live in
`NativeCodingTuiApp.state`.

## Code Lane Field Priorities

`status_line_fields(...)` should keep the current priority order unless user
review changes it:

| Field | Token | Priority | Default |
| --- | --- | ---: | --- |
| model | `model` | 100 | enabled |
| workspace | `workspace` | 90 | enabled |
| branch | `branch` | 80 | enabled |
| session | `session` | 70 | enabled |
| runtime running | `runtime.running` | 60 | enabled when running |
| runtime idle | `runtime.idle` | 60 | enabled when idle |
| queue | `queue` | 50 | auto |
| message | `message` | 40 | auto |

This table is the source of truth for focused code-lane priority tests.

## Code Lane Setting IDs and Value Cycles

The code-lane Settings tab should use stable setting ids:

- `statusline.enabled`: `true -> false -> true`
- `statusline.field.model`: `true -> false -> true`
- `statusline.field.workspace`: `true -> false -> true`
- `statusline.field.branch`: `true -> false -> true`
- `statusline.field.session`: `true -> false -> true`
- `statusline.field.runtime`: `true -> false -> true`
- `statusline.field.queue`: `auto -> true -> false -> auto`
- `statusline.field.message`: `auto -> true -> false -> auto`
- `statusline.separator`: `pipe -> dot -> pipe`
- `statusline.style`: `codex-like -> muted -> plain -> codex-like`

The UI may display `pipe` as `|` and `dot` as `.` or `·`, but the setting value
should remain an enum-like string. The style setting maps directly to
`StatusBar.style_mode`.

## Code Lane Default Focus

Adding `Status Line` as a top-level tab must not change the existing
`/settings` default page. The settings page should continue opening with
`Config` selected unless a future user request explicitly changes that
interaction.

## Handoff Contract

The TUI PR is ready for code-lane pickup only when these contracts are true:

- Old call sites keep working:
  `StatusBar([StatusField("model", priority=100)])`.
- With defaults, rendered text remains byte-for-byte compatible for unstyled
  callers.
- `StatusField.token` is optional and defaults to an empty string.
- `StatusBar.separator` defaults to `" | "`.
- `StatusBar.style_mode` defaults to `"plain"`.
- `style_mode == "plain"` bypasses all `statusBar.*` token resolution.
- Styled modes can resolve field and separator styles via `ThemeResolver`.
- Tokenized fields do not affect field fitting because width calculation uses
  unstyled text.
- Helpers that clone `StatusField` values preserve `token`.
- Public exports include the updated dataclass signatures.

The code lane should depend only on those public contracts, not on private
helpers inside `status.py`.

## Code Lane API Consumption Example

The code lane should be able to build status fields like this:

```python
fields = (
    StatusField("moonshot/kimi-for-coding", priority=100, token="model"),
    StatusField("loushang", priority=90, token="workspace"),
    StatusField("tui", priority=80, token="branch"),
    StatusField("idle", priority=60, token="runtime.idle"),
)

bar = StatusBar(
    fields,
    separator=" | ",
    style_mode="codex-like",
    theme=theme,
)
```

The TUI renderer is responsible for mapping `"model"` to status-bar token
chains such as `statusBar.codexLike.model`, `statusBar.model`, and
`statusBar.field`. The code lane should not pre-resolve ANSI styling.

## Code Lane Product Defaults

The later code-lane product slice should use these defaults unless user review
changes them:

- status line enabled: `true`
- model field: `true`
- workspace field: `true`
- branch field: `true`
- session field: `true`
- runtime field: `true`
- queue field: `auto`
- message field: `auto`
- separator: pipe
- color style: `codex-like`

`Queue field = true` with no live data should render `queued=0 steer=0`.
`Message field = true` with no live data should render `no status`.

## Validation Sequence

Before the TUI PR is handed off:

- run TUI renderer tests for status-bar compatibility and styling
- run existing composer bottom-frame tests that exercise `StatusBar`
- run focused lint on modified files

Before the later code-lane PR is handed off:

- run focused tests for `src/loushang/coding/ui/status_line.py`
- run coding settings-page tests
- run native surface manager tests
- run native playback tests for settings and `/statusline`
- run focused lint on modified coding UI files

Focused `status_line.py` tests should cover:

- default `StatusLineSettings`
- default field order and priority
- `auto` queue/message behavior
- forced `true` queue/message output when no data exists
- forced `false` queue/message omission
- separator enum mapping
- style enum mapping to `StatusBar.style_mode`
- real status line and preview using the same field builder

Integration tests in native surface manager/app coverage should prove:

- `/statusline` updates provider-owned enabled state and mirrors it into app
  state
- Settings tab updates provider-owned settings and mirrors effective settings
  into app state
- an open preview reads the app preview snapshot for queue/message data

## Risk Controls

- Keeping `plain` as the TUI default prevents a reusable widget change from
  silently recoloring existing status bars.
- Deferring product settings to code lane prevents the TUI PR from owning
  coding app state, `/statusline`, and settings persistence questions.
- Using public TUI exports as the handoff boundary keeps code lane insulated
  from private renderer implementation details.
- Merging the TUI PR before starting code-lane work avoids long-lived
  cross-lane branch dependency.

## Resolved Decisions

- TUI renderer work is implemented first in the TUI lane.
- Code/product settings work waits until the TUI renderer PR is merged into
  `main`.
- The TUI lane spec is
  `2026-06-14-tui-statusbar-rendering-design.md`.
- The long-term documentation target remains under
  `docs/internals/architecture/tui/native-terminal-core/ui-parts/`.
