# User Guide

English | [中文](../../zh-CN/user-guide/)

The user guide explains the product surfaces that are currently relevant for `loushang code`.

## CLI And TUI

`loushang` is the main CLI entry point. It supports one-shot prompt runs, text/print/json/rpc modes, session controls, model listing, command listing, diagnostics, tools, extensions, skills, methods, packages, export, and work logs.

Use `loushang --tui` to start the terminal UI product surface when you want an interactive coding session. The installed `loushang-tui` command is a convenience entry point for the same TUI mode.

TUI mode has two runtime surfaces. With TTY stdin/stdout, `loushang --tui` and
`loushang-tui` open the screen surface. With piped or redirected stdio under
`--tui`, the same mode uses the plain prompt loop, which is useful for smoke
tests:

```bash
printf "hi\n/quit\n" | loushang --tui
```

There is no separate UI selector flag for plain output. Use `--tui` and let
terminal interactivity choose the surface.

Useful starting commands:

```bash
loushang --help
loushang --list-models
loushang --list-commands
loushang --list-sessions
loushang --tui
loushang-tui
loushang -p "Summarize the current project."
```

For building terminal UI applications with `loushang.tui`, see [Building TUI Apps](tui.md).

## Sessions

Sessions preserve the coding conversation and execution record. They are designed for workflows that need resume, fork, export, diagnostics, and later inspection.

Common actions:

```bash
loushang --list-sessions
loushang --resume
loushang --continue
loushang --resume <session-id-or-path>
loushang --export
```

Interactive `loushang --resume` and argument-free `/resume` open the full-screen
searchable continuity picker. By default, Space opens a lazy preview, Tab cycles
available domains when several providers are installed, and Ctrl+S changes the
common sort. `--continue` resumes the newest session in the current project,
while `--resume <session-id-or-path>` and `/resume <session-id-or-path>` restore
a specific session directly. Non-interactive use requires one of those explicit
forms.

Inside the interactive surface, built-in slash commands include `/session`, `/resume`, `/fork`, `/clone`, `/tree`, `/tools`, `/extensions`, `/export`, `/compact`, `/reload`, and `/quit`.

## Tools

Tools expose executable capabilities to the agent. The coding product includes built-in tool surfaces and options for enabling, disabling, and narrowing tools:

New interactive sessions enable the built-in `read`, `ls`, `find`, `grep`, `bash`, `edit`, and `write` tools by default. Prefer `ls`, `find`, `grep`, and `read` for file exploration; keep `bash` for shell behavior such as pipelines, redirects, build commands, tests, and Git operations.

```bash
/tools
/tools off bash
/tools only read,ls,find,grep
/tools reset
loushang --tools bash,write -p "Inspect this project."
loushang --no-tools -p "Explain the repository from context only."
```

### LSP Semantic Tools

`coding.lsp` is an optional, high-frequency Coding capability that provides
`inspect_symbol` and `document_outline`. It defaults to `on_demand`; make the
tools part of the agent's default tool set for one invocation with:

```bash
loushang --capability coding.lsp=always
loushang lsp status
loushang lsp doctor
```

Servers still start lazily on the first semantic query. `status` and `doctor`
only inspect configuration and executable availability; they do not start or
install a server. Loushang probes installed Pyright, TypeScript Language Server,
rust-analyzer, gopls, and clangd defaults.

Declare a custom server in `~/.loushang/coding/lsp.json`:

```json
{
  "servers": [
    {
      "id": "python-custom",
      "command": ["my-language-server", "--stdio"],
      "language_extensions": {"python": [".py", ".pyi"]}
    }
  ]
}
```

Project `.loushang/lsp.json` may tune a Product default or a server already
declared by the user. Until the general workspace-trust mechanism exists, a
repository config cannot introduce a new executable or environment override.

## Extensions

Extensions are Python files that can register lifecycle hooks, tools, dynamic resources, commands, and flags. Start with the runnable extension examples in [examples/coding/extensions](../../../examples/coding/extensions/).

An extension may include an adjacent `loushang-extension.toml` manifest to declare identity, permission level, dependencies, and expected runtime surfaces. Use `/extensions` to inspect loaded extensions, surface summaries, and diagnostics; use `/extensions <id>` for one extension. `/tools` includes source information for extension-provided tools when available.

## Packages And Plugins

Packages and plugins can contribute reusable coding assets. Common lifecycle commands:

```bash
loushang --list-plugins
loushang --list-packages
loushang --install-package <source>
loushang --check-package-updates
loushang --update-packages
```

## Methods And Skills

Methods and skills turn reusable working practices into runtime assets. In the CLI, use:

```bash
loushang --list-methods
loushang --show-method <method>
loushang --show-method-plan <method>
loushang --method <method> -p "Run this coding task."
loushang --no-method -p "Run without the configured default method."
loushang --list-skills
```

`--method` is supported for non-interactive prompt/print/json paths. It is intentionally rejected in TUI and RPC modes until the method step UI and work-event projection path are ready.

## Work Logs

Work logs record `WorkOperation` and `WorkEvent` entries for one-shot prompt/print/json runs:

```bash
loushang --work-log .loushang/work/events.jsonl -p "Run this coding task."
loushang --work-log-inspect .loushang/work/events.jsonl
loushang --work-log-inspect .loushang/work/events.jsonl --work-log-inspect-format plans
```

`--work-log` is not supported in TUI or RPC modes.

## Diagnostics And Export

Diagnostics and exports help inspect what happened in a session:

```bash
loushang --list-diagnostics
loushang --diag-export --diag-output diagnostics.json
loushang --export session.html
```
