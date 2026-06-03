# Contributing

English | [中文](../zh-CN/contributing.md)

Loushang is in active early development. Contributions should keep the current public surface honest: document what works today, separate roadmap direction from shipped behavior, and keep internal design material out of the primary user path.

## Local Development

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

The equivalent shortcut is `make bootstrap`.

For Python work in this repository, use the local virtual environment in `.venv/`.

## Documentation Changes

- Public user documentation belongs under `docs/en/` and `docs/zh-CN/`.
- Historical architecture, design decisions, specs, plans, and glossary drafts belong under `docs/internals/`.
- Keep English and Chinese public pages structurally aligned.
- Do not present roadmap surfaces as complete shipped behavior.

## Verification

For documentation-only changes, verify that changed relative links resolve and that the documentation tree still separates public and internal material clearly. For code changes, run the relevant tests and linters before claiming completion.
