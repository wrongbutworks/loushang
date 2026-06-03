# Native Terminal Core Glossary

This glossary defines the canonical terms used by the native terminal core
requirements, architecture decisions, key designs, renderable specifications,
and UI part specifications. Use these terms consistently in new TUI documents.

## Terminal And Screen Model

### Native Terminal

The user's normal terminal screen and scrollback. The primary coding workflow
runs here instead of requiring a fullscreen alternate-screen application.

Native terminal does not mean "plain print only." The runtime may still use
temporary terminal input modes for immediate key reading, cursor movement, ANSI
styling, synchronized updates, and terminal capability detection. Any terminal
mode changes must be covered by terminal restoration.

### Alternate Screen

A terminal mode with a separate fullscreen buffer, commonly used by editors and
fullscreen terminal apps. The native terminal core must not require alternate
screen for the primary coding workflow because it would hide normal shell
scrollback.

### Physical Terminal

The actual terminal device, including viewport size, current scroll position,
hardware cursor, terminal modes, scrollback, and supported capabilities.

### Viewport

The visible terminal rows and columns at a point in time. The viewport may move
when the terminal scrolls, when output is printed, or when the user scrolls.

### Scrollback

The terminal-owned history above the current viewport. Committed transcript
content should be visible through normal scrollback.

### Hardware Cursor

The terminal cursor controlled by escape sequences. The runtime owns hardware
cursor placement. Renderables declare logical cursor positions; they do not move
the hardware cursor directly.

### Terminal Capability

A feature supported by the current terminal, such as truecolor, synchronized
updates, hyperlinks, bracketed paste, focus events, mouse tracking, or image
protocols. The runtime detects capabilities and degrades gracefully when a
capability is unavailable.

### Terminal Capability Detection

The process of discovering optional terminal features through terminal queries,
environment hints, and conservative fallback rules. Capability detection should
produce a stable capability snapshot for renderers and UI parts rather than
making each component inspect environment variables independently.

### Terminal Environment Detection

The process of identifying terminal host context such as tmux, screen, Kitty,
Ghostty, WezTerm, iTerm2, VS Code terminal, Windows Terminal, Termux, SSH, or
platform-specific terminals. Environment detection informs capability detection,
input protocol choices, resize policy, clipboard strategy, and safe fallback
behavior.

Common environment hints:

| Probe hint | Capability implication |
| --- | --- |
| `TMUX` or `TERM=tmux-*` / `TERM=screen-*` | Disable images and hyperlinks by default. |
| `KITTY_WINDOW_ID` or `TERM_PROGRAM=kitty` | Prefer Kitty image protocol. |
| `GHOSTTY_RESOURCES_DIR`, `TERM_PROGRAM=ghostty`, or `TERM` containing `ghostty` | Prefer Kitty image protocol. |
| `WEZTERM_PANE` or `TERM_PROGRAM=wezterm` | Prefer Kitty image protocol. |
| `ITERM_SESSION_ID` or `TERM_PROGRAM=iTerm.app` | Prefer iTerm2 image protocol. |
| `TERM_PROGRAM=vscode` | Enable truecolor and hyperlinks, with no image protocol. |
| `COLORTERM=truecolor` or `COLORTERM=24bit` | Enable truecolor. |
| `WT_SESSION` | Enable truecolor for Windows Terminal. |

### Image Protocol

A terminal graphics protocol used to display inline images, such as Kitty
graphics protocol or iTerm2 inline image protocol. Image protocol support must
be capability-gated and must fall back to textual image descriptions when the
current terminal or multiplexer is unsafe.

### Cell Dimensions

The pixel width and height of one terminal cell. Cell dimensions are distinct
from cell width: cell width measures displayed text columns, while cell
dimensions are used to scale terminal images into a target number of rows and
columns.

### Terminal Restoration

The process of returning the terminal to a safe user shell state on exit,
including restoring raw/cbreak mode, showing the cursor, disabling temporary
keyboard protocols, disabling bracketed paste, and draining residual input when
needed.

### Terminal Writer

The only code path that writes terminal control sequences and text to stdout.
The native terminal core requires one runtime-owned terminal writer. Renderables,
UI parts, product adapters, and extensions return data or intents; they do not
write to stdout, move the cursor, or clear terminal lines.

## Render Model

### Logical Screen

