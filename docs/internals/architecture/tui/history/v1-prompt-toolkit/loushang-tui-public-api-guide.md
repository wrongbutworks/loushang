# Loushang TUI Public API Guide

## Purpose

This guide defines how product layers should consume `loushang.tui`.

`loushang.tui` is a generic terminal UI primitive layer. It provides terminal-safe output,
inline prompt runtime, reusable controls, and generic terminal rendering helpers. Product
layers such as `loushang.coding.ui` own business semantics and adapt those semantics into
generic TUI primitives.

## Stable Import Surfaces

### Top-Level Facade

Use the top-level facade for stable generic primitives, controls, and view models:

```python
from loushang.tui import (
    CommandPalette,
    CommandPaletteItem,
    CompletionProvider,
    ControlController,
    ControlRenderer,
    Column,
    ColumnList,
    Frame,
    InfoPanel,
    KeyValueItem,
    KeyValueList,
    Notice,
    NoticeKind,
    PendingQueueView,
    SettingItem,
    SettingsList,
    TextView,
    fragments_to_text,
    lines_to_fragments,
)
```

The top-level facade is the preferred import surface for non-inline product code. It
intentionally does not expose prompt_toolkit buffers, Rich console internals, or inline
runtime delivery policy types such as `ComposerPolicy` or `ComposerDelivery`; those remain
internal to the inline runtime.

The facade is lazy. `import loushang.tui` and access to any symbol exported from
`loushang.tui.__all__` must not import prompt_toolkit or Rich. Those implementation
dependencies are loaded only when an interactive runner, prompt_toolkit style conversion,
or terminal render helper actually executes. The facade keeps explicit `TYPE_CHECKING`
re-exports so type checkers and IDEs can still see the public API without changing runtime
import behavior.

Complete top-level facade exports:

- `AutocompletePrompt`, `run_autocomplete`
- `ChoiceItem`, `ChoiceList`
- `CommandPalette`, `CommandPaletteAction`, `CommandPaletteController`, `CommandPaletteItem`,
  `CommandPaletteRenderer`, `run_command_palette`
- `CompletionItem`, `CompletionProvider`
- `ConfirmAction`, `ConfirmController`, `ConfirmPrompt`, `run_confirm`
- `ControlController`, `ControlRenderer`, `TextFragment`, `TextFragments`
- `Column`, `ColumnList`, `Frame`, `KeyValueItem`, `KeyValueList`, `Notice`, `NoticeKind`,
  `TextView`
- `fragments_to_text`, `lines_to_fragments`
- `InfoPanel`, `InfoPanelAction`, `InfoPanelController`, `run_info_panel`
- `InlineTheme`, `default_inline_theme`
- `PendingQueueProvider`, `PendingQueueRenderer`, `PendingQueueView`, `PendingSection`
- `SelectListAction`, `SelectListController`, `SelectListRenderer`, `run_select_list`
- `SettingItem`, `SettingsList`, `SettingsListAction`, `SettingsListController`,
  `SettingsListRenderer`, `run_settings_list`
- `StatusLine`, `StatusProvider`, `WorkingLine`
- `TerminalCapabilities`, `TerminalPort`, `is_interactive_terminal`
- `TextInputAction`, `TextInputController`, `TextInputPrompt`, `run_text_input`
- `TranscriptEmitter`

### Display Primitives

Use display primitives for generic terminal layout and status presentation:

```python
from loushang.tui import (
    Column,
    ColumnList,
    Frame,
    KeyValueItem,
    KeyValueList,
    Notice,
    NoticeKind,
    TextView,
)

status = Frame(
    title="Status",
    body=KeyValueList(
        (
            KeyValueItem("model", "moonshot/kimi-for-coding"),
            KeyValueItem("cwd", "/workspace/loushang"),
        )
    ).plain_text(width=70).splitlines(),
)

message = Notice("Model set.", kind=NoticeKind.SUCCESS)
```

