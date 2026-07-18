# Host Runtime Core Ownership Migration Plan

## Goal

Move product-neutral host lifecycle, queue-ledger, and ordered event mechanisms
from Coding into `loushang.harness.host` while preserving Agent ownership of the
inner run loop and Coding ownership of product behavior.

## Tasks

- [x] Define Host Runtime and Product adapter ownership boundaries.
- [x] Implement neutral host records and compatibility run state.
- [x] Implement the generic Host input queue ledger.
- [x] Implement the generic ordered event bus.
- [x] Implement driver-delegating Host Runtime lifecycle coordination.
- [x] Add product-neutral contract probes for lifecycle, queue, and events.
- [x] Adapt Coding queue snapshots and ledger mechanics to Harness.
- [x] Adapt Coding session event dispatch to Harness.
- [x] Adapt AgentSession prompt/continue/abort/idle/dispose lifecycle to Harness.
- [x] Preserve Coding input, event, session, retry, compaction, and UI policy.
- [x] Add compatibility and architecture ownership tests.
- [x] Update Harness README, migration inventory, and capability boundaries.
- [x] Run focused Harness and Coding lifecycle tests.
- [x] Run changed-file Ruff, diff checks, and the full non-live suite.

## Validation Record

- Cross-layer Harness host, Coding session/runtime, extension, bootstrap, SDK,
  mode, workflow, compaction, and architecture suite: 564 passed.
- Full non-live suite: 4373 passed, 9 deselected.
- New Harness host and touched Coding/test default Ruff checks: passed.
- `git diff --check`: passed.
- A live Moonshot verification was excluded from the final suite after the
  configured credential returned HTTP 401; no live-provider result is claimed.

## Non-Goals

- Moving or reimplementing `loushang.agent.Agent` or the agent loop.
- Moving Coding session storage, tree operations, controllers, or event schema.
- Moving retry classification, compaction, prompts, resources, extensions, or UI.
- Adding Host Runtime symbols to top-level `loushang.harness.__all__`.