The complete ordered list of logical lines produced by the current active render
tree before terminal diffing. It may include lines above the visible terminal
viewport when those lines are still part of the active UI tree. It also includes
transient bottom-frame UI.

Logical screen is an internal render model. It is not the same as terminal
scrollback, and it is not the same as the complete persisted session history.

### Active Logical Screen

The logical screen currently owned by the TUI runtime and eligible for render
planning. It is the full line array for the active render tree, not the full
session archive and not only the visible terminal viewport.

The active logical screen may include current header rows, a chat or transcript
container, pending-message rows, status rows, extension widget rows, editor rows,
footer rows, active streaming drafts, active tool records, overlays, and
bottom-frame UI. It excludes session-store entries that are no longer projected
into the current UI and external terminal scrollback that existed before the TUI
rendered it.

### Logical Line

A rendered line with text, style metadata, and enough width information for
diffing and cursor mapping. A logical line may contain ANSI styling in the final
terminal output, but measurement uses terminal cell width rather than Python
string length.

### Render Tick

A single runtime render attempt. A render tick collects current state, asks the
renderable tree for a logical screen, computes terminal operations, and flushes
the result through the terminal writer.

### Render Pass

The renderable-tree evaluation step within a render tick. It produces render
results; it does not write to the terminal.

### Render Operation

A terminal write operation planned by the runtime, such as moving the cursor,
writing a line, clearing a line fragment, showing or hiding the cursor, or
flushing a synchronized update. Renderables and UI parts must not create raw
terminal writes themselves. Render operations are runtime-internal terminal
plans; they are not renderable render results.

### Differential Rendering

Line-level comparison of current logical lines with previous rendered lines,
emitting only the operations required to show the next frame when it is safe to
do so. The native terminal core does not use character-level terminal diffing as
the steady-state render strategy.

### Reflow

Recomputing logical line breaks, renderable layout, and cursor mapping after
terminal width changes or content updates. Reflow must preserve transcript order
and must not duplicate previously committed transcript blocks.

### Resize-Stable Reflow

Reflow performed after terminal size changes while preserving visual stability.
The runtime recomputes the renderable tree, soft wraps, region heights, and
cursor mapping from the new terminal constraints, then updates the managed
viewport through line-level differential rendering or a resize repaint.

Resize-stable reflow must not duplicate transcript blocks, lose user input,
displace the composer or status area, or cause visible full-screen flicker.

### Full Recompose

Re-rendering the complete renderable tree into current logical lines. Full
recompose is normal and cheap enough to use for resize, theme changes, overlay
changes, and content updates. It does not imply terminal clearing.

### Full Repaint

Rewriting the runtime-managed visible area from current logical lines. Full
repaint is allowed for first render, resize, constrained-height recovery, overlay
geometry changes, or documented unsafe viewport transitions. It is distinct from
clear scrollback.

### Resize Repaint

A full repaint triggered by terminal width or height changes. Resize repaint
prioritizes deterministic visual stability: composer, status, overlays, cursor
mapping, and transient regions must return to coherent positions after the
resize.

### Clear Scrollback

A terminal operation that clears terminal history, such as CSI 3 J on terminals
that support it. Clear scrollback is separate from full repaint and is enabled
by default for resize repaint. It remains policy-controlled and must not be used
by steady-state diff updates.

### History Preservation Policy

The product policy that controls how aggressively the runtime preserves terminal
history. The default native terminal core policy is best effort: steady-state
streaming should preserve scrollback, resize uses deterministic repaint with
clear scrollback by default, and history-preserving deployments may disable
resize clear scrollback explicitly.

### Synchronized Update

A terminal update mode that lets multiple writes appear as one visual frame when
the terminal supports it. The runtime should use this for render flushes to avoid
visible intermediate states.

### Managed Viewport

The rows the runtime currently believes it owns or may safely update in place.
The managed viewport includes the bottom frame and may include recently rendered
logical-screen lines. It never grants permission to rewrite arbitrary historical
scrollback.

### Unsafe Viewport Transition

A state change where the runtime can no longer prove that its previous rendered
lines are still at the expected physical positions. Examples include writes to
stdout from outside the TUI runtime, terminal scrollback movement that affects
managed rows, or a resize/reflow case that invalidates row mapping. Recovery
behavior must be explicit and must avoid stale row assumptions. Re-establishing
the managed viewport after such a transition is a runtime responsibility.

### Previous Rendered Lines

