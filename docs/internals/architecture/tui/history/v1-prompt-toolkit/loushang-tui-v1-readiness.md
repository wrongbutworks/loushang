# Loushang TUI v1 Readiness

## Purpose

This note defines the release contract for `loushang.tui` before it is treated as a stable
terminal UI primitive layer. It complements the component design and public API guide with
checkable readiness criteria.

`loushang.tui` is a generic terminal UI library. Product semantics stay in `loushang.coding.ui`.
The TUI package provides terminal capabilities, reusable controls, inline prompt mechanics,
transcript-safe output, and generic rendering primitives.

## Public API Freeze

The v1 public surface is intentionally narrow and explicit:

- `loushang.tui.__all__` exports stable generic primitives, view models, reusable control
  controllers/renderers, standalone runners, terminal capability helpers, and transcript
  output contracts.
- `loushang.tui.inline.__all__` exports the inline prompt runner, inline action model,
  inline local-control host contract, and inline local-control starters.
- `loushang.tui.render.__all__` exports generic Markdown, code, diff, rule, and block
  rendering primitives.

Adding a public symbol requires updating the facade mapping, `TYPE_CHECKING` re-export,
API guide, import-boundary tests, and this readiness document when the category changes.
Removing or renaming a public symbol after v1 requires a deprecation plan.

## Direct Import Allowlist

Product code should import stable generic primitives from `loushang.tui`.

Direct submodule imports from product layers are limited to:

- `loushang.tui.inline` for inline prompt and inline local-control host entry points.
- `loushang.tui.prompt` for the non-interactive prompt loop.
- `loushang.tui.render` for generic transcript rendering helpers.
- `loushang.tui.text_utils` for terminal width calculations needed by product adapters.

All other `loushang.tui.*` implementation modules are internal to TUI or white-box tests.

## Internal Surfaces

The following are not product-layer contracts:

- `loushang.tui.inline.runtime`, `services`, `layout`, `views`, `tasks`, `abort`,
  `composer`, `composer_policy`, and related helper modules.
- prompt_toolkit `Application`, `Buffer`, `Window`, `Container`, key binding, and style
  objects.
- Rich `Console` internals.
- low-level output helpers such as `emit_in_terminal`, `patched_stdout`, and `write_line`.

prompt_toolkit and Rich stay execution-time implementation details. Importing a facade and
accessing facade exports must not load them unless the called function actually needs the
interactive runner or render engine.

## Runtime Boundary

`_InlinePromptRuntime` is an internal composition root. It owns only:

- constructor inputs;
- `services`, the wired callback/controller graph;
- `application_parts`, the prompt_toolkit application assembly;
- `run()`, the runtime entry point.

The runtime must not re-export flattened passthroughs such as `state`, `buffer`,
`renderers`, `key_bindings`, `app`, or `_schedule_abort()`. White-box tests may inspect
`services` and `application_parts`; product code must only use `loushang.tui.inline`.

## PTY Matrix

The v1 PTY regression matrix must cover:

- idle submit, running submit, running alternate submit, abort, forced abort, dequeue, and
  blank input;
- repeated steer/follow-up/abort sequences with deferred prompts;
- local controls opened while idle and while a run is active;
- local-control submit, cancel, close, and validation errors, including validation misses
  that stay inside the local control and cancel without dispatching session abort;
- resize during prompt entry, running controls, and local-control display;
- recovery after abort before the next prompt is accepted;
- queue clearing after abort and after successful run completion.

Scenarios that mix resize with escape-prefixed keys should wait for each semantic action to
land. Separate burst tests should cover fast mixed input without resize.

## Done Criteria

`loushang.tui` is v1-ready when:

- public facades are lazy and tested in a fresh interpreter;
- product layers import only from the public facade or the direct import allowlist;
- internal inline runtime helpers are hidden behind `services` and `application_parts`;
- generic render helpers remain product-semantics free;
- the PTY matrix passes under repeated local-control, abort, steer, and follow-up mixes;
- the public API guide contains examples for top-level controls, inline controls, render
  blocks, and transcript output.

## Freeze Checklist

This checklist is historical. The old release gate was removed because it
referenced prompt-toolkit/Rich-era tests that were never part of the current
native terminal core. Current verification should follow the live native
terminal core testing strategy and screen playback regression docs.

For historical context, this track expected any public export change to update
the facade, type-checking re-export, public API guide, import-boundary tests,
and readiness contract in the same change.