These primitives are generic view models. They return prompt_toolkit-compatible
`(style, text)` fragments and know only about terminal width, wrapping, padding, alignment,
and notice severity. They must not inspect sessions, models, tools, slash commands, or
agent state.

Use fragment helpers when a consumer needs to compose or inspect generic TUI fragments:

```python
from loushang.tui import fragments_to_text, lines_to_fragments

fragments = lines_to_fragments(["one", "two"], style="class:item")
text = fragments_to_text(fragments)
```

These helpers operate only on the public `(style, text)` fragment shape. They do not load
prompt_toolkit and they do not understand product semantics.

### Rendering Helpers

Use `loushang.tui.render` for generic terminal rendering primitives:

```python
from loushang.tui.render import (
    CodeBlock,
    DiffBlock,
    MarkdownBlock,
    RuleBlock,
    TerminalBlock,
    TextBlock,
    block_to_terminal_text,
    blocks_to_terminal_text,
    code_to_terminal_text,
    create_terminal_console,
    diff_stat,
    diff_to_terminal_text,
    markdown_to_terminal_text,
    render_to_terminal_text,
    rule_to_terminal_text,
)
```

Rendering helpers must stay product-semantics free. They can render Markdown, code, diffs,
rules, or Rich renderables; they must not know about sessions, tools, models, providers,
agents, slash commands, or coding events.

Use render blocks when a generic terminal transcript needs to combine already-classified
content fragments without introducing product semantics:

```python
from loushang.tui.render import MarkdownBlock, RuleBlock, TextBlock, blocks_to_terminal_text

text = blocks_to_terminal_text(
    [
        RuleBlock("Summary"),
        MarkdownBlock("**Done**"),
        TextBlock("Plain footer"),
    ],
    width=80,
)
```

`TerminalBlock` is the public type alias for these renderable block values. The block type
only says how content should be rendered. It must not encode why the content
exists. Coding-owned projections such as assistant messages, tool summaries, model status,
and slash command output still decide which blocks to create.

The `loushang.tui.render` package facade is also lazy. Importing the package and accessing
helper functions must not load Rich; Rich is loaded when a helper actually renders a Rich
object, Markdown, code, or diff text. Pure helpers such as `diff_stat()` stay dependency-light.

### Inline Runtime

Use `loushang.tui.inline` for the inline prompt runner and inline local-control host API:

```python
from loushang.tui.inline import (
    InlineAction,
    InlineLocalInteractionController,
    InlinePromptConfig,
    run_inline_prompt_app,
    start_inline_command_palette,
)
```

`loushang.tui.inline` is the public inline facade. Product code may import from this exact
subpackage, but must not import deeper implementation modules such as
`loushang.tui.inline.runtime`, `loushang.tui.inline.services`, or
`loushang.tui.inline.composer_policy`.

The inline facade is lazy as well. `import loushang.tui.inline` must not load the inline
runtime, local-control implementation modules, keymap, prompt_toolkit, or Rich. Those pieces
load only when a consumer accesses a concrete inline symbol or executes the runner.

### Transcript Output

Use `TranscriptEmitter` when a product layer needs to write durable transcript output while
an inline prompt application is active:

```python
from loushang.tui import TranscriptEmitter

emitter = TranscriptEmitter(interactive=True)
await emitter.emit(lambda: stdout.write("hello\n"))
```

Product code should use the top-level facade import. `loushang.tui.output` contains low-level
runtime helpers for the TUI implementation; those helpers are not part of the product-layer
consumer contract.

### Non-Interactive Fallback

Use `loushang.tui.prompt.run_non_interactive_prompt_loop()` only for non-interactive stdin.
Interactive terminal mode belongs to `run_inline_prompt_app()`.

### Text Utilities

Use `loushang.tui.text_utils` for generic terminal text sizing:

```python
from loushang.tui.text_utils import fixed_width, visible_width
```

This is allowed because fixed-width status rendering is generic and frequently needed by
product adapters. `visible_width()` is also allowed for generic terminal layout decisions.

## Consumer Patterns

