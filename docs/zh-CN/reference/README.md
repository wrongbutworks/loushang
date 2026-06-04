# 参考手册

[English](../../en/reference/) | 中文

本页收集当前用户与贡献者常用的参考入口。

## CLI

```bash
loushang --help
loushang --version
loushang --list-models
loushang --list-commands
loushang --list-sessions
loushang --list-methods
loushang --list-skills
loushang --list-plugins
loushang --list-packages
```

## 输出格式

多个 list 与 export 命令支持机器可读输出：

```bash
loushang --list-models --list-models-format json
loushang --list-sessions --list-sessions-format json
loushang --list-commands --list-commands-format json
loushang --export session.jsonl --export-format jsonl
```

## Slash Commands

内置交互命令包括：

```text
/settings /model /scoped-models /export /import /share /copy /name
/session /terminal /changelog /hotkeys /fork /clone /tree
/login /logout /new /compact /resume /reload /quit
```

## TUI

- [TUI Runner](tui-runner.md)：使用 `loushang.tui` 构建终端应用的公共生命周期入口。
