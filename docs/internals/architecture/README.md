# Internal Architecture

[Internals](../README.md)

## Status

Architecture workspace.

This directory contains both live architecture sources and historical/draft
architecture material. Not every file here has the same authority.

## Reading Rule

Read in this order for current implementation decisions:

1. [Architecture Overview](architecture-overview.md)
2. [Cross-Layer Architecture Principles](loushang-architecture-principles.md)
3. [Subsystems](subsystem.md)
4. Accepted ARDs under subsystem directories, especially
   [agent harness boundaries](agent/ARD-001-agent-harness-and-product-adapters.md),
   [harness product adapter substrate](agent/ARD-002-harness-product-adapter-substrate.md), and
   [coding](coding/ARD-001-coding-product-boundaries.md)
5. Component interfaces and core data object notes for the subsystem being edited
6. Draft/history/reference material only when extra rationale is needed

When files conflict, prefer current code/tests and accepted ARDs over drafts,
history, experimental notes, or legacy documents.

## Live Architecture Areas

- [Cross-Layer Architecture Principles](loushang-architecture-principles.md)
- [AI](ai/README.md)
- [Agent](agent/README.md)
- [Channel](channel/README.md)
- [Coding](coding/loushang-coding-system-context.md)
- [Method](method/README.md)
- [Work](work/README.md)
- [TUI](tui/README.md)
- [Harness TUI](harnesstui/README.md)
- [Monorepo Conventions](loushang-monorepo-conventions.md)

For terminal architecture evaluation, read the TUI overview together with
[KD-010: Terminal Playback Harness](tui/native-terminal-core/key-designs/KD-010-terminal-playback-harness.md)
and [HarnessTUI Conversation Playback Testing](harnesstui/README.md#conversation-playback-testing).

## Non-Live Reference Areas

- [Architecture Drafts](drafts/README.md)
- [TUI History](tui/history/README.md)

Historical terminology and old paths may be preserved in non-live areas. Do not
rewrite those files just to match current Python package names unless a live
migration plan explicitly asks for it.
