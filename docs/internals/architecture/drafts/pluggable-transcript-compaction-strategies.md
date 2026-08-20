# Pluggable Transcript Compaction Strategies

**Status**: Draft / exploratory
**Date**: 2026-08-20
**Area**: `loushang.harness.transcript` compaction + session file lifecycle
**Related**: existing `context.compaction` capability, transcript session resume path

---

## 1. Problem Statement

Two compounding issues make large loushang transcripts expensive:

1. **Resume cost grows with file size.** Resume loads and integrity-verifies every
   record in the transcript (`_canonical_dumps` per node, hash verification).
   A 19 MB session took 17.3 s before the load-path work; it is ~3.5 s now, but
   sessions grow without bound and the current conversation already exceeds 30 MB.
   `model_input_v2` snapshots dominate the byte count and are never pruned.
2. **One rigid compaction strategy.** The only compaction implementation is
   `agent_transcript.turn_aware_summary` (`TURN_AWARE_SUMMARY_IMPLEMENTATION`,
   `compaction.py:26`): a model summarization of the older history appended as a
   `context.compaction_checkpoint` record, with a `keep_recent_tokens` tail kept
   verbatim. It is logical-only: records are never removed, and resume still
   parses the whole file.

Reference research (`cc/`, `codex/` — see `.research/cc_compact_strategy.md`,
`.research/codex_compact_strategy.md`) shows both mature products solve the same
problem with **pluggable, selectable compaction strategies** plus
**checkpoint-based context rebuild** (cc prunes on load only because it has no
revision counting; codex rebuilds the model context from the newest checkpoint
and keeps the rollout fully intact).

This draft proposes: (a) a strategy registry for compaction implementations with
strict JSON configuration (extending the existing capability pattern), and
(b) checkpoint-aware context rebuild so checkpoints make the resumed **model
context** cheaper, as the first delivered strategy (see §5.3 for why load cost
is addressed by session segmentation instead).

## 2. Goals / Non-Goals

### Goals

- Make the compaction mechanism selectable per profile/configuration, not
  hard-wired to one implementation (plugin-style replaceability).
- Make compaction observably reduce resume cost for large sessions (target:
  resume parses only post-checkpoint content once a checkpoint exists).
- Keep the durable transcript append-only and integrity-preserving; never
  rewrite or truncate the live JSONL while a session is active.
- Keep strict JSON configuration and validation for every strategy (mirror
  `TranscriptCompactionConfiguration.from_json`/`to_json`).

### Non-Goals

- Physical file rotation/segmentation of the active transcript (deferred; see
  `rollover_segment` strategy sketch in §6 — a future second implementation).
- Removing `model_input_v2` snapshots from transcripts (separate concern).
- Changing the transcript file format or the per-node hash model.
- Full-text resume search semantics (separate session-catalog work).

## 3. Reference Findings (Evidence Summary)

### Claude Code (`cc/`)

- Multi-stage pipeline before each query: tool-result budget → snip →
  microcompact → context collapse → **auto-compact** → reactive compact
  (`src/query.ts:366-462`).
- Auto-compact threshold ≈ effective window − 20 k reserved − 13 k buffer
  (~83.5% of a 200 k window) (`src/services/compact/autoCompact.ts:30-90`).
- Disk is append-only at compact time; **physical pruning happens at
  load/resume**: `applyPreservedSegmentRelinks` re-links the preserved tail and
  deletes pre-boundary entries (`src/utils/sessionStorage.ts:1836-1937`);
  buffered reads skip pre-boundary bytes above a threshold
  (`sessionStorage.ts:3520-3560`).
- Compaction boundary is a `system/compact_boundary` entry; the summary becomes
  a synthetic user message; attachments (≤5 recent files, ≤50 k tokens) are
  re-injected (`src/services/compact/compact.ts:318-325, 440-540`).
- Configurable via `autoCompactEnabled`, `DISABLE_COMPACT`, PreCompact/PostCompact
  hooks, `/compact [instructions]` (`commands/compact/`, `hooks.ts:3961-4087`).

### Codex CLI (`codex/`)

- Auto-compact by token threshold (`model_auto_compact_token_limit`, scope
  `Total`/`BodyAfterPrefix`), pre-turn and mid-turn triggers
  (`core/src/session/context_window.rs:23-91`, `turn.rs:396-457, 1003-1017`).
- Summary path: model call, `SUMMARY_PREFIX` + last assistant message, keeps
  recent user messages ≤ `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000`
  (`core/src/compact.rs:266-270, 466-527`).
