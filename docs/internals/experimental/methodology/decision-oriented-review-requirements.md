# Decision-Oriented Review Requirements

## Status

Experimental requirements and expectations.

This document captures requirements for reviewing long specs, architecture
documents, and design decisions with humans and agents while preserving context
isolation and durable review records. It is not a runtime contract.

## Problem

Long design specs contain many decisions mixed with background, rationale,
component details, test strategy, implementation phases, and open questions.
Reviewing the whole document in one conversation creates several problems:

- unrelated decisions contaminate each other's context
- related decisions may be reviewed separately and become inconsistent
- exploratory side research can flood the main working thread
- human approval becomes ambiguous because it is not tied to a decision ID,
  spec version, or patch
- review state is hard to resume after context compaction or thread switches
- final synthesis is often skipped after local decision edits

The desired workflow is not just long-document review. It is lifecycle
management for design decisions.

## Proposed Review Objects

| Object | Purpose |
| --- | --- |
| Spec Document | Full narrative source of truth. |
| Decision Index | Short index of reviewable decisions extracted from the spec. |
| Decision Record | One durable record per decision, including rationale, alternatives, dependencies, and review status. |
| Decision Graph | Dependencies and impact relationships between decisions. |
| Review Ledger | Appendable state log of review outcomes, comments, actions, and resolutions. |
| Review Packet | Minimal context package for one human or agent review session. |
| Review Delta | Structured result returned from a side review to the main thread. |
| Synthesis Review | Final pass that checks the whole document after local decisions have changed. |

## Requirement Index

| ID | Title | Summary | Status |
| --- | --- | --- | --- |
| DOR-REQ-001 | Decision index extraction | A long spec must be split into reviewable decision IDs. | Draft |
| DOR-REQ-002 | Context-isolated review packets | Independent decisions should be reviewed with minimal scoped context. | Draft |
| DOR-REQ-003 | Decision graph and bundles | Related decisions should be reviewed together through explicit dependency bundles. | Draft |
| DOR-REQ-004 | Total-part-total review flow | Review should start broad, proceed by groups, and end with synthesis. | Draft |
| DOR-REQ-005 | Durable review ledger | Review status must be recorded outside chat history. | Draft |
| DOR-REQ-006 | Decision record schema | Each decision needs a stable record with status, rationale, alternatives, dependencies, and resolution. | Draft |
| DOR-REQ-007 | Large spec vs decision documents | The method must support both a single large spec and split decision files. | Draft |
| DOR-REQ-008 | Side conversation recovery | Side reviews must return structured deltas instead of polluting the main thread. | Draft |
| DOR-REQ-009 | Human decision-group review | Human review should support small batches of decisions, typically one to three at a time. | Draft |
| DOR-REQ-010 | Role-based agent review | Agents should review the same spec by risk role, not by reading the whole session history. | Draft |
| DOR-REQ-011 | Review command model | Commands or interaction modes should make split, next, bundle, ledger, and synthesis review operations explicit. | Draft |
| DOR-REQ-012 | Methodology integration | The workflow should map to method phases, tasks, roles, and workproducts. | Draft |
| DOR-REQ-013 | Version-aware approval | Every approval or requested change should reference a spec version or commit. | Draft |
| DOR-REQ-014 | Progressive expectation capture | New review needs and expectations should be appended as requirements, not buried in conversation. | Draft |
| DOR-REQ-015 | Side-review command boundaries | Side-review commands must account for commands that only work from the main thread. | Draft |

## Requirement Records

### DOR-REQ-001: Decision Index Extraction

Long specs should expose a `Decision Index`.

The index should contain:

- stable decision ID
- short title
- one-sentence decision statement
- relevant spec section
- owner or review role if known
- status

Example:

```text
DEC-003 SearchableList is an extracted widget abstraction.
DEC-004 TabGroup returns TabChange for value changes.
DEC-005 Nested tab colors use level-aware tokens.
```

The index is the human review entry point. Reviewers should not need to scan the
entire spec before deciding which decisions need attention.

### DOR-REQ-002: Context-Isolated Review Packets

Independent decisions should be reviewed in isolated packets so they do not
inherit unrelated conversation history.

A review packet should include:

