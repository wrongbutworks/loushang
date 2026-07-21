# Harness Agent Transcript Catalog Boundary

## Status

Status: implementation complete for integration into `lane/harness` on
`harness/agent-transcript-catalog`.

## Purpose

`loushang.harness.agent_transcript.catalog` owns the reusable read model for
current Native Agent transcript files. It provides `AgentTranscriptSessionCatalog`,
`SessionRecord`, `SessionSummary`, `SessionQuery`, and `SessionTreeNode` for
discovery, summary projection, query, JSON projection indexes, and annotated
branch trees.

This is an optional Agent/AI profile, not a neutral Harness core. The neutral
`loushang.harness.conversation` and `loushang.harness.storage` packages remain
independent of Agent and AI. The catalog may use the standard Agent transcript
profile and the existing neutral `ConversationCatalog`; it must not import
Coding or a Product package.

## Ownership

Harness owns these standard current-format facts:

- direct Native JSONL discovery within a selected session directory;
- per-session metadata, message previews, model snapshot, and diagnostic
  summary fields;
- filters by workspace, name, parent session, text, diagnostic presence, and
  limit, including relevance ordering;
- rebuildable JSON projection indexes for those summaries;
- display-label annotations and selected-branch context reconstruction;
- canonical comparison of transcript session paths.

The catalog uses `ConversationCatalog`, `ConversationRepository`, and
`JsonProjectionIndex`. It does not create another repository or replay
implementation. Native loading remains current-format-only and retains the
file-store loader's corruption and partial-tail policy.

`AgentTranscriptDirectoryRuntime` is the optional runtime layer above that
catalog. It owns current-root and all-root queries, direct or coalesced index
refresh, and deterministic drain on disposal/tests. It does not create or
replace an active session, choose a Product root or retention policy, or
classify Product diagnostics.

Products choose their session roots, whether persistence is enabled, the
runtime transcript profile, product-specific projected fields, retention,
display names, and CLI/RPC/TUI presentation. `coding.session_manager.SessionManager`
remains the Product lifecycle adapter; it delegates the
standard read model instead of maintaining a second catalog.

## Extensibility

`SessionSummary` is a common read model, not a closed cross-product schema. A
Product needing domain-specific search or index fields composes its own
projection over the same Native records or supplies another catalog profile.
It must not fork the file discovery, summary, query, or index mechanics merely
to add presentation fields.

Database, Redis, external search, journal-offset checkpoints, and an
extension-owned catalog provider are outside this boundary. Those additions
must implement the existing storage/catalog ports rather than extend the
current Native file catalog with product policy.

## Verification

- Harness tests cover Native discovery, direct and root-level query, projection
  index refresh/load and coalesced scheduling, branch context, and annotation
  labels without importing Coding.
- Coding session tests exercise the same owner through its compatibility
  facade.
- Import-boundary tests require `SessionManager` to delegate to
  `AgentTranscriptSessionCatalog`, require `AgentSessionRuntime` to consume
  `AgentTranscriptDirectoryRuntime`, require the catalog to use
  `ConversationCatalog`, and prohibit catalog imports from Coding.