- `CompactedItem` with `replacement_history` is **appended** to the rollout;
  old lines are kept but ignored: resume finds the newest `Compacted`
  newest-to-oldest and replays only the suffix
  (`core/src/session/rollout_reconstruction.rs:114-190`).
- Token-budget variant skips summarization entirely and installs a fresh
  context window (`compact_token_budget.rs`, `session/mod.rs:3700-3749`).
- Compaction prompt is replaceable: `compact_prompt` config.toml string and
  `experimental_compact_prompt_file` (`config_toml.rs:242, 513`); pre/post
  compact hooks can stop or observe compaction (`hook_runtime.rs:404-465`).

### Common design (the pattern to adopt)

- **Summary + recent tail** is the accepted strategy in both products (not
  summary-only).
- **Checkpoint-prefix content is skipped/ignored at resume**, which is what
  makes large sessions fast again.
- **The summarizer and the strategy are replaceable/selectable**, not
  hard-coded.

## 4. Current Loushang Model

- `TranscriptCompactionConfiguration` (strict JSON, `compaction.py:52-131`):
  `enabled`, `compact_percent`, `reserve_tokens`, `keep_recent_tokens`.
- `AgentTranscriptCompactionCapability` (`compaction.py:136-181`): one
  implementation + version, validated against the whitelist; exposes
  `.policy` and `.prepare()`.
- `create_agent_transcript_compaction_capability(implementation, version, config)`
  (`compaction.py:182`): the factory/registration point.
- Runtime selection: `get_runtime_capability("context.compaction")`
  (`product_session.py:154-159`).
- Planner: `plan_turn_aware_compaction` → `summarized_entry_ids`,
  `kept_entry_ids` (tail after `keep_recent_tokens`), `first_kept_entry_id`.
- Checkpoint record: `context.compaction_checkpoint`
  (`CONTEXT_COMPACTION_CHECKPOINT_KIND`, `kinds.py:7`); appended via
  `session.append_compaction` (`session.py:253-273`); the store append is
  pure-append (`stores/file.py:256-330`).
- Resume: `ProductTranscriptSession.load` → full `_load_mapping` parse +
  per-node hash verification (`conversation/jsonl_codec.py`, transcript codecs).
  No boundary awareness on load today. The load path is also the single
  integrity-verification point: journal `_load_mapping` deep-validates every
  line (`journal/jsonl.py:469-506`), and the store derives revision from
  `len(records)` (`conversation/stores/file.py:249, 285`).

## 5. Proposed Design

### 5.1 Strategy registry (plugin seam)

Extend the capability factory into a registry keyed by `implementation` string.
Each implementation is a self-contained module providing:

- `implementation: str` + `version: int` (registered constants);
- strict-JSON configuration schema (`from_json`/`to_json`) with `enabled`,
  plus strategy-specific fields;
- `prepare(entries, keep_recent_tokens=None) -> CompactionPreparation`;
- `apply_transcript_semantics` — the storage/lifecycle behavior of the strategy
  (see below), defined by the strategy, not by the core.

Selection stays capability-style: `get_runtime_capability("context.compaction")`
returns the profile-selected implementation; unknown implementations are
rejected (existing whitelist behavior) but the whitelist becomes a registry
lookup instead of a single constant.

### 5.2 Strategy dimension: content of the resumed context

All strategies share the planner's split (summarized region / kept tail) but
differ in **where the tail lives**:

| Strategy | Summary | Tail location | Model-context cost | Load cost |
|---|---|---|---|---|
| `turn_aware_summary` (today, adjusted) | in-file checkpoint | same file, after checkpoint | post-checkpoint only (after §5.3) | full file (unchanged) |
| `session_memory` | in-file checkpoint | moved to a session-memory sidecar (cc experiment) | sidecar + tail only | full file + sidecar |
| `rollover_segment` | checkpoint in old file | new session file (`parentSession` chain) | new file only | **new file only (tiny)** |
| `fresh_window` | none (no model call) | none; initial context only (codex token-budget) | initial context only | full file (unchanged) |

The first two are the "summary vs summary + tail" question from earlier
discussion; `rollover_segment` is the "compact naturally opens a new session"
idea (process/session boundary instead of hash chaining); `fresh_window` is the
zero-summary escape hatch. Only `rollover_segment` reduces the **load** cost;
the others reduce **model-context** cost.

### 5.3 Checkpoint-aware context rebuild (deliverable #1, revised after review)

