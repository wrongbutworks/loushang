# TUI Tabs Focus Theme Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Tabs` and `TabGroup` render selected-page highlight and keyboard-focus highlight with a stable, tested contract.

**Architecture:** Keep `Tabs` as the one-line primitive that maps selected/focus state to marker and theme tokens. Keep `TabGroup` as the focus-routing container that passes explicit `selected_focus` states into its internal `Tabs`. Update playback assertions and internals docs after the primitive and nested behavior are locked.

**Tech Stack:** Python 3.11, pytest, existing `loushang.tui` render primitives, `ThemeResolver`, terminal playback helpers.

---

## Spec

Implement against:

`docs/superpowers/specs/2026-06-14-tui-tabs-focus-theme-contract-design.md`

The key contract:

- `>` means selected tab header has keyboard focus.
- `*` means selected tab page is current, but the tab header does not have keyboard focus.
- space means normal or disabled tab.
- `widget.tabs.tab` remains in the normal-tab fallback chain.
- level 0 and level 1 nested focus paths are covered by playback/unit tests.
- level 2 is covered by synthetic unit tests only.

## File Structure

- Modify `src/loushang/tui/ui_parts/widgets/tabs.py`
  - Owns primitive tab marker and theme-token state mapping.
  - Add private helpers only; do not change public dataclass fields.

- Modify `src/loushang/tui/ui_parts/widgets/tab_group.py`
  - Should need little or no behavior change.
  - Only adjust if tests reveal an incorrect focus-state handoff to internal `Tabs`.

- Modify `tests/tui/test_widgets_light_controls.py`
  - Primitive `Tabs` marker/token/fallback tests.

- Modify `tests/tui/test_widgets_tab_group.py`
  - Nested `TabGroup` focus-path and example playback assertions.

- Modify `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`
  - Promote stable marker, focus, and theme-token contract to long-term docs.

No `src/loushang/coding/...` product behavior should be changed in this plan.

---

### Task 1: Primitive Tabs Marker And Token Contract

**Files:**
- Modify: `tests/tui/test_widgets_light_controls.py`
- Modify: `src/loushang/tui/ui_parts/widgets/tabs.py`

- [ ] **Step 1: Add failing tests for selected-focus markers**

Add tests near the existing `test_tabs_normalize_value_render_theme_and_width()` block:

```python
def test_tabs_selected_focus_states_use_distinct_markers_and_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.selected": {"color": "green"},
            "widget.tabs.focus": {"bold": True},
            "widget.tabs.level0.selected_header_focus": {"color": "cyan"},
            "widget.tabs.level0.selected_content_focus": {"color": "yellow"},
            "widget.tabs.tab": {"color": "white"},
        }
    )
    tabs = Tabs(
        [TabItem("config", "Config"), TabItem("model", "Model")],
        value="config",
        theme=theme,
    )

    assert plain_lines(tabs, width=40, height=1) == ("*[Config]   [Model]",)

    tabs.focus()
    header_raw = render_lines(tabs, width=40, height=1)[0]
    assert strip_control_sequences(header_raw).startswith(">[Config]")
    assert header_raw.startswith("\x1b[1;36m>[Config]")

    tabs.selected_focus = "content"
    content_raw = render_lines(tabs, width=40, height=1)[0]
    assert strip_control_sequences(content_raw).startswith("*[Config]")
    assert ">[Config]" not in strip_control_sequences(content_raw)
    assert content_raw.startswith("\x1b[33m*[Config]")

    tabs.selected_focus = "none"
    assert plain_lines(tabs, width=40, height=1)[0].startswith("*[Config]")
```

- [ ] **Step 2: Add failing tests for level 2 and fallback behavior**

Add:

```python
def test_tabs_level2_marker_and_token_fallbacks_are_stable() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.tab": {"color": "red"},
            "widget.tabs.normal": {"color": "white"},
            "widget.tabs.nested.normal": {"color": "blue"},
            "widget.tabs.level2.normal": {"color": "magenta"},
            "widget.tabs.selected": {"color": "green"},
            "widget.tabs.nested.selected_content_focus": {"color": "yellow"},
            "widget.tabs.level2.selected_header_focus": {"color": "cyan"},
        }
    )

    content = Tabs(
        [TabItem("one", "One"), TabItem("two", "Two")],
        value="one",
        level=2,
        selected_focus="content",
        theme=theme,
    )
    content_raw = render_lines(content, width=40, height=1)[0]
    assert strip_control_sequences(content_raw).startswith("*[One]")
    assert content_raw.startswith("\x1b[33m*[One]")
    assert "\x1b[35m [Two]" in content_raw

    header = Tabs(
        [TabItem("one", "One"), TabItem("two", "Two")],
        value="one",
        level=2,
        selected_focus="header",
        theme=theme,
    )
    header_raw = render_lines(header, width=40, height=1)[0]
    assert strip_control_sequences(header_raw).startswith(">[One]")
    assert header_raw.startswith("\x1b[36m>[One]")
```

