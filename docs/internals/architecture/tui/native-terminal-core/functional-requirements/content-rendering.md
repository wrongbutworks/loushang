# Functional Requirements: Content Rendering

## FR-CR-001: Markdown Rendering

The TUI must render markdown content through a terminal-safe renderer. Initial
markdown support includes paragraphs, headings, ordered and unordered lists,
links, inline code, fenced code blocks, block quotes, emphasis, strikethrough,
and horizontal rules.

Markdown rendering must use the shared cell-width model for wrapping and must
not import heavy renderers into the raw runtime core at module import time.
Markdown parsing uses `markdown-it-py`; rendering remains owned by loushang TUI
so parser output is converted into terminal-safe logical lines instead of Rich
console output or HTML.

Related: SC-CR-001, NFR-TC-001, ARD-004

## FR-CR-002: Code Blocks

Code blocks must render with indentation, optional language labels, optional
syntax highlighting, and stable wrapping or horizontal truncation policy.

Syntax highlighting is an adapter concern. If a highlighter is unavailable, code
blocks render as plain styled text.

Related: SC-CR-001, NFR-PORT-001

## FR-CR-003: Diff Blocks

Diff content must render additions, deletions, context, file headers, and hunks
with theme-controlled styles. The renderer must preserve line identity so diffs
remain stable under terminal resize.

Related: SC-CR-001, NFR-TC-001

## FR-CR-004: Image Blocks

Image content must have a text fallback. Terminal image protocols may be
supported through capability-specific adapters, but the raw runtime core must not
depend on a specific image protocol for correctness.

Related: NFR-PORT-001

## FR-CR-005: Thinking Blocks

Thinking blocks are rendered only when product data supplies them. The TUI must
support visible, collapsed, hidden-by-policy, and unavailable states.

Related: SC-CR-003

## FR-CR-006: Tool Execution Records

Tool execution records must support running, completed, failed, cancelled, and
truncated states. They must support a per-tool timing marker: elapsed while
running and took after completion.

Related: SC-CR-002, FR-CI-002

## FR-CR-007: Error Records

Error records must render concise user-facing summaries by default and may expose
diagnostic details only when the product adapter enables verbose diagnostics.

Related: SC-ERR-001, FR-CI-007
