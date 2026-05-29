# KD-009: Theme Resolution

## Purpose

Support product-level visual customization without coupling style loading to the
raw terminal runtime.

## Design

The generic TUI core defines theme token names and resolved terminal style
values. Product adapters own where theme definitions come from: built-in
defaults, JSON files, settings, extension-provided themes, or tests.

Theme resolution happens before renderables produce styled logical lines. If
terminal capabilities are limited, the resolver degrades style requests before
terminal output is planned.

Theme changes invalidate cached styled output. Invalidation requests a render;
it does not write the terminal directly.

## Token Shape

Theme tokens use dotted namespaces by UI part or content domain:

```text
status.model
status.cwd
status.branch
composer.prompt
surface.border
surface.selection.active
markdown.heading.1
markdown.code.inline
markdown.code.block
thinking.visible
thinking.collapsed
tool.running
tool.error
diff.add
diff.delete
```

Theme definitions may be loaded from JSON or another product-owned source, but
the resolver exposes typed token lookup to renderables and renderers.

## Degradation And Cache Order

The resolver first merges defaults, product theme definitions, and extension
overrides into semantic tokens. It then resolves semantic tokens against terminal
capabilities, degrading unsupported colors, links, or emphasis into supported
styles. Renderables cache only resolved styles scoped by theme version and
terminal capability profile.

Theme invalidation may be global at first. More granular invalidation by UI part
family is allowed later, but it must not change terminal writer ownership.

## Test Obligations

- changing theme tokens invalidates markdown and status cached output
- truecolor can degrade without changing layout width
- hyperlink styles degrade to plain text or visible URLs
- extension themes cannot bypass terminal writer rules
- resolved token lookup is deterministic for a theme version and capability
  profile
