# 使用手册

[English](../../en/user-guide/) | 中文

使用手册说明当前 `loushang code` 相关的产品面。

## CLI 与 TUI

`loushang` 是主 CLI 入口。它支持一次性 prompt 运行、text/print/json/rpc 模式、会话控制、模型列表、命令列表、诊断、工具、扩展、技能、方法、包、导出和 work log。

需要交互式 coding session 时，可以使用 `loushang --tui` 启动终端 UI 产品面。已安装的 `loushang-tui` 命令是同一 TUI 模式的便捷入口。

常用起始命令：

```bash
loushang --help
loushang --list-models
loushang --list-commands
loushang --list-sessions
loushang --tui
loushang -p "Summarize the current project."
```

如果要用 `loushang.tui` 构建终端 UI 应用，见 [构建 TUI 应用](tui.md)。

## 会话

会话保存 coding 对话与执行记录，适合需要恢复、分叉、导出、诊断和后续检查的工作流。

常见操作：

```bash
loushang --list-sessions
loushang --resume
loushang --export
```

在交互界面中，内置 slash commands 包括 `/session`、`/resume`、`/fork`、`/clone`、`/tree`、`/export`、`/compact`、`/reload` 和 `/quit`。

## 工具

工具把可执行能力暴露给 agent。Coding 产品包含内置工具面，并支持启用、禁用和收窄工具范围：

```bash
loushang --tools bash,write -p "Inspect this project."
loushang --no-tools -p "Explain the repository from context only."
```

## 扩展

扩展是可以注册生命周期 hooks、工具、动态资源、命令和 flags 的 Python 文件。可以先阅读 [examples/coding/extensions](../../../examples/coding/extensions/) 中的可运行扩展示例。

## 包与插件

包与插件可以提供可复用的 coding 资产。常见生命周期命令：

```bash
loushang --list-plugins
loushang --list-packages
loushang --install-package <source>
loushang --check-package-updates
loushang --update-packages
```

## 方法与技能

方法与技能把可复用工作实践变成运行时资产。CLI 中可以使用：

```bash
loushang --list-methods
loushang --show-method <method>
loushang --show-method-plan <method>
loushang --method <method> -p "Run this coding task."
loushang --no-method -p "Run without the configured default method."
loushang --list-skills
```

`--method` 支持非交互的 prompt/print/json 路径。在 method step UI 与 work-event projection 路径就绪前，TUI 和 RPC mode 会继续拒绝 `--method`。

## Work Logs

Work log 会为一次性 prompt/print/json 运行记录 `WorkOperation` 与 `WorkEvent`：

```bash
loushang --work-log .loushang/work/events.jsonl -p "Run this coding task."
loushang --work-log-inspect .loushang/work/events.jsonl
loushang --work-log-inspect .loushang/work/events.jsonl --work-log-inspect-format plans
```

`--work-log` 不支持 TUI 或 RPC mode。

## 诊断与导出

诊断和导出用于检查 session 中发生了什么：

```bash
loushang --list-diagnostics
loushang --diag-export --diag-output diagnostics.json
loushang --export session.html
```
