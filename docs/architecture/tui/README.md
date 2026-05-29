# Loushang-TUI Architecture

本目录收纳 `loushang-tui` 子系统的架构文档。

## Current Design Track

Current target design:

- [Loushang TUI Native Terminal Core](./native-terminal-core/README.md)

`native-terminal-core/` is the target whitebox design track for the
`feat/loushang-tui-native` branch. It defines the next `loushang.tui` runtime and
component model. It is not a separate loushang subsystem.

## Historical Material

Older TUI architecture documents are preserved under:

- [History: v1 prompt-toolkit/Rich](./history/v1-prompt-toolkit/README.md)

Those documents describe the previous prompt-toolkit/Rich implementation track
and v1 API release gate. They are useful for migration context, but they are not
the target core runtime strategy for this branch.

## Source Entrypoints

Target source entrypoints remain:

- `src/loushang/tui/`
- `src/loushang/coding/ui/`

`loushang.tui` is the generic terminal UI framework. `loushang.coding.ui` adapts
coding product state, events, and commands into the generic TUI.
