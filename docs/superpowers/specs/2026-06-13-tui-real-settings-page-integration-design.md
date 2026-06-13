# TUI Real Settings Page Integration Design

## Status

Ready for user review.

## Context

`TabGroup` and `SearchableList` now provide the widget foundation for
settings-style pages:

- top-level and nested tab headers;
- persistent selected page content;
- search input plus filtered long-list viewport;
- focus transitions between tabs, search, and list content;
- level-aware tab theme states;
- structured selection results.

The current product `/settings` path still opens `SettingsSurface` through
`NativeSurfaceManager._open_settings()`. That path is useful but narrow:

- `SettingsSurface` is an overlay/surface, not ordinary tab page content.
- `CodingTuiStatusProvider.settings_list()` currently exposes only
  `Status line`.
- Submitted settings are handled by toggling a `SettingsList` item and applying
  it back to the status provider.

The next step is to connect the new widget capabilities to a real product
surface without replacing every settings and stats data source in one change.

## Goals

- Upgrade the real `/settings` native TUI path to a tabbed control-center page.
- Keep the existing `/model` command and `ModelSelectorSurface` behavior
  unchanged, except for optional shared helper reuse.
- Use `TabGroup` for the top-level `Status / Config / Model / Usage / Stats`
  sections.
- Use `SearchableList` for the Config page, including long-list viewport
  support.
- Use a nested `TabGroup(level=1)` under Stats for `Overview / Model Usage`.
- Preserve the existing `/settings` command and native surface intent flow.
- Keep the legacy `SettingsSurface` available for compatibility and tests.
- Reuse existing `SettingItem` / `SettingsList` where they are sufficient.
- Add a small adapter layer for product settings rows instead of inventing a
  second settings schema.
- Connect only low-risk real settings in the first integration slice.
- Render Usage and Stats from available real session/context data where
  possible, with explicit unavailable states where data does not exist.
- Add playback coverage for the real `/settings` path.

## Non-Goals

- Do not delete `SettingsSurface`.
- Do not expose every `SettingsManager` field as a writable UI setting in the
  first slice.
- Do not add long-term historical usage storage.
- Do not fake contribution heatmaps, token history, or model-usage percentages
  when the real data source is absent.
- Do not make the first slice depend on mouse support.
- Do not add a new global focus manager.
- Do not change the public contracts of `TabGroup` or `SearchableList` unless a
  real integration bug proves the contract insufficient.
- Do not copy another product's exact visual styling, colors, labels, or field
  set.
- Do not rewrite model registry, provider configuration, or model metadata
  management in this slice.
- Do not remove or degrade the standalone `/model` selector path.

## Proposed Architecture

Add a product-level native surface content object, tentatively named
`SettingsPageView`, under `src/loushang/coding/ui/`.

`SettingsPageView` is not a new generic widget. It composes existing generic
widgets into the coding product page:

- owns the top-level `TabGroup`;
- owns page-specific adapters;
- delegates render and input to selected page content;
- returns `InputIntent(kind="setting", text=<id>, note=<value>)` when a setting
  changes;
- returns `InputIntent(kind="setting", text="model.current", note=<choice>)`
  when the Model page selects a model;
- exposes `async apply_setting(id, value)` so `NativeSurfaceManager` can
  delegate new-page setting/model side effects back to the page instead of
  duplicating adapter routing;
- returns `InputIntent(kind="surface_close")` for close keys;
- exposes an `editor_input_target()` so text input reaches the focused
  `SearchableList` search box.

`NativeSurfaceManager._open_settings()` should become async and be awaited from
`handle_text()`, matching the existing async command handling used by model
selection. It should instantiate this view and keep using
`NativeSurfaceView(purpose="settings")`. That preserves the existing surface
lifecycle and `_normalize_surface_intent()` handling.

`SettingsPageView` should be created through an async builder or equivalent
factory that loads a model-choice snapshot from existing async model helpers. If
model choices cannot be loaded, the Model page renders an unavailable state and
the standalone `/model` command remains the fallback.

`NativeSurfaceView` needs two compatible delegation changes for this integration:

- `editor_input_target()` delegates to hosted content when content exposes that
  method.
- `render()` offsets and returns non-`InfoPanel` content cursors, rather than
  dropping them.

These are host-level compatibility fixes, not `SettingsPageView`-specific
shortcuts. Existing surfaces should keep their current visual behavior unless
they already return a cursor.

The initial page structure:

```text
Status   Config   Model   Usage   Stats

Config page:
  Search settings...
  Setting                                    Value
  Status line                                true
  Auto compaction                            true
  Auto retry                                 true
  Terminal progress                          false
  ...

Model page:
  Search models...
  Model                                      Status
  kimi-for-coding                            current
  kimi-k2.5
  Haiku 4.5

Stats page:
  Overview   Model Usage
  <read-only usage summary>
```

## Components

### SettingsPageView

Responsibilities:

- Build the top-level `TabGroup`.
- Keep focus stable across tab switches.
- Render a simple separator between tab headers and page content.
- Render a focus-aware footer.
- Hide the hardware cursor unless the selected content declares a real text
  input cursor.
