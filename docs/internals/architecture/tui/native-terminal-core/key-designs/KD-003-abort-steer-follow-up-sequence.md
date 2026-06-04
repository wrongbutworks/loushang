# KD-003: Abort, Steer, And Follow-Up Sequence

## Purpose

Define the time-sensitive interaction model while a product run is active.

## Design

The composer stays usable during an active run. Submitted text is classified by
the product adapter:

- follow-up: queued for a later turn
- steer: delivered to the active run when the product supports live steering
- abort: control action that cancels or interrupts the active run
- surface action: handled by the active surface before active-run controls

Pending follow-up and steering items are rendered in the pending queue area. The
queue is transient bottom-frame UI and grows upward. Queued text remains visible
until the product adapter reports it has been delivered, rejected, restored to
the composer, or cancelled.

## Priority

If a surface is active, Esc is first offered to that surface. Only if the surface
does not consume Esc may it become an abort intent for an active run.

## Test Obligations

- follow-up while running clears the composer and displays queued text
- steer while running displays separately from follow-up
- unavailable steering is rejected or downgraded visibly
- edit-queue restores pending text into the composer
- abort removes running chrome, commits interruption state, and restores focus
