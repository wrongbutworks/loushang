# ARD-004: Markdown Parser And Renderer Boundary

## Status

Accepted for the native terminal core draft.

## Context

Markdown is a primary content format for coding assistant transcript output. The
TUI needs reliable parsing for headings, lists, links, inline code, emphasis,
strikethrough, fenced code, quotes, tables, and future nested content. Continuing
to grow a regular-expression based parser would duplicate CommonMark behavior
and make nested inline and block rendering fragile.

The Python ecosystem offers two tempting options:

- `markdown-it-py`: a pure Python port of markdown-it that exposes a markdown
  token stream and syntax tree helpers.
- Rich: a broad terminal rendering framework that includes markdown rendering,
  console measurement, segment rendering, tables, live display, and themes.

The native terminal core already owns terminal measurement, logical line
composition, line-level diffing, synchronized flushing, cursor placement, and
theme token resolution. Markdown parsing should improve content structure
without transferring terminal rendering ownership away from the TUI runtime.

## Decision

Use `markdown-it-py` as the Markdown parser for `loushang.tui`.

Do not use Rich as the `loushang.tui` markdown renderer or as a dependency of
the native terminal core rendering path.

Markdown rendering follows this boundary:

- `markdown-it-py` parses markdown into tokens or a syntax tree.
- loushang maps parser output into TUI-owned markdown block and inline tokens.
- loushang renders those tokens into ANSI-safe logical lines.
- loushang owns cell-width measurement, wrapping, truncation, spacing policy,
  theme token resolution, and terminal operation planning.
- Rich, Pygments, or any future highlighter may be used only through optional
  adapters that do not write to the terminal and are not imported by the raw
  runtime core at module import time.

## Consequences

- Markdown behavior can move closer to CommonMark and token-based reference
  rendering without building a parser from scratch.
- The TUI keeps a single terminal writer and a single cell-width model.
- Theme customization remains based on loushang tokens such as
  `markdown.heading.level2`, `markdown.inline_code`, and `markdown.link`.
- Parser output can be cached by markdown text, width, theme version, and
  terminal capabilities.
- Rich may remain available to other product layers or legacy tools, but it is
  not part of the native terminal core markdown rendering contract.

## Rejected Alternatives

### Continue With A Hand-Written Markdown Parser

Rejected because each new CommonMark feature would add parser complexity and
edge cases. Nested inline tokens, nested lists, block quotes containing block
content, reference links, hard breaks, and tables are better handled by a parser
library.

### Use Rich Markdown Rendering In Core

Rejected because Rich is a terminal rendering framework, not just a parser. It
brings its own console, segment, measurement, theme, table, and live-rendering
models. Those models overlap with native terminal core responsibilities and can
conflict with full logical lines, line-level diffing, managed viewport
updates, cursor markers, and loushang theme tokens.

### Use `markdown-it-pyrs` As The Default Parser

Rejected for the default path because it vendors compiled Rust code and is a
less conservative packaging choice for a core dependency. It may be evaluated
later as an optional acceleration backend after the `markdown-it-py` adapter and
renderer contract are stable.

## Migration Guidance

- Add `markdown-it-py` as a direct project dependency instead of relying on Rich
  to bring it transitively.
- Replace the current lightweight parser incrementally:
  1. introduce a parser adapter that converts `markdown-it-py` tokens into
     loushang markdown tokens
  2. keep existing renderer tests as the compatibility contract
  3. add nested list, quote, table, hard-break, and link tests before replacing
     each corresponding hand-written path
  4. remove the hand-written parser only after the adapter covers the existing
     and target behaviors
- Keep all Rich/Pygments imports out of `src/loushang/tui` module import paths.
