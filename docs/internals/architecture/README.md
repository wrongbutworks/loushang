# Internal Architecture

[Internals](../README.md)

## Status

Architecture workspace.

This directory contains both live architecture sources and historical/draft
architecture material. Not every file here has the same authority.

## Reading Rule

Read in this order for current implementation decisions:

1. [Architecture Overview](architecture-overview.md)
2. [Subsystems](subsystem.md)
3. Accepted ARDs under subsystem directories, especially
   [coding](coding/ARD-001-coding-product-boundaries.md)
4. Component interfaces and core data object notes for the subsystem being edited
5. Draft/history/reference material only when extra rationale is needed

When files conflict, prefer current code/tests and accepted ARDs over drafts,
history, experimental notes, or legacy documents.

## Live Architecture Areas

- [AI](ai/README.md)
- [Agent](agent/README.md)
- [Coding](coding/loushang-coding-system-context.md)
- [TUI](tui/README.md)
- [Monorepo Conventions](loushang-monorepo-conventions.md)

## Non-Live Reference Areas

- [Architecture Drafts](drafts/README.md)
- [TUI History](tui/history/README.md)

Historical terminology and old paths may be preserved in non-live areas. Do not
rewrite those files just to match current package names unless a live migration
plan explicitly asks for it.