This locks:

- selected content focus uses `*`, not `>`
- nested content focus can use `widget.tabs.nested.selected_content_focus`
- level 2 header focus can use `widget.tabs.level2.selected_header_focus`
- level 2 normal tabs override legacy fallback through `widget.tabs.level2.normal`

- [ ] **Step 3: Run tests and verify they fail for the current bug**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py -k "tabs_selected_focus or tabs_level2" -q
```

Expected: at least `test_tabs_selected_focus_states_use_distinct_markers_and_tokens` fails because current content focus renders `>[Config]`.

- [ ] **Step 4: Implement the primitive render-state helper**

In `src/loushang/tui/ui_parts/widgets/tabs.py`, replace the local marker decision with private helpers:

```python
TabRenderState = Literal[
    "normal",
    "selected_unfocused",
    "selected_content_focus",
    "selected_header_focus",
    "disabled",
]


def _tab_render_state(tabs: Tabs, tab: TabItem) -> TabRenderState:
    selected = tab.value == tabs.value and not tab.disabled
    if tab.disabled:
        return "disabled"
    if not selected:
        return "normal"
    focus_state = _selected_focus_state(tabs)
    if focus_state == "header":
        return "selected_header_focus"
    if focus_state == "content":
        return "selected_content_focus"
    return "selected_unfocused"


def _tab_marker(state: TabRenderState) -> str:
    if state == "selected_header_focus":
        return ">"
    if state in {"selected_unfocused", "selected_content_focus"}:
        return "*"
    return " "
```

Then update `_tab_segment()` to call these helpers and update `_tab_tokens()` to accept a render state:

```python
def _tab_segment(tabs: Tabs, tab: TabItem) -> str:
    state = _tab_render_state(tabs, tab)
    text = f"{_tab_marker(state)}[{tab.display_label}]"
    return style_text(text, tabs.theme, *_tab_tokens(tabs, state=state))
```

Keep the public `TabFocusState` values unchanged.

- [ ] **Step 5: Update `_tab_tokens()` to use the render state**

Implement:

```python
def _tab_tokens(tabs: Tabs, *, state: TabRenderState) -> tuple[str, ...]:
    level = max(0, tabs.level)
    nested_prefix = "widget.tabs.nested" if level > 0 else ""
    level_prefix = f"widget.tabs.level{level}"
    if state == "disabled":
        return tuple(
            token
            for token in (
                "widget.tabs.disabled",
                f"{nested_prefix}.disabled" if nested_prefix else "",
                f"{level_prefix}.disabled",
            )
            if token
        )
    if state == "selected_header_focus":
        return tuple(
            token
            for token in (
                "widget.tabs.selected",
                "widget.tabs.focus",
                f"{nested_prefix}.selected_header_focus" if nested_prefix else "",
                f"{level_prefix}.selected_header_focus",
            )
            if token
        )
    if state == "selected_content_focus":
        return tuple(
            token
            for token in (
                "widget.tabs.selected",
                f"{nested_prefix}.selected_content_focus" if nested_prefix else "",
                f"{level_prefix}.selected_content_focus",
            )
            if token
        )
    if state == "selected_unfocused":
        return ("widget.tabs.selected",)
    return tuple(
        token
        for token in (
            "widget.tabs.tab",
            "widget.tabs.normal",
            f"{nested_prefix}.normal" if nested_prefix else "",
            f"{level_prefix}.normal",
        )
        if token
    )
```

- [ ] **Step 6: Run focused primitive tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py -k tabs -q
```