The logical-line snapshot from the last successful render flush. It is the
previous active logical screen line array after overlay composition,
cursor-marker extraction, and terminal-output line normalization.

Previous rendered lines are a diff baseline, not a durable transcript store.
They may include lines above the current visible viewport if those lines were in
the previous active UI tree. They may shrink or be replaced when the active
render tree is rebuilt after compaction, navigation, clear, force render, resize
repaint, or another explicit UI rebuild.

### Current Logical Lines

The complete logical-line list produced by the current render pass. It is the
full line array for the current active logical screen. The render loop first
renders the root tree, then composites overlays, extracts cursor markers, and
applies terminal-output line normalization before using the array for diffing and
writing.

Current logical lines are complete for the active render tree, but they are not
the complete terminal scrollback and not necessarily the complete persisted
session history.

### Changed Line Range

The smallest logical-line range that differs between previous rendered lines and
current logical lines. The render loop uses this range to plan minimal terminal
updates when the range is inside the managed viewport.

### Append Update

A differential render path used when current logical lines only append after the
previous rendered lines. Append updates are preferred because they let the
terminal scroll naturally without rewriting earlier transcript content.

### Rendered Line Array

The concrete ordered array of terminal-ready logical-line strings used by the
render loop. The current array and the previous successful array form the
line-level diff baseline for the next terminal update.

The rendered line array is intentionally bounded by the active logical screen.
Long-lived session history must be represented through session storage,
compaction summaries, and transcript windows rather than by keeping every past
line in the per-tick render array.

### Viewport Top

The logical-line index that corresponds to the first visible terminal row during
render planning.

### Previous Viewport Top

The viewport top recorded after the previous successful render flush. It lets the
runtime translate logical-line positions into relative terminal cursor movement.

### Logical Cursor Row

The logical row the runtime uses as the render cursor baseline, usually the end
of the managed logical screen.

### Hardware Cursor Row

The runtime's last known physical terminal cursor row. It may differ from the
logical cursor row when the runtime positions the hardware cursor for IME or
focused input.

### Working Area High-Water Mark

The largest logical-screen height the runtime has rendered in the current
terminal session. It helps decide when shrinking content requires clearing stale
rows or a recovery repaint.

### Recovery Repaint

A full repaint used to re-establish a safe managed viewport after an unsafe
transition, non-resize recovery condition, width reflow, or stale-row condition.
It may share implementation with resize repaint. It does not imply clear
scrollback.

### Synchronized Flush

A render flush emitted as one terminal update, preferably using synchronized
terminal output when supported. It is the runtime's frame boundary for terminal
writes.

### Cursor Marker

A zero-width marker emitted by a focused renderable to declare the logical cursor
position. The runtime strips the marker from output and maps it to the hardware
cursor location.

### Hardware Cursor Masking

The render-loop practice of hiding the terminal hardware cursor while runtime
write operations are in progress, then positioning and restoring it after the
render frame. This prevents visible cursor jumps through transcript or status
rows during changed-range updates.

### Viewport-Relative Cursor Placement

Mapping a logical cursor row to a visible terminal row by subtracting `Viewport
Top`, then positioning the hardware cursor with absolute visible-screen
coordinates. This keeps the next input render anchored to the composer even if
the last rendered line reached the terminal's right edge.

## Transcript Model

### Transcript

The user-visible conversation history. In the native terminal core, stable
transcript content is represented by display records and may become visible in
normal terminal scrollback after it is committed.

### Session Store

The durable product-owned storage for the complete conversation session, such as
JSONL files, a database, or segmented files. The session store may contain far
more data than the active logical screen. The render loop must not treat the
session store as the per-tick rendered line array.

### Transcript Window

The product adapter's projected subset of session history used by the TUI for
the active logical screen. A transcript window typically contains a compaction
summary, retained recent display records, active draft records, and active tool
records.

Transcript windows are the normal way to keep full line array rendering
bounded while preserving complete session history in the session store.

### Evicted Transcript Prefix

A stable prefix of transcript records that is no longer projected into the
active logical screen. It remains in the session store and may already be present
in terminal scrollback, but it is not part of current logical lines or previous
rendered lines.

### Transcript Area

The conceptual region above transient UI. It is backed by normal terminal
scrollback and contains stable transcript content, not active composer or status
UI.

### Display Record

A product-neutral record describing stable transcript content before rendering.
Examples include user prompt, assistant response, tool summary, error,
interruption, divider, and worked-divider records.

