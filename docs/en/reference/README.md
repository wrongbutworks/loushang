# Reference

English | [中文](../../zh-CN/reference/)

This page collects reference entry points for current users and contributors.

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

## Output Formats

Several list and export commands support machine-readable output:

```bash
loushang --list-models --list-models-format json
loushang --list-sessions --list-sessions-format json
loushang --list-commands --list-commands-format json
loushang --export session.jsonl --export-format jsonl
```

## Slash Commands

Built-in interactive commands include:

```text
/settings /model /scoped-models /export /import /share /copy /name
/session /terminal /changelog /hotkeys /fork /clone /tree
/login /logout /new /compact /resume /reload /quit
```

## TUI

- [TUI Runner](tui-runner.md): public lifecycle entry point for terminal apps built with `loushang.tui`.
- [TUI Editing](tui-editing.md): reusable TextInput, Composer, selection-aware editing, keybindings, and playback smoke checks.