- Translate Config page selection results into `InputIntent(kind="setting")`.
- Treat `q`, Esc, and Escape as close keys by returning
  `InputIntent(kind="surface_close")`.
- Keep the surface open after Config changes and Model selections so users can
  make multiple changes in one visit.
- Expose `apply_setting(id, value)` as the single owner for new-page Config and
  Model side effects.

The view should use the same focus rules proven by
`examples/tui/52_widgets_tabgroup_searchable_list.py`:

- Down from top-level tab header enters the selected page.
- Up from Config search returns to top-level tabs.
- Down from Config search enters the list.
- Up from the first Config list item returns to search.
- Left/right move only the focused tab header.
- Nested Stats tabs use their own level-1 focus and colors.
- Interactive page wrappers consume left/right/home/end while their search or
  list content is focused, so the current `TabGroup` fallback tab navigation
  cannot switch top-level pages from inside an editing/list region.

### ConfigSettingsPage

Responsibilities:

- Own one `SearchableList`.
- Render a header row and a separator above list rows.
- Support long lists through the existing `SearchableList` viewport.
- Keep active row stable when a value changes.
- Return structured setting-change events.

Config rows should be produced from adapters:

- `StatusSettingsAdapter` wraps `CodingTuiStatusProvider.settings_list()` for
  the existing `Status line` setting.
- `ControlSettingsAdapter` exposes a small allowlist of low-risk
  `SettingsManager` fields.

The first allowlist should prefer simple booleans and enum-like values with
existing getters/setters:

- status line visibility, through `CodingTuiStatusProvider`;
- auto compaction, through `SessionSettingsController` if available;
- auto retry, through `SessionSettingsController` if available;
- terminal progress, through `SettingsManager.get_show_terminal_progress()` and
  `set_show_terminal_progress()`;
- theme, read-only or cycle-through only if the existing accepted values are
  explicit.

Rows without a safe write path must be read-only or disabled. Disabled rows stay
visible in filtering but are skipped by navigation, matching
`SearchableList`.

### ModelPage

The Model page should become a first-level tab because model selection is a
primary coding workflow, not a secondary Config row.

Responsibilities:

- Show the current model clearly in the first viewport.
- Reuse the same data sources as the existing `/model` selector:
  `available_model_choices()`, `current_model_choice_value()`,
  `iter_scoped_model_selections()`, and model detail descriptions where
  available.
- Render model choices through `SearchableList` so search, long-list scrolling,
  active-row repair, and disabled-row behavior match Config.
- Selecting an enabled model should return
  `InputIntent(kind="setting", text="model.current", note=<choice>)` so the
  existing settings surface event path can route it without adding a new
  `InputIntentKind`.
- Keep the settings page open after selection and refresh the status/model
  label.

If model choices cannot be loaded, render a read-only unavailable state and
keep `/model` as the fallback path.

### StatusPage

The Status page should be read-only in the first slice. It should show compact
runtime facts from a small explicit snapshot API, not by parsing rendered
toolbar text or reaching into private provider fields.

Add or inject a read-only status snapshot with:

- current model label;
- current cwd and branch;
- session label;
- thinking level;
- running/idle state;
- status line visibility.

If a value is unavailable, render a short `Unavailable` value instead of
guessing.

### UsagePage

The Usage page should be read-only in the first slice. It should render current
context usage only through an explicit optional usage snapshot/provider.
`current_context_usage()` requires messages, branch entries, and model inputs;
the page should not discover those by broad session introspection.

Minimum useful rows:

- current context tokens;
- context window;
- percent used;
- compaction threshold if available;
- source, such as estimated or assistant usage.

If the usage provider is absent or cannot compute a snapshot from explicit
inputs, render `Usage data unavailable` and keep the page navigable.

### StatsPage

Stats should use a nested `TabGroup(level=1)`:

- `Overview`: compact read-only session/context summary.
- `Model Usage`: model-related usage summary, clearly distinct from the
  top-level Model selection page.

The first slice should not render fake historical charts. If the repository
does not yet have durable usage aggregation, Overview can render current
session totals and explicitly state that historical stats are unavailable.

## Data Flow

Opening `/settings`:

1. `NativeSurfaceManager.handle_text("/settings")` awaits `_open_settings()`.
2. `_open_settings()` loads the model-choice snapshot with existing async model
   helpers. Failures become a Model page unavailable state.
3. `_open_settings()` builds `SettingsPageView` with:
   - `CodingTuiStatusProvider`;
   - the current session;
   - the model-choice snapshot or unavailable state;
   - a read-only status snapshot provider;
   - an optional usage snapshot provider;
   - optional `SessionSettingsController` or `SettingsManager` accessors.
4. `NativeSurfaceView` hosts the page with `purpose="settings"`.

Changing a setting:

1. `ConfigSettingsPage` activates the current enabled row.
2. Boolean rows toggle in place. Enum rows cycle only when the allowed values
   are explicit.
