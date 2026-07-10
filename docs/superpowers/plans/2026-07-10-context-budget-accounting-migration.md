# Context Budget And Accounting Migration Plan

## Goal

Move deterministic context compaction-budget accounting and the neutral usage
estimate record into Harness while preserving Coding public imports, settings
compatibility, message estimation, and compaction behavior.

## Tasks

- [ ] Define budget/accounting ownership and Coding adapter boundaries.
- [ ] Implement `loushang.harness.context.budget`.
- [ ] Preserve threshold calculation, normalization, and settings precedence.
- [ ] Implement `loushang.harness.context.usage`.
- [ ] Reduce Coding policy and type modules to compatibility exports.
- [ ] Redirect Coding internal consumers to the Harness owners.
- [ ] Add Harness budget and usage-record tests.
- [ ] Add Coding compatibility and estimator identity tests.
- [ ] Add architecture owner and documentation tests.
- [ ] Update Harness and Coding architecture records.
- [ ] Run focused Harness, Coding compaction/session, and architecture tests.
- [ ] Run changed-file Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving Coding settings, defaults, or compaction enablement policy.
- Moving message token estimation or AI usage interpretation.
- Moving context usage snapshots, decisions, plans, or branch semantics.
- Moving summarization, salience, transcript rebuild, or packing policy.
- Adding context symbols to top-level `loushang.harness` exports.
