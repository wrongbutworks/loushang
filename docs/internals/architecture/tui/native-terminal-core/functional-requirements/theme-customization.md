# Functional Requirements: Theme Customization

## FR-TH-001: Structured Theme Tokens

The TUI must support structured theme tokens for core UI parts, transcript
records, markdown, code, diffs, thinking blocks, tool execution records, status
fields, and surfaces.

Related: SC-TH-001

## FR-TH-002: Theme Capability Degradation

Theme resolution must adapt requested styles to terminal capabilities. For
example, truecolor may degrade to basic colors, hyperlinks may render as plain
URLs, and unsupported emphasis may be omitted.

Related: NFR-PORT-001

## FR-TH-003: Theme Invalidation

When theme tokens change, cached styled render output must be invalidated before
the next render. Renderables and UI parts still must not write directly to the
terminal during invalidation.

Related: SC-TH-001, NFR-EX-001

## FR-TH-004: Product Theme Loading

The generic TUI core owns theme representation and resolution. Product adapters
own where themes come from, such as JSON files, built-in defaults, settings, or
extension-provided themes.

Related: FR-CI-001
