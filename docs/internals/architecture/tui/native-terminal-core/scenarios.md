# Native Terminal Core Scenarios

## SC-START-001: Startup In Existing Shell Scrollback

Given the user has existing shell output above the cursor
When the TUI starts
Then it does not clear the previous shell output by default
And the initial composer/status frame appears below existing output.

## SC-START-002: Startup From Non-Empty Cursor Line

Given the process starts while the hardware cursor may not be on a clean new line
When the TUI performs the first render
Then the runtime must not overwrite the current shell line
And it may emit a newline before the first managed row when needed.

## SC-CI-001: Submit Prompt And Stream Assistant

Given the TUI is idle
When the user submits a prompt
Then the prompt is committed to transcript
And a transient working line appears
And assistant draft updates do not duplicate transcript entries
And final assistant content is committed as one stable assistant block
And the composer and status areas remain anchored at the bottom.

## SC-CI-001A: Submit Draft After Previous Run Completes

Given a run is active
And the user types follow-up text in the composer without submitting it
And the run completes, leaving that text as a live composer draft
When the user continues editing the draft and submits it as the next prompt
Then the runtime first renders the composer-cleared frame
And only then does the product adapter append the submitted prompt to transcript
And the old live composer draft does not appear as a separate transcript or
scrollback line.

## SC-CI-002: Complete Turn

Given an agent turn is running
When the turn completes successfully
Then the transient working line disappears
And the final assistant block is visible in transcript
And a worked divider is committed
And the composer returns to idle input.

## SC-CI-003: Interrupt Running Turn

Given an agent turn is running
When the user presses Esc or Ctrl-C
Then the active run receives an abort request
And transient running UI is removed
And an interruption block is committed
And focus returns to the composer
And the session remains usable.

## SC-CI-004: Queue Follow-Up While Running

Given an agent turn is running
When the user submits regular text
Then the composer clears
And the text appears in the follow-up queue area
And the active turn continues rendering
And the queued input is submitted after the current run completes
And the queue can be restored to the composer for editing through the configured
edit-queue action.

## SC-CI-005: Steer While Running

Given an agent turn is running and steering is supported
When the user submits steering input through the configured steering action
Then the input is delivered to the active run
And the UI shows it as pending steering rather than next-turn follow-up.

## SC-CI-006: Steering Unavailable

Given an agent turn is running and steering is unavailable
When the user attempts steering input
Then the UI must either reject the input with a concise status message or queue
it explicitly as follow-up
And it must not imply live steering succeeded.

## SC-LAYOUT-001: Long Composer Line

Given the composer contains a long line
When it exceeds terminal width
Then the line soft-wraps
And the beginning of the line remains reachable
And the cursor maps to the correct visual cell.

## SC-LAYOUT-002: Explicit Newline In Composer

Given the composer is focused
When the user inserts an explicit newline
Then the composer grows by one logical line
And the status bar remains fixed at the bottom.

## SC-LAYOUT-003: Multi-Line Paste

Given the composer is focused
When the user pastes text containing newlines
Then the pasted newlines are inserted into the composer buffer
And the prompt is not submitted until the user explicitly submits it
And the whole paste can be undone as one editing operation.

## SC-LAYOUT-004: Large Paste

Given the composer is focused
When the user pastes large content
Then the composer may display a paste marker
And the full pasted content is preserved for submission
And cursor movement and deletion treat the marker atomically.

## SC-LAYOUT-005: Paste With Terminal Control Sequences

Given the composer is focused
When the user pastes text containing terminal control sequences
Then those sequences are not executed by the terminal
And they are inserted as inert text, escaped for display, filtered, or rejected
with a concise error according to product policy.

## SC-LAYOUT-006: IME Candidate Position

Given the composer is focused and contains wide characters, combining marks, or
wrapped text
When the runtime positions the hardware cursor
Then the cursor maps to the focused logical cursor declaration
And IME candidate windows appear near the visual insertion point when the
terminal supports it.

## SC-SO-001: Slash Command Surface

Given the composer contains slash command input
When command suggestions are available
Then an autocomplete or command surface opens above the composer
And selecting a command emits a product intent
And closing the surface restores composer focus
And Enter executes the highlighted slash command
And Tab applies the highlighted command without submitting.