## Control Contract

Reusable controls follow a small shared shape:

- an `Action` enum describes generic UI actions such as submit, cancel, move, toggle, or close.
- a `Controller.handle(action)` method owns state transitions and returns the stable result when a control completes.
- controllers expose `done` and `cancelled` so adapters can distinguish completed, cancelled, and still-active states.
- `ControlController` is the public structural protocol for controller-like objects. It is a contract, not a base class.
- `ControlRenderer` is the public structural protocol for renderer-like objects that return generic `(style, text)` fragments.
- controls that render selectable state provide a renderer object that returns prompt-toolkit-compatible text fragments without exposing prompt_toolkit types in the public contract.
- a standalone runner provides the direct terminal workflow, such as `run_command_palette()`.
- an inline starter adapts the same generic control into `InlineLocalInteractionController`, such as `start_inline_command_palette()`.

Inline starters must keep `local_interactions`, `on_result`, and `on_cancel` keyword-only.
They translate `InlineAction` into the underlying generic control action. They must not parse
slash commands, inspect sessions, select models, or mutate product settings directly.
Successful inline local control completion clears local status so validation errors from the
local control do not leak back into the main composer state.

### Keyboard Contract

The inline runtime normalizes terminal keys into generic `InlineAction` values before product
adapters see them:

| Key | Idle Action | Running Action |
| --- | --- | --- |
| `Enter` | `SUBMIT` | `RUNNING_SUBMIT` |
| `Alt+Enter` | `NEWLINE` | `RUNNING_ALT_SUBMIT` |
| `Ctrl+J` | `NEWLINE` | `NEWLINE` |
| `Esc` | `ABORT` | `ABORT` |
| `Ctrl-C` | `ABORT` | `ABORT` |
| `Ctrl-D` | `EXIT` only when idle and empty | `NOOP` |
| `Alt-Up` | `DEQUEUE` | `DEQUEUE` |
| `Up` / `Down` | local-control navigation only | local-control navigation only |

`submit_on_enter=False` changes `Enter` to `NEWLINE` in both idle and running states. It does
not change `Alt+Enter`, `Esc`, `Ctrl-C`, `Ctrl-D`, or `Alt-Up`.

`Alt+Enter` is encoded as an escape-prefixed key sequence by terminals. The runtime supports
it as a semantic key, but product behavior must not rely on a no-wait burst that mixes
`Alt+Enter` and a standalone `Esc` during terminal resize redraws. PTY tests should wait for
each semantic action to land when the scenario also exercises resize or cursor-position
responses. Dedicated burst tests may still cover rapid input sequences without resize.

### Inline Runtime

The inline runtime is callback/provider based:

```python
from loushang.tui.inline import InlinePromptConfig, run_inline_prompt_app

exit_code = await run_inline_prompt_app(
    stdin=stdin,
    stdout=stdout,
    handle_prompt=handle_prompt,
    handle_alternate_submit=handle_follow_up,
    handle_dequeue=handle_dequeue,
    pending_messages=pending_messages,
    status=status,
    status_visible=status_visible,
    on_abort=on_abort,
    should_exit=should_exit,
    local_interaction_ready=bind_local_controls,
    config=InlinePromptConfig(prompt="› "),
)
```

The TUI runtime submits raw text and generic UI actions. It does not receive a session object
and does not know whether running input means steer, follow-up, or any other product action.
Product adapters map `handle_alternate_submit` to their own semantics; `loushang.coding.ui`
currently maps it to follow-up.

### Standalone Controls

Standalone controls can be used outside the inline runtime:

```python
from loushang.tui import CommandPalette, CommandPaletteItem, run_command_palette

palette = CommandPalette(
    title="Commands",
    items=(CommandPaletteItem(value="/help", description="Show help"),),
)
selected = await run_command_palette(stdin=stdin, stdout=stdout, palette=palette)
```

Standalone runners are useful for scripts and non-inline flows. They should remain generic.

### Inline Local Controls

