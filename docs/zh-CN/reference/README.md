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
loushang --show-method <method>
loushang --show-method-plan <method>
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
loushang --list-methods --list-methods-format json
loushang --show-method <method> --show-method-format json
loushang --show-method-plan <method> --show-method-plan-format json
loushang --list-packages --list-packages-format json
loushang --work-log-inspect .loushang/work/events.jsonl --work-log-inspect-format plans-json
loushang --export session.jsonl --export-format jsonl
```

## 方法

```bash
loushang --method <method> -p "Run this coding task."
loushang --no-method -p "Run without the configured default method."
```

`--method` 支持 prompt/print/json 路径，不支持 TUI/RPC mode。

## Work Logs

```bash
loushang --work-log .loushang/work/events.jsonl -p "Run this coding task."
loushang --work-log-inspect .loushang/work/events.jsonl
loushang --work-log-inspect .loushang/work/events.jsonl --work-log-run <run-id>
```

inspect 格式支持：`text`、`json`、`plans`、`plans-json`。

## 包

```bash
loushang --install-package <source>
loushang --uninstall-package <source>
loushang --materialize-package <source>
loushang --update-package <source>
loushang --update-packages
loushang --check-package-updates
```

## 命令执行

```bash
loushang --command <command-name> --command-args "<args>"
loushang --command <command-name> --command-result-format json
```

## Slash Commands

内置交互命令包括：

```text
/settings /model /scoped-models /export /import /share /copy /name
/session /terminal /tools /changelog /hotkeys /fork /clone /tree
/login /logout /new /compact /resume /reload /quit
```

## TUI

- [TUI Runner](tui-runner.md)：使用 `loushang.tui` 构建终端应用的公共生命周期入口。
- [TUI 编辑能力](tui-editing.md)：可复用的 TextInput、Composer、selection-aware editing、快捷键和 playback smoke 检查。
- [TUI 控件](tui-widgets.md)：可复用的按钮、选项、字段、表单、选择列表和 modal 对话框。
