# ARD-002: Loushang-TUI Terminal Strategy

## Status

Accepted

## Date

2026-05-11

## Context

`loushang-tui` 的目标体验已经从 fullscreen terminal app 转向 Codex / Claude / Kimi 风格的 inline terminal workflow：

- 真实 terminal scrollback 保留 transcript。
- 底部 composer / status 是 transient UI，不进入 scrollback。
- 输入区支持 multi-line editing。
- assistant streaming 与 tool events 写入真实终端输出。
- 错误默认以短摘要展示，调试时才输出 traceback。

早期 `ARD-001` 选择 Textual 作为 `loushang-tui` 的实现底座。该方向适合 fullscreen/app-style TUI，但不适合将 terminal scrollback 作为主 transcript，并在底部维护临时 composer block。

新的架构需要同时满足：

- `loushang.tui` 可作为通用终端 UI 基础层复用。
- `loushang.coding` 保持 headless，不依赖 UI。
- `loushang.coding.ui` 负责连接 coding runtime/session 与 terminal UI primitives。

## Decision

`loushang-tui` P0 改为 prompt_toolkit + Rich 终端架构。

源码分层采用：

```text
src/loushang/
  tui/
    __init__.py
    terminal.py
    control.py
    output.py
    render/
    command_palette.py
    confirm.py
    info_panel.py
    select_list.py
    settings_list.py
    text_input.py
    inline/
      __init__.py
      keymap.py
      runtime.py
      local_interaction.py

  coding/
    ui/
      mode.py
      controller.py
      events.py
      renderer.py
      intent.py
      toolbar.py
```

依赖方向固定为：

```text
loushang.tui
  does not depend on loushang.coding

loushang.coding
  does not depend on loushang.tui

loushang.coding.ui
  depends on loushang.tui
  depends on loushang.coding
```

`prompt_toolkit` 负责 prompt session、multi-line editing、history、keybindings、bottom toolbar、stdout coordination。

`Rich` 负责 transcript、tool event、status、error summary 等 terminal output rendering。

`Textual` 不进入新的 `loushang-tui` P0 架构。旧 Textual 分支只作为参考，不作为依赖基线。

## Consequences

### Positive

- `loushang-tui` 更接近 Codex / Claude / Kimi 的 terminal interaction model。
- transcript 保持在真实 terminal scrollback 中。
- composer/status 可以作为 transient UI 独立重绘。
- `loushang.tui` 成为可复用的通用 terminal UI primitive layer。
- `loushang.coding` 不被 UI 框架污染。
- 新分支可以从 `main` 直接实现，不继承旧 Textual 架构。

### Negative

- 需要新增 prompt_toolkit / Rich 显式依赖。
- 需要自行设计一层 coding-specific event renderer。
- fullscreen widget/layout 能力不再由 Textual 提供。
- prompt_toolkit 的真实终端行为需要通过 pseudo-terminal 或 injectable fake session 做测试。

### Deferred

- session selector
- model selector
- tool expansion UI
- theme system
- remote channel attach
- Textual-based `loushang-uiapp` 是否保留为独立产品入口

## Compatibility

Recommended public entries:

```text
loushang-tui
python -m loushang.coding.cli --tui
```

`loushang-tui` should call `loushang.coding.ui.cli`.

`python -m loushang.coding.cli --tui` should remain as a compatibility path and forward to `loushang.coding.ui.mode`.

## References

- [Loushang TUI System Context](./loushang-tui-system-context.md)
- [ARD-001: Loushang-TUI Textual Strategy](./ARD-001-loushang-tui-textual-strategy.md)
