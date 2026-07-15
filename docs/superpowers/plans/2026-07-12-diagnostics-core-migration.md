# Diagnostics Core Migration Plan

## Goal

Move neutral diagnostic records, queries, summaries, startup-check contracts,
and bounded in-memory diagnostic mechanics into Harness while preserving Coding
imports, emitted records, serialization, and product behavior.

## Tasks

- [x] Define Diagnostics Core ownership and Coding adapter boundaries.
- [x] Implement `loushang.harness.diagnostics.types`.
- [x] Preserve record fields, defaults, vocabulary, and callable contracts.
- [x] Implement `loushang.harness.diagnostics.service`.
- [x] Preserve retention, fingerprint, dedupe, query, and summary behavior.
- [x] Reduce Coding diagnostic type and service modules to compatibility exports.
- [x] Redirect Coding internal consumers to focused Harness owners.
- [x] Keep serialization and problem-bridge policy in Coding.
- [x] Add Harness records, service, query, and normalization tests.
- [x] Add Coding compatibility, serialization, and bridge identity tests.
- [x] Add architecture owner and documentation tests.
- [x] Update Harness and Coding architecture records.
- [x] Run focused Harness, Coding diagnostics/session/tool, and architecture tests.
- [x] Run changed-file Ruff, diff checks, and the full non-live test suite.

## Validation Record

- Focused Harness, Coding diagnostics/session/tool, and architecture suite: 450 passed.
- Full non-live suite: 4347 passed, 9 deselected.
- Harness diagnostics, Coding compatibility modules, new tests, architecture
  tests, and all touched-file import/syntax/undefined Ruff checks: passed.
- `git diff --check`: passed.
- Default Ruff reports four pre-existing findings on unchanged lines in files
  touched only for imports: CLI `SIM102`, package resource roots `RUF100`,
  runtime `SIM105`, and tool context `UP035`.

## Non-Goals

- Moving concrete checks, emission timing, or remediation policy.
- Moving observability problem mapping or product serialization.
- Moving session, CLI, RPC, export, or TUI diagnostic presentation.
- Adding diagnostic symbols to Harness package-level exports.
