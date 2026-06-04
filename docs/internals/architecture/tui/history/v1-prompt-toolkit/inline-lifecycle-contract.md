# Loushang TUI Inline Lifecycle Contract

## Purpose

This document defines the lifecycle contract for `loushang.tui.inline`.

The inline runtime owns generic terminal interaction state only. It does not know about
sessions, models, tools, slash commands, agents, or follow-up semantics. Product layers map
runtime actions into product behavior.

## Phases

`InlinePromptState` plus local interaction state is projected into one lifecycle phase:

| Phase | Meaning |
| --- | --- |
| `idle` | No prompt task is running and no local control is active. |
| `running` | A prompt task is active. |
| `local_interaction` | A generic local control, such as a command palette or confirm prompt, owns input. |
| `aborting` | Abort has been requested and the runtime is settling or cancelling active work. |

Priority is fixed:

```text
aborting > local_interaction > running > idle
```

This priority is intentional. Abort settling must not be hidden by a local control, and local
controls must receive navigation/submit keys before the main composer when active.

The helper `inline_lifecycle_phase()` exists to make this projection explicit and testable.
It is a contract helper, not an invitation for product layers to branch on internal runtime
state.

## Keyboard Contract

The keymap converts terminal keys into generic `InlineAction` values:

| Key | Idle | Running |
| --- | --- | --- |
| `Enter` | `SUBMIT` | `RUNNING_SUBMIT` |
| `Alt+Enter` | `NEWLINE` | `RUNNING_ALT_SUBMIT` |
| `Ctrl+J` | `NEWLINE` | `NEWLINE` |
| `Esc` | `ABORT` | `ABORT` |
| `Ctrl-C` | `ABORT` | `ABORT` |
| `Ctrl-D` | `EXIT` only when idle and composer is empty | `NOOP` |
| `Alt-Up` | `DEQUEUE` | `DEQUEUE` |
| `Up` / `Down` | local-control navigation only | local-control navigation only |

`submit_on_enter=False` changes `Enter` to `NEWLINE` in both idle and running phases.
It does not change abort, dequeue, alternate submit, or Ctrl-D behavior.

## Submission Contract

The composer policy normalizes whitespace before delivery. Whitespace-only input is ignored
and clears the composer.

When idle:

- `SUBMIT` starts a prompt task with normalized text.
- `Alt+Enter` inserts a newline.
- `Ctrl+D` exits only when the raw composer is empty.

When running:

- `RUNNING_SUBMIT` schedules the main running-submit handler.
- `RUNNING_ALT_SUBMIT` schedules the alternate-submit handler.
- Product layers may map these to steer/follow-up semantics, but `loushang.tui` does not.
- If input while running is disabled, submission reports status instead of scheduling work.

When aborting:

- submit-like actions are deferred until abort settles.
- empty deferred submissions are ignored.
- non-empty deferred submissions are started after abort cleanup completes.

## Abort Contract

Abort must be idempotent:

- If nothing is running, abort reports `Nothing running.`
- If a prompt task exists but the visible state is already idle, abort force-cancels that task
  and reports `Interrupted.`
- If running, abort marks the state as aborting and starts abort settlement.
- If abort is already in progress, a repeated abort reports `Abort in progress.`
- A force-abort action while aborting cancels the active prompt and abort tasks.

Abort settlement:

- calls the optional abort handler.
- waits briefly for prompt settlement.
- cancels prompt work if it does not settle.
- clears abort state and reports `Interrupted.`
- starts exactly one deferred prompt if one was queued while aborting.

## Local Interaction Contract

Local interactions are generic TUI controls hosted inside the inline runtime.

When a local interaction is active:

- `ABORT` cancels the local interaction before aborting the main runtime.
- local-control actions such as move up/down are offered to the local control.
- main composer actions such as submit, running submit, alternate submit, and dequeue are
  blocked and report `Local interaction active.`
- the composer text is preserved or cleared according to the local interaction adapter policy.

## Test Map

This contract is covered by focused tests:

- `tests/tui/test_inline_lifecycle_contract.py`
- `tests/tui/test_inline_lifecycle_sequences.py`
- `tests/tui/test_keymap.py`
- `tests/tui/test_inline_runtime_actions.py`
- `tests/tui/test_inline_submission.py`
- `tests/tui/test_inline_abort.py`
- `tests/tui/test_inline_local_interaction.py`

Future inline runtime refactors should update implementation internals without weakening
these tests or changing this contract unless the contract itself is intentionally revised.
