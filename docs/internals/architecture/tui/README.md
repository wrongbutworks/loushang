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
- `src/loushang/harnesstui/`
- `src/loushang/coding/ui/`

`loushang.tui` is the generic terminal UI framework. The
[`loushang.harnesstui`](../harnesstui/README.md) composition layer adapts neutral
Harness conversation contracts into reusable TUI interaction. Product adapters
such as `loushang.coding.ui` provide Coding-specific state, event projection,
commands, policy, and runtime assembly.

For status presentation, `loushang.tui` owns the generic status-bar widget and
its layout, styling, invalidation, and rendering mechanics. A shared Harness
status profile belongs to `loushang.harnesstui`; products populate that profile
and retain their own status policy.

Generic settings rows, themes, formatting, and input helpers live in
`loushang.tui.settings`. Reusable Harness-oriented settings pages, model
selection, and surface framing live one layer outward in `loushang.harnesstui`.
Product shells remain responsible for supplying values and applying decisions.

Host clipboard-image acquisition lives in
`loushang.tui.clipboard_image`. This generic capability owns platform fallback,
neutral image bytes and MIME normalization. Product-neutral persistence into a
caller-supplied directory, composer-marker tracking, and prompt-order recovery
live in `loushang.harnesstui.conversation.attachments`. Product shells remain
responsible for workspace-directory policy, UI copy, and conversion into
model-specific attachment values such as `ImagePart`.

Clipboard-image acquisition resolves the host once into an ordered backend
plan behind a common protocol. On macOS, the system `NSPasteboard` adapter is
preferred, with `pngpaste` retained only as a compatibility fallback.