Expected: all selected `tabs` tests pass. If existing example playback snapshots fail because selected content focus now uses `*`, do not update them in this task unless they are in the same file and directly caused by the primitive contract.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/tui/ui_parts/widgets/tabs.py tests/tui/test_widgets_light_controls.py
git commit -m "fix(tui): distinguish tab selected and focus markers"
```

---

### Task 2: Nested TabGroup Focus Path Contract

**Files:**
- Modify: `tests/tui/test_widgets_tab_group.py`
- Modify if needed: `src/loushang/tui/ui_parts/widgets/tab_group.py`

- [ ] **Step 1: Add nested focus-path unit test**

Add near the existing nested `TabGroup` tests:

```python
def test_nested_tab_group_markers_follow_active_focus_path() -> None:
    nested_page = FocusablePage(("nested content",))
    nested = TabGroup(
        [
            TabPage("overview", "Overview", nested_page),
            TabPage("models", "Models", StaticPage(("models",))),
        ],
        level=1,
    )
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True)

    parent_header = plain_lines(outer, width=80, height=5)
    assert parent_header[0].startswith(">[Stats]")
    assert parent_header[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in parent_header) == 1

    assert outer.focus_content() is True
    child_header = plain_lines(outer, width=80, height=5)
    assert child_header[0].startswith("*[Stats]")
    assert child_header[1].startswith(">[Overview]")
    assert sum(line.count(">") for line in child_header) == 1

    assert outer.handle_input(InputEvent(kind="key", key="down")) is True
    child_content = plain_lines(outer, width=80, height=5)
    assert child_content[0].startswith("*[Stats]")
    assert child_content[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in child_content) == 0

    outer.focus_header()
    parent_header_again = plain_lines(outer, width=80, height=5)
    assert parent_header_again[0].startswith(">[Stats]")
    assert parent_header_again[1].startswith("*[Overview]")
    assert sum(line.count(">") for line in parent_header_again) == 1
```

- [ ] **Step 2: Add nested theme token test**

Extend or add:

```python
def test_nested_tab_group_uses_parent_content_and_child_header_tokens() -> None:
    theme = ThemeResolver(
        defaults={
            "widget.tabs.level0.selected_content_focus": {"color": "green"},
            "widget.tabs.level1.selected_header_focus": {"color": "magenta"},
            "widget.tabs.level1.selected_content_focus": {"color": "yellow"},
        }
    )
    nested = TabGroup([TabPage("overview", "Overview", FocusablePage(("nested",)))], level=1, theme=theme)
    outer = TabGroup([TabPage("stats", "Stats", nested)], focused=True, theme=theme)

    assert outer.focus_content() is True
    child_header_raw = render_lines(outer, width=80, height=5)
    assert child_header_raw[0].startswith("\x1b[32m*[Stats]")
    assert child_header_raw[1].startswith("\x1b[35m>[Overview]")

    assert outer.handle_input(InputEvent(kind="key", key="down")) is True
    child_content_raw = render_lines(outer, width=80, height=5)
    assert child_content_raw[0].startswith("\x1b[32m*[Stats]")
    assert child_content_raw[1].startswith("\x1b[33m*[Overview]")
```

- [ ] **Step 3: Run tests and verify failures are limited to the known marker contract**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -k "nested_tab_group_markers or nested_tab_group_uses_parent" -q
```

Expected before Task 1 implementation: content focus may render `>`. After Task 1, these tests should pass unless `TabGroup` is passing the wrong `selected_focus` state.

- [ ] **Step 4: Adjust `TabGroup` only if the tests expose a handoff bug**

Expected current behavior is mostly correct:

- `TabGroup._selected_focus_state()` returns `none`, `header`, or `content`.
- `TabGroup.focus_header()` blurs child content before marking parent header focused.
- `TabGroup.focus_content()` calls child `focus()` when the selected content is another `TabGroup`.

Only change `src/loushang/tui/ui_parts/widgets/tab_group.py` if tests show these assumptions are false.

- [ ] **Step 5: Run focused TabGroup tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -k "not example" -q
```

Expected: all non-playback `TabGroup` tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/tui/test_widgets_tab_group.py src/loushang/tui/ui_parts/widgets/tab_group.py
git commit -m "test(tui): lock nested tab focus path markers"
```

If `tab_group.py` was not modified, omit it from `git add`.

---

### Task 3: Playback Assertions For Searchable TabGroup Example

**Files:**
- Modify: `tests/tui/test_widgets_tab_group.py`
- Do not modify `examples/tui/52_widgets_tabgroup_searchable_list.py` unless manual playback reveals the example itself is wrong.

- [ ] **Step 1: Update initial content-focus expectations**

In `test_tabgroup_searchable_list_example_playback_filters_settings()`, update the initial selected top-level tab assertion from:

