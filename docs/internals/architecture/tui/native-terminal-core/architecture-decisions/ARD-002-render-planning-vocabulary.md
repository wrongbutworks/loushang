# ARD-002: Render Planning Vocabulary

## Status

Accepted for the native terminal core draft.

## Context

The reference TUI render loop uses a full logical-line buffer, a previous-line
snapshot, viewport tracking, changed-line detection, append-only fast paths, and
fallback full redraws. These ideas are central to avoiding flicker and
scrollback corruption.

Using source variable names directly in loushang architecture documents would
make the design too implementation-specific. The native terminal core needs
stable mechanism terms that can guide Python implementation while remaining
independent of the reference source layout.

## Decision

Use render planning terms from the glossary when describing the render loop:

- `Current Logical Lines`: the current full logical-line render result.
- `Previous Rendered Lines`: the last successfully flushed logical-line snapshot.
- `Changed Line Range`: the minimal changed line interval between current and
  previous lines.
- `Append Update`: the steady-state path for appending new lines without
  rewriting prior transcript content.
- `Viewport Top` and `Previous Viewport Top`: logical-row anchors used to convert
  render-line positions to terminal cursor movement.
- `Logical Cursor Row` and `Hardware Cursor Row`: separate logical content row
  tracking from physical terminal cursor tracking.
- `Working Area High-Water Mark`: the highest rendered line count used to reason
  about stale rows and shrink behavior.
- `Full Recompose`: rebuild the full logical-line buffer from the renderable
  tree.
- `Full Repaint`: rewrite runtime-managed visible UI from current logical lines.
- `Resize Repaint`: full repaint after terminal width or height changes.
- `Recovery Repaint`: full repaint when differential rendering is no longer safe
  for a non-resize reason.
- `Clear Scrollback`: terminal-history clearing operation controlled by repaint
  policy; default-on for resize repaint and default-off for steady-state diff
  updates.
- `Synchronized Flush`: one terminal update representing a render frame.
- `Cursor Marker`: zero-width cursor declaration emitted by a focused renderable.
- `Hardware Cursor Masking`: hide the hardware cursor during terminal writes,
  then position and restore it after the synchronized render frame.
- `Viewport-Relative Cursor Placement`: map logical cursor row to visible screen
  row with `Viewport Top` and use absolute terminal cursor placement after the
  render frame.

## Reference TUI Mapping

This mapping is for migration and implementation guidance.
It is based on observed behavior as of 2026-05-23 and is not a compatibility
contract.

| Reference TUI concept | Loushang term | Notes |
| --- | --- | --- |
| Current rendered-line array | `Current Logical Lines` | Current root render result after overlay composition, cursor-marker extraction, and line normalization. It can be longer than the visible viewport. |
| Previous rendered-line snapshot | `Previous Rendered Lines` | Last successfully written current-line array used as the baseline for diff planning. It is not the persisted session history. |
| First/last changed row indices | `Changed Line Range` | Minimal changed range used for terminal write planning. |
| Appended line segment | `Append Update` | Scroll-friendly append path. |
| Current viewport anchor | `Viewport Top` | Current logical top of visible viewport within current logical lines during planning. |
| Previous viewport anchor | `Previous Viewport Top` | Saved viewport top from the prior flush. |
| Logical content cursor row | `Logical Cursor Row` | Logical content cursor baseline. |
| Last known physical cursor row | `Hardware Cursor Row` | Runtime's last known terminal cursor row. |
| Maximum rendered height | `Working Area High-Water Mark` | High-water mark for clearing stale rows. |
| Full render with optional clear | `Full Recompose` + `Full Repaint` / `Resize Repaint` + policy-controlled `Clear Scrollback` | The reference combines these concerns in one path. Loushang keeps clear scrollback explicit in diagnostics while defaulting resize to deterministic clear. |
| width/height resize full render | `Resize Repaint` | Preferred resize path for deterministic visual stability. |
| clear screen / clear scrollback escape sequence | `Full Repaint` / `Clear Scrollback` | Clear screen may be part of repainting managed UI. Clear scrollback is policy-controlled and default-on for resize repaint. |
| synchronized output buffer | `Synchronized Flush` | One buffered terminal update per render frame. |
| Zero-width cursor marker | `Cursor Marker` | Rendered marker stripped before terminal output. |
| Hide cursor during writes and position it after render | `Hardware Cursor Masking` | Loushang may restore cursor visibility after positioning until a fake editor cursor is implemented. |
| cursor row mapped through viewport | `Viewport-Relative Cursor Placement` | Loushang uses absolute visible-screen cursor placement after the frame to avoid terminal autowrap drift. |

## Source-Checked Semantics

The reference implementation renders a current line array from the active root
UI tree: child containers concatenate their rendered lines in a stable order, and
the interactive coding UI projects header, chat, pending messages, status,
widgets, editor, and footer regions into that root.

The render loop then composites overlays into the current line array, extracts
the cursor marker from the bottom visible viewport, applies line resets, computes
the changed row range against the previous line snapshot, and writes only the
changed range when safe. On a successful flush, the previous snapshot becomes the
current line array.

Therefore current and previous rendered lines are full arrays for the active root
UI tree. They are not only the visible terminal rows. They are also not the
complete session archive: after compaction, navigation, or other UI rebuilds,
the coding UI clears and rebuilds the chat region from a session context that
may contain a compaction summary plus retained recent messages instead of every
stored session entry.

## Consequences

- Key designs and implementation plans can describe render behavior without
  depending on reference variable names.
- Tests should use loushang terms. For example, test names should prefer
  `test_changed_line_range.py` over names tied to source variable names.
- Implementation may still use local variable names that are natural in Python,
  but public architecture docs should keep the glossary vocabulary.

## Rejected Alternatives

### Copy Reference Variable Names

Rejected because it would make architecture documents look like source-code
annotations and would obscure the actual design invariants.

### Omit Mechanism Terms Until Implementation

Rejected because render-loop stability is a core product constraint. The team
needs shared vocabulary before writing key designs and tests.
