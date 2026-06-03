# Getting Started

English | [中文](../../zh-CN/getting-started/)

This guide gets you from a fresh clone to a first `loushang code` run.

## Requirements

- Python 3.11 or newer.
- A model provider credential for online runs.
- A terminal environment that can run Python virtual environments.

## Install From Source

```bash
git clone https://github.com/<owner>/loushang.git
cd loushang

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Check The CLI

```bash
loushang --help
loushang --list-models
loushang --list-commands
```

## Run A First Prompt

```bash
loushang -p "Inspect this repository and summarize what it does."
```

Use `--model` or provider-specific environment variables when you need to select a concrete model route. Project and example model catalog files can be placed under `.loushang/models/` or passed explicitly where supported.

## Next Steps

- Read the [User Guide](../user-guide/) for sessions, commands, tools, extensions, methods, and diagnostics.
- Read the [Examples](../examples/) page for runnable coding and AI SDK scenarios.
- Read the [Reference](../reference/) page when you need exact CLI and configuration surfaces.