- decision ID and title
- decision statement
- relevant spec excerpt
- known constraints
- dependency list
- current ledger status
- explicit review question

It should not include the full parent conversation unless the decision depends
on it. This keeps side research and long discussions from disrupting the main
work lane.

### DOR-REQ-003: Decision Graph And Bundles

Some decisions are coupled and must be reviewed together. The method should
maintain a decision graph:

```text
DEC-004 TabGroup return contract
  impacts DEC-009 Playback assertions
  impacts DEC-010 Surface integration

DEC-003 SearchableList extraction
  depends_on existing SelectionSurface behavior
  impacts DEC-008 Long list playback
```

The graph enables bundle review:

```text
Bundle: Focus and event contract
- DEC-004 Return contract
- DEC-005 Focus transitions
- DEC-009 Playback assertions
```

Independent decisions can stay isolated. Related decisions should move together.

### DOR-REQ-004: Total-Part-Total Review Flow

Long spec review should use a total-part-total flow:

1. Broad review: confirm the problem, scope, goals, and non-goals.
2. Grouped decision review: review one decision or one small bundle at a time.
3. Synthesis review: check consistency after local edits.

The synthesis step is required because local decision edits can create global
contradictions. Passing all individual decisions is not enough to approve the
whole spec.

### DOR-REQ-005: Durable Review Ledger

Review conclusions must be stored in a durable ledger, not only in chat.

Minimum ledger fields:

- decision ID
- decision title
- status
- reviewer
- spec version
- review notes
- action required
- resolution
- resolution commit or patch reference when available

Statuses should include:

- `pending`
- `approved`
- `changes_requested`
- `deferred`
- `superseded`
- `reopened`
- `needs_recheck`

The ledger is the recovery point after context compaction, side conversations,
or session switches.

### DOR-REQ-006: Decision Record Schema

Each significant decision should have a record. The record can be embedded in a
large spec or live in a separate decision file.

Suggested schema:

```yaml
id: DEC-003
title: SearchableList as extracted widget
status: approved
spec_version: f9d672d
decision: >
  SearchableList extracts existing searchable-list behavior into a reusable
  page-content widget.
rationale:
  - Avoid duplicating SelectionSurface, SearchableList, and CommandPaletteView behavior.
  - Make long-list behavior embeddable in tab pages.
alternatives:
  - Reuse SelectionSurface directly.
  - Keep list logic example-local.
dependencies:
  - DEC-008
impacts:
  - implementation phase 3
  - playback tests
review_notes:
  - human: mention existing surfaces explicitly
resolution:
  - patched in commit f9d672d
```

### DOR-REQ-007: Large Spec Vs Decision Documents

The workflow must support two storage styles.

Single spec style:

```text
spec.md
review-ledger.md
```

This is best for small and medium specs. The spec remains readable as one
document, while the index and ledger provide review structure.

Split decision style:

```text
topic/
  overview.md
  decisions/
    DEC-001-tabs-primitive.md
    DEC-002-content-switcher.md
    DEC-003-searchable-list.md
  review-ledger.md
```

This is better for high-risk or long-running architecture work. It provides
better context isolation but requires stronger synthesis.

The method should allow starting with a single spec and later splitting into
decision files if review grows too large.

### DOR-REQ-008: Side Conversation Recovery

Side conversations are useful for deep research, disagreement resolution, and
exploring one decision without distracting the main thread.

However, a side conversation should not become the permanent source of truth.
It must return a structured review delta:

```yaml
decision: DEC-003
status: changes_requested
summary: Existing searchable-list behavior already exists and should be cited.
patch_needed: true
ledger_update:
  note: Mention SelectionSurface, SearchableList, and CommandPaletteView.
```

The main thread should ingest the delta, update the ledger, and patch the spec
if needed.

### DOR-REQ-009: Human Decision-Group Review

Human review should support small decision groups.

Default group size:

- one decision for complex or controversial topics
- two or three decisions for simple or related topics

Each group should show:

- decision statement
- rationale
- alternatives considered
- dependency summary
- expected implementation impact
- direct review prompt

Human responses should map to durable states:

```text
DEC-004 approve
DEC-005 changes requested: clarify focus return path
DEC-006 defer until implementation plan
```

### DOR-REQ-010: Role-Based Agent Review

