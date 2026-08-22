# KD-003: Abort, Steer, And Follow-Up Sequence

## Purpose

Define the time-sensitive interaction model while a product run is active.

## Design

The composer stays usable during an active run. Harnesstui's
`ConversationInputRouter` is the sole shared conversation-input semantic owner:
it interprets idle and running Enter, running-submit alternatives, queue
restore, and conversation cancellation from explicit conversation state. It
reuses generic TUI editor targets and key helpers, but does not delegate the
whole event to generic `InputRouter` as a second conversation state machine.

Generic `loushang.tui.InputRouter` emits only neutral `submit` and
`prompt_cancel` signals. It does not know whether a run is active and does not
construct follow-up, steer, queue-edit, or conversation-abort intents.
Conversation text is classified above that generic layer:

- follow-up: queued for a later turn
- steer: delivered to the active run when the product supports live steering
- abort: control action that cancels or interrupts the active run
- surface action: handled by the active surface before active-run controls

Capability and downgrade policy also stays above generic TUI. Coding currently
uses `ConversationInputRouter`'s default `running_submit_mode="steer"`; it has
not yet injected an explicit steering-capability policy. Coding continues to
own slash-command classification, final Product actions, and Product copy.

Pending follow-up and steering items are rendered in the pending queue area. The
queue is transient bottom-frame UI and grows upward. Queued text remains visible
until the product adapter reports it has been delivered, rejected, restored to
the composer, or cancelled.

## Priority

`ConversationInputRouter` preserves surface, focused-editor, completion, and
pending-steer priorities before conversation cancellation. If a surface is
active, Esc is first offered to that surface. Only if no higher-priority owner
consumes it may the HarnessTUI adapter request abort for an active run. Generic
TUI's independent jump-mode cancellation never decides whether work is aborted.

## Test Obligations

- follow-up while running clears the composer and displays queued text
- steer while running displays separately from follow-up
- unavailable steering is rejected or downgraded visibly
- edit-queue restores pending text into the composer
- abort removes running chrome, commits interruption state, and restores focus
- generic `InputRouter` produces no follow-up, steer, queue-edit, or
  conversation-abort result
- Coding conversation playback preserves its effective shortcuts without
  depending on generic `InputRouter`