Display records are data. The renderer decides how records become logical lines.
One committed transcript block typically corresponds to one display record after
rendering, though a renderer may combine or split records according to product
policy.

### Content Block

A nested content item inside a display record. For example, an assistant message
record may contain text blocks, thinking blocks, and tool-call references.

### Assistant Message Record

A display record for assistant output. It may contain multiple content blocks and
may remain a draft record while streaming.

### Thinking Block

A provider- or product-supplied assistant content block that represents model
thinking or reasoning output intended for UI display. The TUI must not infer,
invent, or expose hidden reasoning that was not supplied through product data.

### Thinking Visibility

The display policy for thinking blocks. Common states are visible, collapsed,
hidden by policy, or unavailable. Collapsed thinking renders a label rather than
the full thinking content.

### Tool Execution Record

A display record for one tool call lifecycle. It may include the tool name,
input summary, running state, output summary, truncation notice, error state,
expand/collapse state, and timing marker.

### Tool Timing Marker

A timing label associated with a tool execution record. Running or partial tool
output may show elapsed time; completed tool output may show took time. This is
per-tool timing, distinct from the run-level worked divider.

### Error Record

A stable transcript record for a runtime, provider, product, or recoverable TUI
error that is not owned by a specific tool execution record.

### Tool Error

An error state inside a tool execution record, such as command failure,
permission denial, timeout, cancellation, or truncated failed output.

### Committed Transcript Block

A stable output block that may remain in terminal scrollback, such as a
submitted user prompt, final assistant response, tool summary, error,
interruption notice, or worked divider.

Committed transcript blocks must not be rewritten, duplicated, or partially
erased by transient UI updates.

### Draft Record

An in-progress display record that is still changing, such as an assistant
streaming response. A draft record is rendered as part of the current logical
screen until completion. It becomes committed only when the product adapter marks
it stable.

### Commit

The transition from transient or draft state into stable transcript content.
After commit, the runtime may allow the content to scroll naturally into terminal
scrollback, but future transient renders must not mutate it.

### Working Line

A transient line shown while a run is active. It reports elapsed time and any
configured interrupt affordance. It is not transcript content while active.

### Worked Divider

A stable transcript block committed after a run completes, for example
`Worked for 28.6s`. It replaces the transient working line after the run
completes and is then stable transcript content.

## Layout Model

### Screen Region Stack

The ordered vertical list of region containers assembled by the screen root. It
defines screen composition before terminal diffing. It is the loushang concept
corresponding to a reference TUI root that adds header, transcript, pending,
status, widget, editor, and footer containers in order.

### Region Container

A renderable that owns one named screen region. Region containers provide stable
layout slots; UI parts and transcript views live inside those slots.

### Header Area

An optional region for startup notices, onboarding text, changelog summaries, or
other product-provided introductory content. In native terminal layouts, header
content is not fixed terminal chrome unless an explicit layout policy makes it
so.

### Transcript Render Area

The region container that renders display records, draft records, and transcript
UI parts. It may map to the transcript area and is allowed to scroll naturally
into terminal scrollback.

### Bottom Frame

The runtime-owned mutable region at the bottom of the viewport. It contains
transient UI such as surface area, pending queues, working line, composer,
separator, and status.

### Transient Area

The conceptual region that contains runtime-owned UI which may be redrawn in
place. It includes surface, pending queue, working, composer, separator, and
status regions.

### Extension Widget Slot

An optional region where product adapters or extensions can insert transient
runtime-owned UI above or below the composer. Widget slots are part of the
screen region stack and must still obey renderable, focus, and terminal writer
rules.

### Surface Area

The bottom-frame region above the composer where temporary interactive surfaces
are hosted. Surfaces that are not overlays are rendered inside the surface area.
Overlays may be positioned outside the surface area by the surface host
according to layout policy.

### Pending Queue Area

The bottom-frame region that displays queued follow-up, pending steering, or
other submitted inputs waiting for product handling. In the default coding
layout, it appears above the working line and grows upward.

### Working Line Area

The bottom-frame region that displays transient run progress such as
`Working 3.01s` and interrupt affordances. It disappears when the run completes
or is interrupted.

### Composer Area

The bottom-frame region containing editable input. It grows upward when input
soft-wraps or contains explicit newlines. It is rendered by the composer
UI part.

### Separator Area