Inline local controls are hosted through `InlineLocalInteractionController`. Product layers
bind local controls once and trigger them from business command handling:

```python
from collections.abc import Callable

from loushang.tui import CommandPalette
from loushang.tui.inline import (
    InlineAction,
    InlineLocalInteractionController,
    start_inline_command_palette,
)

class CommandChooser:
    def __init__(self) -> None:
        self._local_interactions = None
        self._query: Callable[[], str] | None = None

    def bind(
        self,
        *,
        local_interactions: InlineLocalInteractionController[object],
        query: Callable[[], str],
    ) -> None:
        self._local_interactions = local_interactions
        self._query = query

    def show(self, palette: CommandPalette) -> bool:
        if self._local_interactions is None or self._query is None:
            return False
        return start_inline_command_palette(
            local_interactions=self._local_interactions,
            palette=palette,
            query=self._query,
            on_result=handle_selection,
        )
```

The adapter owns only UI translation. Slash command parsing, model selection, session actions,
and settings application remain in the product layer.

`InlineAction` is the public generic action enum passed to inline local controls. Product
layers may use it to drive command palettes, settings lists, confirmation prompts, or other
local controls without importing inline keymap implementation modules directly.

## What Stays Out Of loushang.tui

`loushang.tui` must not own or import:

- `loushang.coding`
- `loushang.agent`
- `loushang.ai`
- session, model, provider, tool, method, or slash command semantics
- prompt_toolkit or Rich objects as public consumer-facing API
- complete fullscreen application framework abstractions until a concrete consumer needs them

`/model`, `/status`, `/statusline`, `/settings`, `/commands`, steer, follow-up, and abort
recovery semantics are product adapter responsibilities. `loushang.tui` only provides generic
controls and generic runtime actions.

## API Stability Tiers

### Stable v1 Contract

The v1 contract is intentionally small:

- `loushang.tui` top-level facade exports generic data models, standalone controls,
  terminal output primitives, and stable view models.
- `loushang.tui.inline` exports the inline runner, inline prompt configuration, generic
  inline actions, local-control host protocol, and local-control starter functions.
- `loushang.tui.render` exports generic transcript block types and terminal text render
  helpers.
- `loushang.tui.prompt.run_non_interactive_prompt_loop()` remains the non-interactive stdin
  fallback.
- `loushang.tui.text_utils.fixed_width()` and `visible_width()` remain available for product
  adapters that need terminal text sizing.

The v1 contract also includes import behavior. Importing a facade, direct stable module, or
accessing facade exports must not load prompt_toolkit or Rich. Those dependencies are
implementation details and are loaded only when an interactive runner, prompt_toolkit style
conversion, or terminal rendering helper actually executes.

The following are not v1 public contracts:

- modules below `loushang.tui.inline.*`
- prompt_toolkit `Application`, `Buffer`, `Layout`, key binding, or fragment types
- Rich `Console` and renderable objects
- `ComposerPolicy`, `ComposerDelivery`, runtime service containers, task controllers, or
  lifecycle internals
- future component/focus/overlay framework types

### Stable Public API

Stable generic public API is exported from `loushang.tui.__all__`. Product code should import
generic controls, primitives, and view models from `loushang.tui`.

### Stable Public Subpackages

These subpackages/modules are stable for direct imports:

- `loushang.tui.inline`
- `loushang.tui.render`
- `loushang.tui.prompt.run_non_interactive_prompt_loop`
- `loushang.tui.text_utils.fixed_width`
- `loushang.tui.text_utils.visible_width`

Direct production imports from these modules are intentionally narrow and are checked by
`tests/tui/test_import_boundaries.py`.

### Direct Import Allowlist

Production code outside `loushang.tui` may directly import only the following symbols from
`loushang.tui` submodules:

