# Diagnostics Core Migration Plan

## Goal

Move neutral diagnostic records, queries, summaries, startup-check contracts,
and bounded in-memory diagnostic mechanics into Harness while preserving Coding
imports, emitted records, serialization, and product behavior.

## Tasks

- [ ] Define Diagnostics Core ownership and Coding adapter boundaries.
- [ ] Implement `loushang.harness.diagnostics.types`.
- [ ] Preserve record fields, defaults, vocabulary, and callable contracts.
- [ ] Implement `loushang.harness.diagnostics.service`.
- [ ] Preserve retention, fingerprint, dedupe, query, and summary behavior.
- [ ] Reduce Coding diagnostic type and service modules to compatibility exports.
- [ ] Redirect Coding internal consumers to focused Harness owners.
- [ ] Keep serialization and problem-bridge policy in Coding.
- [ ] Add Harness records, service, query, and normalization tests.
- [ ] Add Coding compatibility, serialization, and bridge identity tests.
- [ ] Add architecture owner and documentation tests.
- [ ] Update Harness and Coding architecture records.
- [ ] Run focused Harness, Coding diagnostics/session/tool, and architecture tests.
- [ ] Run changed-file Ruff, diff checks, and the full non-live test suite.

## Non-Goals

- Moving concrete checks, emission timing, or remediation policy.
- Moving observability problem mapping or product serialization.
- Moving session, CLI, RPC, export, or TUI diagnostic presentation.
- Adding diagnostic symbols to Harness package-level exports.