Agent review should be role-based and parallel when possible.

Recommended review roles:

| Role | Focus |
| --- | --- |
| Architecture reviewer | Boundaries, abstraction, duplication, conceptual fit. |
| API reviewer | Public contract, naming, compatibility, migration risk. |
| Testing reviewer | Playback, regression coverage, observability, acceptance criteria. |
| Implementation reviewer | Plan feasibility, task slicing, file ownership, risk. |

Each agent should receive a scoped review packet, not the full conversation
history. The conductor or main thread merges their review deltas into the
ledger.

### DOR-REQ-011: Review Command Model

The workflow should support explicit review commands or interaction modes.

Candidate commands:

```text
/review split
/review next 3
/review decision DEC-003
/review bundle focus-model
/review ledger
/review synthesize
/btw DEC-003
```

`/btw` should open or mark a side review. It must still return a review delta
and update the ledger. Side conversations should not silently change the source
of truth.

Current Codex observation:

- `/btw` is unavailable inside an existing side conversation.
- To open another side conversation, the user must return to the main thread
  first.
- This means review commands need session-location awareness. A side review
  cannot assume it can recursively spawn another `/btw` branch from inside
  itself.

### DOR-REQ-012: Methodology Integration

Decision-oriented review should map to method objects:

| Method object | Review workflow mapping |
| --- | --- |
| Phase | Design review, grouped review, synthesis review. |
| Activity | Extract decisions, assign reviewers, patch spec, reconcile ledger. |
| Task | Review one decision, review one bundle, update one decision record. |
| Role | Human reviewer, architecture reviewer, API reviewer, testing reviewer, implementation reviewer, conductor. |
| Workproduct | Spec, decision index, decision records, decision graph, review ledger, review deltas, synthesis report. |

This lets methodology drive the process instead of relying on ad hoc prompting.

### DOR-REQ-013: Version-Aware Approval

Approval must reference a concrete document version.

Minimum acceptable version references:

- git commit SHA
- document checksum
- explicit revision number
- timestamp plus immutable artifact snapshot

If the spec changes after approval, impacted decisions should be marked
`reopened` or `needs_recheck` unless the change is clearly non-semantic.

### DOR-REQ-014: Progressive Expectation Capture

This document should grow as new review expectations emerge.

New needs should be added as:

- a new requirement in the index
- a concrete requirement record
- optional command or workflow impact
- optional method-object mapping

Avoid burying durable process requirements inside chat history. Chat can
discover the need; the requirement document should retain it.

### DOR-REQ-015: Side-Review Command Boundaries

The review method must model which commands are available in which conversation
surface.

Observed constraint:

```text
'/btw' is unavailable in side conversations. Press Ctrl+C to return to the
main thread first.
```

This affects decision-oriented review because a side review may discover a new
subtopic that also deserves isolation. The method should not rely on recursive
side conversations unless the host supports them.

Required behavior:

- a side review can record a follow-up side-review request as a review delta
- the main thread or conductor decides whether to open the next side review
- the review ledger records that the follow-up came from a side conversation
- commands such as `/review decision`, `/review bundle`, and `/btw` should
  declare whether they are valid from the main thread, side threads, or both

Practical implication:

```text
Side conversation finds related issue
  -> emits ReviewDelta(follow_up_review=DEC-017)
  -> main thread updates ledger
  -> human/conductor opens a new side review from the main thread if needed
```

This keeps side conversations useful without turning them into an unmanaged
tree of nested review contexts.

## Open Design Questions

- Should decision records start embedded in specs and be extracted only when a
  threshold is exceeded?
- What threshold should trigger split decision documents: line count, number of
  decisions, number of unresolved review notes, or expected implementation
  risk?
- Should review ledgers be plain Markdown, YAML, JSONL, or generated from
  structured frontmatter?
- How should a conductor detect that two independent review sessions produced
  conflicting advice?
- Which commands are user-facing interaction commands, and which are internal
  method tasks?

## Initial Workflow Sketch

```text
Draft spec
  -> extract Decision Index
  -> build Decision Graph
  -> run role-based agent review
  -> run human grouped review
  -> update Review Ledger
  -> patch spec and decision records
  -> run synthesis review
  -> approve for implementation planning
```
