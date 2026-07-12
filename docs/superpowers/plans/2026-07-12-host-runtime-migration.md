# Host Runtime Core Ownership Migration Plan

## Goal

Move product-neutral host lifecycle, queue-ledger, and ordered event mechanisms
from Coding into `loushang.harness.host` while preserving Agent ownership of the
inner run loop and Coding ownership of product behavior.

## Tasks

- [ ] Define Host Runtime and Product adapter ownership boundaries.
- [ ] Implement neutral host records and compatibility run state.
- [ ] Implement the generic Host input queue ledger.
- [ ] Implement the generic ordered event bus.
- [ ] Implement driver-delegating Host Runtime lifecycle coordination.
- [ ] Add product-neutral contract probes for lifecycle, queue, and events.
- [ ] Adapt Coding queue snapshots and ledger mechanics to Harness.
- [ ] Adapt Coding session event dispatch to Harness.
- [ ] Adapt AgentSession prompt/continue/abort/idle/dispose lifecycle to Harness.
- [ ] Preserve Coding input, event, session, retry, compaction, and UI policy.
- [ ] Add compatibility and architecture ownership tests.
- [ ] Update Harness README, migration inventory, and capability boundaries.
- [ ] Run focused Harness and Coding lifecycle tests.
- [ ] Run changed-file Ruff, diff checks, and the full non-live suite.

## Non-Goals

- Moving or reimplementing `loushang.agent.Agent` or the agent loop.
- Moving Coding session storage, tree operations, controllers, or event schema.
- Moving retry classification, compaction, prompts, resources, extensions, or UI.
- Adding Host Runtime symbols to top-level `loushang.harness.__all__`.