3. The page returns `InputIntent(kind="setting", text=row.id, note=new_value)`.
4. `NativeSurfaceManager._normalize_surface_intent()` keeps producing a
   settings submit event.
5. `_handle_settings_submit()` checks the current surface content.
6. If the content is `SettingsPageView`, the manager calls
   `await page.apply_setting(id, value)`, keeps the surface open, refreshes
   app status/statusline/model label from the result, and does not duplicate
   adapter logic.
7. If the content is legacy `SettingsSurface`, the manager preserves existing
   close-on-submit behavior.

Changing the model:

1. `ModelPage` activates the current enabled model row.
2. The page returns `InputIntent(kind="setting", text="model.current",
   note=<choice>)`.
3. `NativeSurfaceManager._handle_settings_submit()` delegates to
   `SettingsPageView.apply_setting("model.current", choice)`.
4. The page method calls `select_available_model()`, matching the existing
   `/model` selector behavior.
5. The page remains open, the current model marker refreshes, and the app
   status/model label updates.

`SettingsPageView.apply_setting()` should return a small result object or
equivalent tuple containing:

- user-facing status message;
- optional status line visibility;
- whether the app model label should be refreshed;
- whether the page rows were refreshed successfully.

Adapter write failures return a recoverable message and keep the page open.

## Visual And Focus States

The real page should use semantic theme tokens rather than hardcoded product
colors:

- unselected tab;
- selected tab with focus inside page content;
- selected tab with focus on the tab header;
- level-1 selected tab with content focus;
- level-1 selected tab with header focus;
- search box focus;
- active Config row;
- disabled Config row;
- overflow hint.

The level-aware resolver must keep the existing `widget.tabs.tab` fallback for
normal tab styling, preserving theme compatibility.

The first selected top-level tab must visibly appear selected even when there
is no left arrow or preceding tab. Focus markers and selected styling should
not disagree.

## Error Handling

- Adapter write failures should keep the settings page open and set a status
  message with the recoverable error text.
- Unknown row ids should be ignored with a recoverable status message.
- Missing `SettingsManager` or session usage data should degrade to read-only
  or unavailable rows.
- A failed value refresh should not clear the user's search query.
- The page must not crash when the terminal height is too small; it should clip
  body rows and keep footer rendering best-effort.

## Testing

Add unit tests for the new product page content:

- builds top-level `Status / Config / Model / Usage / Stats` pages;
- Config search filters rows;
- long Config lists scroll;
- Up/Down transitions between tabs, search, and list;
- toggling a boolean row updates the value and preserves active row;
- Model search filters model rows;
- selecting an enabled model emits the expected model action;
- read-only/disabled rows are visible but skipped by navigation;
- Stats renders nested level-1 tabs;
- tiny render heights do not crash;
- `SettingsPageView.apply_setting()` keeps the page open, refreshes rows, and
  returns a status result for successful Config changes.
- `SettingsPageView.apply_setting("model.current", value)` calls the model
  selection path without requiring a new `InputIntentKind`.

Add native playback tests for the real `/settings` command:

- `/settings` opens the tabbed page instead of the legacy single settings list;
- typing filters Config rows;
- Up from search moves focus to top-level tabs without a stale cursor artifact;
- Down from search enters the list;
- Space or Enter toggles a boolean setting and keeps the page open;
- left/right on focused tabs switches top-level pages;
- Model appears as a top-level tab and shows the current model;
- Stats page exposes `Overview / Model Usage` nested tabs;
- `q` or Esc exits the page.

Add manager/host tests:

- `_open_settings()` is async and `handle_text("/settings")` awaits it.
- `_normalize_surface_intent()` still maps
  `InputIntent(kind="setting", text="model.current", note=value)` through the
  settings submit path.
- `_handle_settings_submit()` delegates to `SettingsPageView.apply_setting()`
  and keeps the surface open for the new page.
- `_handle_settings_submit()` preserves legacy `SettingsSurface`
  close-on-submit behavior.
- `NativeSurfaceView.editor_input_target()` delegates to hosted content.
- `NativeSurfaceView.render()` offsets and preserves non-`InfoPanel` content
  cursors.
- No new `InputIntentKind` is added for model selection.
- The standalone `/model` command and `ModelSelectorSurface` behavior remain
  covered by existing tests or a focused regression.

Keep existing `SettingsSurface` tests. Add one explicit test proving the legacy
surface remains importable and still renders searchable settings.

## Migration Plan

1. Land this spec as the temporary execution record.
2. Write an implementation plan from this spec.
3. Add `SettingsPageView` and adapters behind the existing `/settings` path.
4. Add focused tests and playback scenarios.
5. Update durable internal architecture docs after the implementation settles.

Long-term documentation should live under:

`docs/internals/architecture/tui/native-terminal-core/`

This spec stays under `docs/superpowers/specs/` as the development record for
the slice.

## Open Decisions

1. Which `SettingsManager` fields are safe enough to expose as writable in the
   first implementation plan.
2. Whether `/settings` should be renamed in UI copy to `Config` while keeping
   the slash command unchanged.