| Module | Allowed Symbols | Reason |
| --- | --- | --- |
| `loushang.tui.inline` | `InlineAction`, `InlineLocalInteractionController`, `InlineLocalInteractionReady`, `InlinePromptConfig`, `run_inline_prompt_app`, `start_inline_command_palette`, `start_inline_confirm`, `start_inline_info_panel`, `start_inline_settings_list`, `start_inline_text_input` | inline runtime and local-control host facade |
| `loushang.tui.prompt` | `run_non_interactive_prompt_loop` | non-interactive stdin fallback |
| `loushang.tui.text_utils` | `fixed_width`, `visible_width` | generic terminal text sizing |
| `loushang.tui.render` | `CodeBlock`, `DiffBlock`, `MarkdownBlock`, `RuleBlock`, `TerminalBlock`, `TextBlock`, `block_to_terminal_text`, `blocks_to_terminal_text`, `code_to_terminal_text`, `create_terminal_console`, `diff_stat`, `diff_to_terminal_text`, `markdown_to_terminal_text`, `render_to_terminal_text`, `rule_to_terminal_text` | generic transcript blocks, terminal text rendering, diff summary, and completed-block Markdown rendering |

All other stable primitives should come from the top-level `loushang.tui` facade or from the
`loushang.tui.render` package facade.

### Internal White-Box Runtime API

`loushang.tui.inline.*` modules below the inline facade are internal runtime implementation.
Tests may import them for white-box coverage, but product code must not depend on them
directly.

The inline-related production entry points live in `loushang.tui.inline`:

- `InlineAbortHandler`
- `InlineAlternateSubmitHandler`
- `InlineDequeueHandler`
- `InlineExitPredicate`
- `InlineLocalInteraction`
- `InlineLocalInteractionActionHandler`
- `InlineLocalInteractionCallbacks`
- `InlineLocalInteractionCancelHandler`
- `InlineLocalInteractionComposer`
- `run_inline_prompt_app`
- `InlineAction`
- `InlinePromptConfig`
- `InlineLocalInteractionController`
- `InlineLocalInteractionReady`
- `InlineLocalInteractionRenderer`
- `InlineLocalInteractionResultHandler`
- `InlinePromptHandler`
- `InlineStatusProvider`
- `InlineStatusVisibleProvider`
- `start_inline_command_palette`
- `start_inline_info_panel`
- `start_inline_settings_list`
- `start_inline_confirm`
- `start_inline_text_input`

## Testing Contract

API surface and import boundaries are guarded by:

- `tests/tui/test_import_boundaries.py`
- `tests/tui/test_public_api_guide.py`
- `tests/tui/test_inline_runtime_contract.py`
- PTY smoke/regression tests under `tests/tui/test_coding_tui_*`

New public exports should update this guide, the relevant facade `__all__`
(`loushang.tui`, `loushang.tui.inline`, or `loushang.tui.render`), and the import-boundary
tests in the same change. The import-boundary tests also guard the lazy facade contract so
product-layer imports do not pay for prompt_toolkit/Rich unless they actually run terminal UI
or rendering code. They also guard stable direct modules such as `loushang.tui.inline`,
`loushang.tui.render`, standalone control modules, and rendering helper modules so those
imports remain lightweight. Fresh-interpreter smoke coverage keeps this contract from being
hidden by pytest module cache state.

PTY tests should use semantic helpers from `tests.tui.pty_harness.TuiPtyHarness`:

- generic key helpers such as `send_enter()`, `send_alt_enter()`, `send_escape()`,
  `send_ctrl_c()`, `send_ctrl_j()`, and `send_alt_up()`
- product aliases such as `send_prompt()`, `send_steer()`, `send_follow_up()`,
  `send_abort()`, and `send_dequeue()`
- lifecycle waits such as `wait_run_idle()` or `wait_idle_after()` before sending the next
  idle prompt or `/quit`
- negative assertions such as `wait_no_event()` and `assert_no_running_input_leak()` for
  queue isolation checks

The PTY harness must pump terminal output while waiting on event files, because
prompt_toolkit may issue cursor-position requests (`ESC[6n`) during resize/redraw. The harness
responds to those requests so tests model a real terminal closely enough for control-flow
regression coverage.