```python
assert initial[0].startswith(">[Workspace]")
```

to:

```python
assert initial[0].startswith("*[Workspace]")
```

Reason: the example app starts with focus inside the selected Workspace page search area, not on the top-level header.

- [ ] **Step 2: Update style-focused example test**

In `test_tabgroup_searchable_list_example_styles_top_level_selected_tab()`, update the initial assertion:

```python
assert "*[Workspace]" in strip_control_sequences(initial)
```

Keep the later Activity assertion as header-focused:

```python
assert ">[Activity]" in strip_control_sequences(activity)
```

Also assert there is no marker spacing regression:

```python
assert "> [Activity]" not in strip_control_sequences(activity)
```

- [ ] **Step 3: Update search round-trip assertion**

In `test_tabgroup_searchable_list_example_up_to_tabs_down_returns_to_search()`, update:

```python
assert frames[-1].lines[0].startswith("*[Workspace]")
```

Reason: after down returns to search/content, top-level header no longer has keyboard focus.

- [ ] **Step 4: Strengthen nested playback assertion**

In `test_tabgroup_searchable_list_example_playback_switches_nested_tabs()`, add:

```python
final = frames[-1].lines
assert any("*[Activity]" in line for line in final)
assert any(line.startswith(" [Overview]") and ">[Models]" in line for line in final)
assert sum(line.count(">") for line in final) == 1
assert not any("> [" in line for line in final)
```

If the nested tabs render on a line with no leading space, adjust only the leading-space part to match actual output. Keep the assertions that there is exactly one `>` and no `> [` spacing.

- [ ] **Step 5: Run playback tests for the example**

Run:

```bash
uv run pytest tests/tui/test_widgets_tab_group.py -k tabgroup_searchable_list_example -q
```

Expected: all searchable-list example playback tests pass with the new marker semantics.

- [ ] **Step 6: Run the example import/render smoke**

Run:

```bash
uv run python -c "import runpy; from loushang.tui import RenderConstraints; ns = runpy.run_path('examples/tui/52_widgets_tabgroup_searchable_list.py', run_name='__test__'); app = ns['build_app'](); result = app.render(RenderConstraints(width=100, max_height=24)); print(len(result.lines))"
```

Expected: command exits successfully and prints a positive line count. Do not
launch the interactive runner for automated validation.

- [ ] **Step 7: Commit**

```bash
git add tests/tui/test_widgets_tab_group.py
git commit -m "test(tui): refresh tabgroup playback focus markers"
```

---

### Task 4: Documentation And Final Verification

**Files:**
- Modify: `docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md`

- [ ] **Step 1: Expand internals documentation**

Update the document to include these sections:

```markdown
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

## Tab Theme Fallbacks

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
```

- [ ] **Step 2: Run focused TUI tests**

Run:

```bash
uv run pytest tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_tab_group.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run focused lint**

Run:

```bash
uv run ruff check src/loushang/tui/ui_parts/widgets/tabs.py src/loushang/tui/ui_parts/widgets/tab_group.py tests/tui/test_widgets_light_controls.py tests/tui/test_widgets_tab_group.py
```

Expected: no lint failures.

- [ ] **Step 4: Run broader TUI test slice**

Run:

```bash
uv run pytest tests/tui -q
```

Expected: all TUI tests pass. If unrelated failures appear, capture exact failing tests and inspect whether they are caused by this marker contract.

- [ ] **Step 5: Commit docs and final verification updates**

```bash
git add docs/internals/architecture/tui/native-terminal-core/ui-parts/tabgroup-content-switcher.md
git commit -m "docs(tui): document tab focus marker contract"
```

- [ ] **Step 6: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected: branch contains the plan/spec commits plus implementation commits; worktree is clean.

---

## Manual Validation Notes

After automated tests pass, manually inspect the example if practical:

```bash
uv run python examples/tui/52_widgets_tabgroup_searchable_list.py
```

Expected visual behavior:

- initial Workspace page shows selected content marker/highlight, not header focus marker
- up from search moves header focus to `>[Workspace]`
- right arrow moves `>` across top-level tabs with no `> [` spacing
- down into Activity nested tabs changes top-level Activity to `*`
- nested selected tab shows `>`
- down into nested content changes nested selected tab from `>` to `*`
- only one `>` is visible in the active tab hierarchy at a time

Use `q` or `ctrl+c` to exit.
