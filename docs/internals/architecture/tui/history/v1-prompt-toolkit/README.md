# History: Loushang TUI v1 Prompt-Toolkit/Rich Track

## Status

Historical.

This directory preserves the previous TUI v1 design track. It targeted a
prompt-toolkit inline application plus Rich rendering. The current
`feat/loushang-tui-native` branch uses
[`native-terminal-core`](../../native-terminal-core/README.md) as the target
design track instead.

## Documents

- [Loushang TUI System Context](./loushang-tui-system-context.md)
- [Loushang TUI Public API Guide](./loushang-tui-public-api-guide.md)
- [Loushang TUI v1 Readiness](./loushang-tui-v1-readiness.md)
- [Loushang TUI Component Design](./loushang-tui-component-design.md)
- [Inline Lifecycle Contract](./inline-lifecycle-contract.md)
- [ARD-002: Loushang-TUI Terminal Strategy](./ARD-002-loushang-tui-terminal-strategy.md)
- [ARD-001: Loushang-TUI Textual Strategy](./ARD-001-loushang-tui-textual-strategy.md)

## Reading Rule

Use these files as migration and history references only. Do not treat
prompt-toolkit, Rich, Textual, or the v1 inline runtime layout as the current
target architecture.

Older subsystem names such as `loushang-methods` are preserved inside these
files as historical wording. Current method resources live in `loushang.method`,
and coding/TUI method integration is governed by the live coding ARDs.

If the historical v1 release gate needs to be reproduced, run
`make test-tui-v1`.
