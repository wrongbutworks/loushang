# Harness Agent Transcript File Store Boundary

## Status

Status: implementation complete for integration into `lane/harness` on
`harness/agent-transcript-file-store`.

## Purpose

The optional `loushang.harness.agent_transcript` profile owns the current
Native Agent transcript JSONL provider. This includes the v1 header and record
codecs, durable journal policy, platform file lock, file layout, discovery,
and `FileConversationStore` adapter. These are common Agent-transcript storage
mechanisms, not Coding semantics.

The neutral `loushang.harness.conversation` and `loushang.harness.storage`
cores remain independent of Agent and AI. They own repository and store
protocols respectively; the Agent transcript profile supplies the typed native
codec and record identity functions required by the file provider.

## Binding Contract

`AgentTranscriptFileLayout` maps a selected root to `ConversationKey` values
and current Native JSONL paths. A Product chooses the root and may inject a
filename function. `create_agent_transcript_file_store()` then produces the
standard `ConversationStore[ConversationHeader, AgentTranscriptRecord]`.

At session construction, a Product binds one selected `ConversationStore` and
one `AgentTranscriptProfile` into `AgentTranscriptSessionStore`. The standard
`AgentTranscriptSession` owns session-facing transcript operations over that
store: durable commit observation, standard Agent/application records,
annotations, selected-branch context, and idempotent application-message
commit. It does not create a second repository or own Product lifecycle.

Coding supplies its runtime-profile selection, session root, persist decision,
summary/search projection, display naming, retention, CLI/TUI behavior, and
diagnostic wording. `SessionManager` is a Coding facade over the Harness
transcript session rather than the owner of native codecs or file layout.

## Current Format Policy

The native loader accepts only `ConversationHeader.version == 1` and standard
Agent transcript payload codecs. It rejects old or future envelopes before any
rewrite. A malformed complete record fails; an incomplete trailing JSONL line
is skipped for reads and repaired only by a writable load, following the shared
journal policy.

Current Loushang Session v3 migration remains an explicit external operation
in the transcript migrator. Pi, Claude Code, Codex, and other formats remain
external importers. The normal native loader never performs implicit migration
or recovery into an empty transcript.

## Provider Extensibility

The file provider is a reference implementation, not the storage abstraction.
Products, OEMs, or extensions may select a Memory, SQL, Redis, or custom
provider by supplying a conforming `ConversationStore` through the sealed
runtime profile before a session is created. A provider cannot be replaced
after the session binding is sealed. This wave does not implement SQL, Redis,
outbox delivery, or extension-owned persistence providers.

## Verification

- Harness tests cover current Native file creation, discovery, custom filename
  selection, and future-format rejection without rewrite.
- Coding file/session tests exercise the same Harness provider through Coding
  compatibility exports and runtime-profile assembly.
- Import-boundary tests require codec and lock ownership in
  `harness.agent_transcript.file_store` and prohibit Coding from recreating
  them.
