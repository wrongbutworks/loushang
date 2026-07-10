# Context Budget And Accounting Migration Plan

## Goal

Move deterministic context compaction-budget accounting and the neutral usage
estimate record into Harness while preserving Coding public imports, settings
compatibility, message estimation, and compaction behavior.

## Tasks

- [x] Define budget/accounting ownership and Coding adapter boundaries.
- [x] Implement `loushang.harness.context.budget`.
- [x] Preserve threshold calculation, normalization, and settings precedence.
- [x] Implement `loushang.harness.context.usage`.
- [x] Reduce Coding policy and type modules to compatibility exports.
- [x] Redirect Coding internal consumers to the Harness owners.
- [x] Add Harness budget and usage-record tests.
- [x] Add Coding compatibility and estimator identity tests.
- [x] Add architecture owner and documentation tests.
- [x] Update Harness and Coding architecture records.
- [x] Run focused Harness, Coding compaction/session, and architecture tests.
- [x] Run changed-file Ruff, diff checks, and the full non-live test suite.

## Validation Record

- Focused Harness, Coding compaction/session, and architecture suite: 98 passed.
- Full non-live suite: 4331 passed, 9 deselected.
- Changed-file Ruff and `git diff --check`: passed.

## Non-Goals

- Moving Coding settings, defaults, or compaction enablement policy.
- Moving message token estimation or AI usage interpretation.
- Moving context usage snapshots, decisions, plans, or branch semantics.
- Moving summarization, salience, transcript rebuild, or packing policy.
- Adding context symbols to top-level `loushang.harness` exports.