## SC-SO-002: Settings Surface

Given a settings command is selected
When the settings surface opens
Then it captures focus
And user changes are returned as intents or callbacks
And Esc closes the surface without submitting prompt text.

## SC-SO-003: Approval Surface

Given a protected product action needs user approval
When the product adapter opens an approval surface
Then the surface shows the guarded action, risk context, and choices
And keyboard navigation can select an explicit approval intent
And closing or aborting the surface does not execute the guarded action.

## SC-SO-004: Selection Surface

Given a product or extension needs item selection
When a selection surface opens
Then it supports navigation, optional filtering, visible selection state, and
explicit close reasons
And the product adapter receives selected values as intents, not raw key events
And a focused selection surface suppresses ordinary composer and status rows
while it is active.

## SC-SO-005: Stacked And Constrained Surfaces

Given a surface is already active
When another surface opens above it
Then the top focused surface receives input first
And closing the top surface restores focus to the previous surface or composer
And any surface that exceeds available height scrolls internally or truncates
without displacing the composer and status minimum rows.

## SC-RR-001: Resize During Streaming

Given an assistant response is streaming
When terminal width changes
Then logical content reflows
And transcript order is preserved
And previous blocks are not duplicated in scrollback
And the composer, status area, working line, pending queue, and hardware cursor
remain visually coherent
And the runtime may use resize repaint to stabilize the current UI.

## SC-RR-002: Resize With Existing Shell Scrollback

Given the user starts the TUI below existing shell output
When the terminal is resized
Then the runtime may full recompose and resize repaint the current UI
And the default resize policy clears scrollback
And a history-preserving policy may disable resize clear scrollback.

## SC-RR-003: User Scrolls Up During Streaming

Given assistant output is streaming
When the user scrolls upward in the native terminal scrollback
Then the runtime does not try to own or rewrite arbitrary historical rows
And any managed viewport assumptions affected by the scroll are treated as unsafe
And the runtime re-establishes a safe bottom anchor before the next in-place
managed update
And that re-anchor may use resize/recovery repaint of runtime-managed UI.

## SC-EX-002: External Stdout Write Invalidates Viewport

Given the TUI is running
When output is written to stdout outside the runtime terminal writer
Then the runtime treats the managed viewport mapping as unsafe
And the next render uses repaint instead of stale diff operations.

## SC-RR-004: Clear Scrollback Policy

Given resize clear scrollback is enabled by default
When resize repaint is used
Then the runtime emits clear-scrollback operations and reports them in
diagnostics
And if clear scrollback is disabled by explicit history-preserving policy,
diagnostics record that policy and resize repaint proceeds without clearing
scrollback
And recovery repaint does not clear scrollback unless explicit policy enables it.

## SC-CR-001: Markdown Assistant Content

Given assistant content contains markdown
When it is rendered
Then headings, lists, links, inline code, code blocks, block quotes, and
horizontal rules render with terminal-safe styles
And wrapping and truncation use terminal cell width.

## SC-CR-002: Tool Execution Lifecycle

Given a tool call starts, streams output, completes, fails, or is cancelled
When the product adapter updates the display record
Then the TUI renders one tool execution record with running/completed state,
timing marker, output summary, truncation, and error state as applicable.

## SC-CR-003: Thinking Visibility

Given assistant output contains thinking blocks
When thinking visibility is visible, collapsed, or hidden by policy
Then the TUI renders only the provided thinking content according to that policy
And never invents or exposes hidden reasoning.

## SC-TH-001: Theme Change

Given the product adapter changes theme tokens
When the runtime receives the new theme
Then renderables invalidate cached styled output
And the next render uses the new style without direct terminal writes from UI
parts.

## SC-EX-001: Extension Widget

Given an extension provides a transient widget
When the product adapter inserts it into an extension widget slot
Then the widget is rendered through the runtime-owned region
And it cannot write stdout, move the cursor, or clear lines directly.

## SC-ERR-001: Concise Error

Given a recoverable runtime or provider error occurs
When the error is rendered
Then the transcript shows a concise human-readable error block
And Python traceback output is hidden unless verbose diagnostics are enabled.