Review finding: skipping the checkpoint prefix at the **store/journal load
depth is not feasible** in loushang's integrity model. The load path is the
only integrity-verification point (journal `_load_mapping` deep-validates every
line, `journal/jsonl.py:469-506`), the store must count all records for
revision-based conflict detection (`conversation/stores/file.py:249, 285`), and
with transcript branching (`session.py:162`) the newest checkpoint's
`first_kept_record_id` is not a unique boundary across forks. Codex is the
isomorphic reference here: it keeps the rollout append-only and fully intact,
and rebuilds the **model context** from the newest checkpoint — load cost is
unchanged, model-context cost drops.

Revised design (codex `rollout_reconstruction` pattern,
`codex/core/src/session/rollout_reconstruction.rs:114-190`):

- Load stays full and integrity-preserving (revision counting, per-node hash
  verification, branch semantics all intact).
- After load, the **model-facing context** is rebuilt from the newest
  `context.compaction_checkpoint`: prefix records are replaced by the
  checkpoint summary (synthetic context message), and the suffix after
  `first_kept_record_id` is appended verbatim.
- Keep a full-integrity audit mode (`loushang verify`) for whole-file
  verification on demand (already how the load path behaves today).
- File-level guard: mirror cc's `MAX_TRANSCRIPT_READ_BYTES`-style bail-out for
  raw reads above a size threshold to prevent OOM on pathological files
  (`cc/src/utils/sessionStorage.ts:229-232`).

This reduces **model-context** cost (tokens), which is what the existing
in-file compaction is for; it does **not** reduce load time. Load-time
reduction is delivered by `rollover_segment` (§6), or by a future physical
prune that would deliberately trade away append-only/revision semantics.

### 5.4 Pluggable summarizer

Mirror codex: add optional `compact_prompt` / `compact_prompt_file` to the
strategy configuration, passed to the summarizer binding (analogous to
`prepare_model_call` today). Mirrors cc: expose PreCompact/PostCompact hook
seams where pre-compact output becomes summarization instructions and
post-compact receives the summary (harness hook system already exists).

### 5.5 Trigger policy (orthogonal)

Keep threshold triggers (`compact_percent`, `reserve_tokens`,
`keep_recent_tokens`) and add manual command surface (e.g. `/compact
[strategy]`) + size/time triggers for `rollover_segment`.

## 6. Rollover-Segment Sketch (future implementation)

- Trigger: file size threshold and/or manual `/rollover`.
- On rollover: freeze current file; create a new session via
  `ProductTranscriptSession.new(..., parent_session=<old id>)` (mechanism
  exists, `product_session.py:197-204`); write the compaction summary as the
  new session's first context message (or reference it).
- No format change; each file stays append-only and self-integrity-verifiable.
- Resume list renders session chains via `parentSession` (already indexed in
  `session_catalog`); search can walk chains.
- Open questions: double-storage of the tail (copy vs move — move requires
  rewriting the old file, breaking append-only; prefer copy), chain UX, and
  multi-segment back-navigation.

## 7. Open Questions (for review)

1. Should the checkpoint-aware context rebuild (§5.3) be the default resume
   path once a checkpoint exists, with full-history context opt-in, or the
   reverse? (After review: this affects model context, not load cost; the
   integrity question is moot because load stays full.)
2. Where should the summary live for `rollover_segment`: duplicated in the new
   session's first message vs referenced via `parentSession`?
3. Is `session_memory` (sidecar) worth a separate strategy, or should the tail
   always stay in-file?
4. Which strategy should be the default when a profile does not declare one?
5. Should strategy selection be user-visible (`/compact [strategy]`) or
   configuration-only at first?
6. Does the reviewer's concern about branch semantics (§5.3) require the
   checkpoint rebuild to pick the newest checkpoint **on the active branch**
   (records_to(leaf_id)) rather than the newest checkpoint in the file?
   (Likely yes — the rebuild must respect `records_to`/branch deltas.)

## 8. Suggested Rollout Order (revised after review)

1. **Checkpoint-aware context rebuild** (§5.3, revised) — reduces model-context
   cost; no format change; load stays full/integrity-preserving.
2. **Strategy registry** (§5.1) — refactor the whitelist into a lookup; keep
   `turn_aware_summary` as the only registered strategy initially.
3. **Pluggable summarizer + hooks** (§5.4).
4. **`rollover_segment`** (§6) as the second registered strategy — the only
   one that reduces **load** time; needs review sign-off on the
   `parentSession` chain UX and tail-copy semantics.

## 9. Evidence Index

- Loushang: `src/loushang/harness/transcript/compaction.py`,
  `maintenance.py`, `session.py`, `unit_of_work.py`, `kinds.py`,
  `src/loushang/harness/conversation/stores/file.py`,
  `src/loushang/harness/transcript/product_session.py`.
- Reference: `.research/cc_compact_strategy.md`,
  `.research/codex_compact_strategy.md`.
