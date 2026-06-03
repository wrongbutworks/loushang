# User Guide

English | [中文](../../zh-CN/user-guide/)

The user guide explains the product surfaces that are currently relevant for `loushang code`.

## CLI And TUI

`loushang` is the main CLI entry point. It supports one-shot prompt runs, text/print/json/rpc modes, session controls, model listing, command listing, diagnostics, tools, extensions, skills, methods, packages, export, and work logs.

Use `loushang --tui` to start the terminal UI product surface when you want an interactive coding session. The installed `loushang-tui` command is a convenience entry point for the same TUI mode.

Useful starting commands:

```bash
loushang --help
loushang --list-models
loushang --list-commands
loushang --list-sessions
loushang --tui
loushang -p "Summarize the current project."
```

## Sessions

Sessions preserve the coding conversation and execution record. They are designed for workflows that need resume, fork, export, diagnostics, and later inspection.

Common actions:

```bash
loushang --list-sessions
loushang --resume
loushang --export
```

Inside the interactive surface, built-in slash commands include `/session`, `/resume`, `/fork`, `/clone`, `/tree`, `/export`, `/compact`, `/reload`, and `/quit`.

## Tools

Tools expose executable capabilities to the agent. The coding product includes built-in tool surfaces and options for enabling, disabling, and narrowing tools:

```bash
loushang --tools bash,write -p "Inspect this project."
loushang --no-tools -p "Explain the repository from context only."
```

## Extensions

Extensions are Python files that can register lifecycle hooks, tools, dynamic resources, commands, and flags. Start with the runnable extension examples in [examples/coding/extensions](../../../examples/coding/extensions/).

## Methods And Skills

Methods and skills turn reusable working practices into runtime assets. In the CLI, use:

```bash
loushang --list-methods
loushang --show-method <method>
loushang --method <method> -p "Run this coding task."
loushang --list-skills
```

## Diagnostics And Export

Diagnostics and exports help inspect what happened in a session:

```bash
loushang --list-diagnostics
loushang --diag-export --diag-output diagnostics.json
loushang --export session.html
```