The optional visual gap or divider between the composer and the status area. In
the default coding layout, this is one blank line.

### Status Area

The bottom-most status row by default. It is one terminal row unless explicitly
disabled or replaced by a product layout. Lower-priority fields are omitted or
truncated when space is constrained. The default renderer avoids writing into
the final terminal cell to prevent bottom-row autowrap artifacts.

### Footer Area

An optional bottom region for product status or custom footer UI. In the default
coding layout, the status area is the footer area.

### Screen Root

The top-level renderable that assembles transcript records and bottom-frame UI
into a logical screen. The screen root owns layout composition, not terminal
writer access.

### Layout Policy

Configuration that decides which regions are present, their priority, and how
they shrink or disappear under constrained height or width. Product adapters may
choose a layout policy, but the runtime enforces terminal safety.

## Render Framework Terms

### Renderable

The framework-level render protocol. A renderable accepts constraints and returns
a render result plus optional input or focus declarations. A renderable has no
direct terminal writer access.

### Container

A renderable that owns child renderable layout. Containers decide child ordering,
constraints, clipping, and focus traversal.

### Focusable

A renderable that can receive keyboard input and declare a logical cursor
position. Focusable renderables return intents or state changes; they do not own
terminal input loops.

### Focus

The runtime-managed right to receive keyboard input events. Only one renderable
or surface holds focus at a time. When a surface closes, the runtime restores
focus to the previous holder when possible.

### Surface

A temporary interactive renderable hosted by the TUI runtime, such as
autocomplete, command palette, model selector, settings, help, changelog, or
confirmation dialog. A surface may be laid out in the surface area or positioned
as an overlay according to layout policy.

### Overlay

A surface presentation mode that may cover or float over another region. Overlay
geometry and z-order are controlled by the runtime or surface host, not by
product code.

### Surface Host

The runtime-owned renderable that owns surface lifetime, focus capture, close
reasons, stacking, and focus restore. It hosts surfaces; a surface may be laid
out in the surface area or positioned as an overlay according to layout policy.
When a surface is active, Esc is offered to that surface before it is interpreted
as an abort control for an active run.

### Selection Surface

A surface for choosing one or more items from a list. It owns display,
navigation, selection state, filtering, and close reasons; the product adapter
owns the meaning of selected items.

### Approval Surface

A surface for permission or authorization decisions, such as allowing a command,
file edit, network access, or other guarded action. It displays the action and
risk context, then returns an approval intent such as allow once, allow always,
deny, edit, details, or cancel.

### Dialog Surface

A focused surface for simple confirm/cancel or acknowledgement workflows. It
returns an explicit close reason and must not submit composer text implicitly.

### Approval Intent

The semantic result returned by an approval surface. Approval intents are product
adapter inputs; the TUI does not execute the guarded action directly.

### Close Reason

The explicit reason a surface closed, such as confirm, cancel, escape, abort,
blur, replaced, or completed. Close reasons are data returned to the caller; they
are not inferred from terminal side effects.

### Render Constraint

The width and height budget passed to a renderable during rendering. Renderables
must respect constraints or report controlled overflow, not write past their
assigned area.

### Render Result

The structured output from a renderable render call. It contains logical lines,
optional cursor declarations, and optional metadata used by the runtime.

## UI Part Terms

### UI Part

A concrete, visible, reusable UI building block built from renderables. A UI part
may itself implement the renderable protocol, but architecture documents use
`UI Part` when referring to product-facing pieces such as composer, status bar,
pending queue, tool execution view, or approval prompt.

Initial UI part families include:

- basic parts: text, truncated text, spacer, box, border, loader
- input parts: composer, text input, autocomplete view
- status and frame parts: status bar, working line, pending queue view
- transcript parts: user prompt view, assistant message view, thinking view,
  tool execution view, error view, markdown block, code block, image block, diff
  block
- selection and surface parts: select list, settings list, command palette,
  approval prompt, dialog view, help viewer, changelog viewer

## Input Model

### Input Event

A normalized keyboard, paste, mouse, focus, resize, or signal event produced by
the terminal input reader.

### Signal

A normalized operating-system or terminal signal that affects the runtime, such
as resize, interrupt, terminate, suspend, or resume. Signals are converted into
runtime events or lifecycle actions instead of being handled by renderables
directly.

### Keybinding

A mapping from input events to actions or intents. Keybindings are owned by the
runtime or product adapter configuration; renderables receive already-routed
events when possible.

