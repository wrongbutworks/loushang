# Harness Conversation Runtime Core Boundary

## Status

Status: implementation complete for integration into `lane/harness`.

This capability owns the product-neutral mechanics behind durable, branching
agent conversations. It lets Coding, Research, Design, PPT, Cowork, and OEM
products share one repository, replay, catalog, and compaction-planning core
without sharing a transcript schema, prompt, model, or artifact vocabulary.

## Ownership

`loushang.harness.conversation` owns:

- neutral conversation headers, parent-linked record envelopes, tree nodes,
  branch deltas, and structured `CommandExecutionRecord` payloads;
- header and record codec ports, projector ports, and state-folder ports;
- `ConversationRepository`, composed over the existing Harness
  `TranscriptRepository` and `BranchGraph` rather than duplicating JSONL or
  graph behavior;
- active-path selection, children, tree construction, lowest common ancestor,
  branch delta, fork, and state fold mechanics;
- `ConversationReplayFolder`, including visible-item projection, checkpoint
  replacement, first-kept suffix reconstruction, and independent product-state
  folding;
- `ConversationCatalog`, `ProjectionQuery`, and composition with
  `JsonProjectionIndex` for discover, project, cache, filter, sort, and limit;
- functional adapters for products that prefer callables over custom classes.

`loushang.harness.context.conversation` owns:

- opaque-record turn grouping;
- recent-token cut-point selection;
- non-cut roles such as tool results;
- split-turn history, turn-prefix, and kept-record planning;
- previous-summary boundary and token accounting;
- cut-group expansion so invisible metadata can remain attached to the first
  kept visible record;
- separate per-record cut estimation and aggregate context-token estimation.

These packages must not import Coding, AI messages, model/provider code,
Product stores, Method, Work, TUI, or channel implementations.

## Product Ports

A Product supplies the semantics that cannot be inferred by Harness:

- concrete header and record schemas plus their historical wire codecs;
- record id, parent id, visibility, role, and token-estimation functions;
- checkpoint recognition and summary-item projection;
- product state initialization and reduction;
- catalog discovery roots, accepted filenames, summary fields, match/scoring
  rules, index location, and fail-fast or per-item projection-error policy;
- exact compaction and branch-summary prompts, model calls, retry behavior,
  content serialization, and artifact extraction;
- command-record projection into its Agent message and UI/event protocols.

The split is deliberately asymmetric: Harness owns the control mechanics;
Products name and interpret the data.

## Coding Adoption

Coding now uses `ConversationRepository[SessionHeader, SessionEntry]` as its
session repository. `coding.store.file_codec` retains the Pi-compatible JSONL
schema and legacy recovery behavior but no longer returns or imports the lower
level `TranscriptRepository` directly.

`SessionManager` delegates active branches, children, tree, fork, lowest common
ancestor, branch delta, replay, catalog indexing, and generic query execution to
Harness. Coding retains:

- `SessionHeader` and `SessionEntry` variants;
- camelCase JSON fields, legacy tags, surrogate/non-finite recovery, and exact
  JSONL formatting;
- label, cwd, naming, retention, recovery, and session-file policy;
- `SessionSummary` fields, message text/preview, diagnostics, and relevance
  scoring;
- Agent-message projection and model/thinking-state interpretation.

Coding compaction now maps `SessionEntry` records into
`ConversationCompactionPlanner`. The former local cut-point, latest-checkpoint,
turn-start, tool-result, and kept-id algorithms have been removed. Coding keeps
its public compatibility plan/preparation records, message estimator, aggregate
usage estimator, prompts, model invocation, file-operation details, and summary
artifact projection.

`BashExecutionMessage` specializes `CommandExecutionRecord`; the historical
`bashExecution` role and JSON fields remain Coding-owned.

## Compatibility Invariants

- Existing Coding JSONL files decode with the same Product codec and remain
  writable without schema migration.
- Harness replay and compaction planning reject missing or future retained-record
  boundaries by default; Coding explicitly selects summary-only recovery for
  historical malformed records.
- Harness catalogs fail fast by default; Coding explicitly skips a single bad
  Product projection to preserve directory enumeration behavior.
- Branch selection, tree labels, fork contents, and unknown-leaf behavior are
  unchanged.
- Replay uses only the selected active path and the latest checkpoint, delays
  visible projection until that checkpoint is known, and still folds model and
  thinking state across every path record.
- A tool result cannot become a compaction cut point.
- Split-turn plans preserve history, turn-prefix, and kept ids.
- summarized, turn-prefix, and kept record partitions never overlap.
- Aggregate context usage and per-record cut estimates remain distinct.
- Metadata immediately preceding a retained message stays inside the retained
  checkpoint boundary.
- Product prompts, model calls, artifact details, and summary wire payloads are
  byte- and behavior-compatible.

## Neutrality Evidence

Harness tests use Research-shaped records to exercise persistence, branching,
fork, tree, LCA/delta, replay checkpoints, catalog/index/query, turn grouping,
split turns, tool-result atomicity, metadata cut groups, and previous-summary
accounting without importing Coding or AI.

Coding tests cover historical JSONL codecs, context replay, session catalogs,
fork/tree/labels, compaction parity, branch summaries, and command-record
projection. Architecture tests enforce dependency direction and prevent these
new symbols from becoming accidental top-level Harness exports.

## Explicit Non-Goals

This capability does not:

- define a universal Product transcript schema or force Products to use the
  neutral default envelope;
- serialize `AgentMessage` or own AI message codecs;
- choose a model, resolve credentials, or call a provider;
- define compaction prompt text, salience policy, memory policy, or artifact
  meaning;
- choose Product session roots, filenames, retention, recovery, or index fields;
- replace Product controllers, commands, event protocols, UI, or host lifecycle;
- migrate shell selection, execution lifecycle, hooks, or approval policy.

The next host/session wave may compose this conversation core with
`loushang.harness.host` and `loushang.harness.runtime`; it must not pull the
Product-owned semantics above into Harness.