### Intent

A semantic action returned by a renderable, UI part, surface, or product
adapter, such as submit prompt, open command surface, select item, cancel
surface, approval decision, abort run, or change model. Intents cross
boundaries; raw key events should not leak through the entire system.

### Composer

The editable input UI part used for prompt text, follow-up text, steering
text, and slash command input.

### Soft Wrap

Visual wrapping caused by terminal width. Soft wrap does not insert newline
characters into the composer buffer. Soft wrap boundaries are determined by cell
width measurement.

### Explicit Newline

A newline character inserted into the composer buffer through a configured
keybinding. It is part of submitted text.

### Cursor Declaration

The logical cursor position reported by a focused renderable. The runtime maps it
to a physical terminal cell after wrapping, width calculation, and layout.

### Bracketed Paste

A terminal mode that marks pasted text as paste input. The runtime should use it
to avoid treating pasted newlines or escape sequences as ordinary key strokes
when the terminal supports it.

### Paste Event

A normalized input event containing pasted text. Paste events are routed to the
focused input renderable as one editing operation. Pasted newlines are inserted
into the composer buffer and must not submit the prompt.

### Paste Marker

A compact composer representation for large pasted content, such as
`[paste #1 +123 lines]`. A paste marker may stand in for the full pasted payload
while preserving the payload for editing, submission, and undo. Cursor movement
and deletion treat a paste marker as an atomic grapheme-like unit.

### Paste Safety

The requirement that pasted terminal control sequences are never executed by the
terminal. The runtime or composer must insert them as inert text, escape them for
display, filter them, or reject them with a concise error according to product
policy.

### Undo Stack

The composer history of editing operations used to undo and redo text changes.
One paste event should normally be one undo step.

### Kill Ring

A composer editing buffer for cut text, used by delete-to-line-end,
delete-word, yank, and related editor actions. It is an editor feature and not a
transcript record.

### Abort

A control action that requests cancellation or interruption of the active run. It
is not prompt text. Esc and Ctrl-C may produce abort intents depending on focus
and active surface state. Abort intents are produced by configured keybindings or
product defaults; emergency signal paths may also request abort through runtime
lifecycle handling. When a surface is active, surface handling has priority over
run abort handling.

## Terminal Input Protocol Model

### Keyboard Protocol

A terminal protocol that reports key presses with enough structure to distinguish
plain keys, modifier keys, release events, alternate layouts, and ambiguous
Escape-prefixed sequences. Keyboard protocols include Kitty keyboard protocol
and xterm modifyOtherKeys.

### Keyboard Protocol Negotiation

The startup state machine that queries keyboard protocol support, enables the
best supported mode, records which mode is active, and disables only the active
mode during terminal restoration.

### Kitty Keyboard Protocol

A modern keyboard protocol that can report CSI-u key sequences, modifier state,
key press/repeat/release event type, and base layout keys. It is preferred when
the terminal responds to the Kitty keyboard protocol query.

### modifyOtherKeys

An xterm keyboard mode used as a fallback when Kitty keyboard protocol is not
available. It reports modified keys with CSI sequences such as
`\x1b[27;<modifier>;<codepoint>~`.

### Escape Sequence

A terminal control or input sequence that begins with the Escape byte `ESC`
(`\x1b`). Escape sequences may represent keys, focus events, mouse events,
terminal responses, hyperlinks, images, or other terminal control operations.

### CSI Sequence

A Control Sequence Introducer sequence, normally beginning with `ESC [`.
Keyboard arrows, modified arrows, many terminal queries, SGR styling, and some
mouse events are represented as CSI sequences.

### OSC Sequence

An Operating System Command sequence, normally beginning with `ESC ]` and ending
with BEL or ST. OSC sequences are used for terminal title changes, OSC 8
hyperlinks, clipboard integration in some terminals, and other host-terminal
features.

### DCS Sequence

A Device Control String sequence, normally beginning with `ESC P` and ending
with ST. DCS responses are terminal control responses and must be buffered until
complete before routing or discarding.

### APC Sequence

An Application Program Command sequence, normally beginning with `ESC _` and
ending with ST. Kitty graphics protocol responses are examples of APC-style
terminal traffic.

### Escape Disambiguation

The process of deciding whether a received `ESC` byte is a standalone Escape key
or the prefix of a longer escape sequence. Disambiguation must be performed by
the input assembler with a short idle deadline, not by adding arbitrary delays to
all input reads.

### Input Assembler

The input-layer component that receives raw stdin chunks, buffers incomplete
terminal sequences, and emits normalized input events only when complete
sequences are available.

### Pending Sequence

An input sequence prefix that has been received but is not complete yet, such as
a lone `ESC`, partial CSI sequence, partial OSC sequence, or partial bracketed
paste marker.

### Idle Flush

The controlled flush of a pending input sequence after no additional input
arrives before the configured idle deadline. Idle flush is primarily used to
emit a real standalone Escape key without corrupting split escape sequences.

### Input Drain

The exit-time process of consuming residual terminal input after disabling
temporary keyboard modes. Input drain prevents delayed key release events or
terminal responses from being interpreted by the parent shell.

## Coding Integration Terms

### Product Adapter

The layer that translates product-specific state and events into generic TUI
records, UI parts, surfaces, status snapshots, and intents.

For coding, this layer is `loushang.coding.ui`. The generic `loushang.tui` core
must not import coding session, model, tool, diagnostics, or provider modules.

### Run

A product-level unit of work, such as an active agent turn. The TUI core knows
only the generic running/idle state exposed by the product adapter. A run is
considered active while the product adapter reports the running state.

### Thinking Level

A product or model setting for reasoning effort, such as off, minimal, low,
medium, high, or xhigh. It may appear in the status snapshot and may affect theme
selection, but it is separate from thinking block content.

### Follow-Up

Regular user input submitted while a run is active and queued for the next turn.
It is shown as pending follow-up instead of being delivered to the active run.

### Steer

User input submitted while a run is active and delivered to the active run when
the coding runtime supports live steering. Steering must be visibly distinct
from queued follow-up.

### Pending Queue

A transient bottom-frame display of submitted inputs that have not yet been
processed. It may contain follow-up items, steering items, or product-specific
pending actions. In the default coding layout, the pending queue is displayed
above the working line and grows upward as items are added.

### Slash Command

Composer input that requests a command selection or command execution path. The
TUI owns suggestion display and navigation; the product adapter owns command
semantics.

### Status Snapshot

Product-provided status data rendered into the status area. A snapshot may
include model, cwd, branch, session id, context usage, quotas, token usage, or
run state. The status renderer decides which fields fit.

### Concise Error

A user-facing error block that summarizes the problem without dumping a Python
traceback. Verbose diagnostics may expose tracebacks only when explicitly
enabled.

## Text Measurement Terms

### Cell Width

The number of terminal columns occupied by displayed text. It differs from byte
length and Python string length. Correct cell width is required for wrapping,
truncation, diffing, and cursor placement.

### Grapheme Cluster

A user-perceived character that may be made from multiple Unicode code points,
such as an emoji sequence or a base character plus combining marks.

### ANSI SGR

ANSI Select Graphic Rendition escape sequences used for styling such as color,
bold, italic, underline, or reset. SGR sequences have zero cell width.

### OSC 8 Hyperlink

An ANSI escape sequence for terminal hyperlinks. Hyperlink control sequences have
zero cell width and must not corrupt wrapping or cursor mapping.

## Style And Theme Terms

### Theme

A structured set of style tokens used by renderables, UI parts, and renderers.
Themes may control colors, emphasis, markdown styles, syntax highlighting, and
status field styles, but they must not grant direct terminal writer access. The
theme describes desired styles; the runtime or style resolver adapts those
styles to the terminal's capabilities.

## Extension Boundary Terms

### Extension

External or product-supplied code that adds commands, surfaces, renderers, or
status fields through public APIs. Extensions must use TUI interfaces and must
not directly write terminal output. See Public TUI API.

### Public TUI API

The stable API exposed by `loushang.tui` to product adapters and extensions.
Internal runtime modules may change faster than the public API.

### Capability Degradation

Fallback behavior when a terminal or environment lacks an optional feature. For
example, a hyperlink becomes plain text, truecolor falls back to basic colors,
and image output falls back to text or file references. Capability degradation is
handled by the runtime and style/rendering adapters, not by direct renderable
terminal writes.

## Avoided Terms

### Component

A non-canonical term for loushang native terminal core documents. Use
`Renderable` for the framework protocol and `UI Part` for concrete visible UI
building blocks. Use "component" only when quoting or mapping an external
reference system that uses that word.
