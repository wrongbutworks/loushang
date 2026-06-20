# Loushang AI Quality Hardening Charter

[Internals](../) | [Plans](./README.md) | [Execution plan](./2026-06-20-loushang-ai-quality-hardening-execution-plan.md)

## Status

Accepted implementation charter for the `ai/quality-hardening-v2` branch.

- Plan ID: `AIQ-001`
- Baseline: `origin/main` at `c5eabfd` on 2026-06-20
- Target contract version: `0.2.0`, pending a final release commit
- Primary package boundary: `src/loushang/ai`

## Goal

This work hardens `loushang.ai` into a smaller, typed, verifiable lower-level
AI SDK. The package should own model invocation, provider request mapping,
stream assembly, usage observations, authentication resolution, and stable
public AI data contracts. It must not own agent lifecycle, session orchestration,
tool execution loops, product policy, or application-level configuration.

The complete implementation sequence and acceptance gates are defined in the
[quality hardening execution plan](./2026-06-20-loushang-ai-quality-hardening-execution-plan.md).

## Scope

The hardening branch covers these architectural changes:

- Shrink the stable root API to the common invocation, model access, message,
  tool, event, usage, options, and error contracts.
- Move provider registry internals, raw stream assembly, catalog loading,
  endpoint resolution, credential stores, and provider-specific payload helpers
  behind advanced or contrib boundaries.
- Replace legacy `compat` dictionaries with typed model capabilities,
  endpoint protocol features, wire dialects, transport facts, routing facts,
  and model bindings.
- Normalize context, messages, tools, errors, streaming events, usage, auth, and
  call options at a single explicit boundary before provider adapters run.
- Centralize provider runtime behavior for retry, cancellation, stream terminal
  semantics, resource closing, and typed error mapping.
- Reduce the built-in catalog to a curated provider set with official evidence,
  explicit unknown facts, and strict provider/model budgets.
- Isolate OpenAI Codex under `loushang.ai.contrib.openai_codex`, and remove
  Bedrock and Azure OpenAI from the core package for this version.
- Add behavior tests, contract tests, executable examples, docs, and review
  evidence for every user-visible capability changed by this plan.

## Non-goals

This branch does not add an agent loop, session recovery, RAG, MCP orchestration,
HTTP/RPC service layer, full model database, or dedicated native adapters for
every vendor. It also does not claim audio, video, embeddings, image generation,
or other modalities until a complete public protocol and tests exist.

Provider facts must not be guessed. If official documentation, an official SDK,
or a real API response does not establish a model ID, base URL, capability,
context window, pricing field, or protocol behavior, the fact stays omitted or
unknown.

## Quality Gates

This charter lists the branch-level final gates. The execution plan remains the
authoritative checklist for phase-specific and commit-specific gates.

Final branch acceptance requires all of the following:

- `make check-ai` passes.
- `uv run pytest tests -q` passes.
- `uv run pytest tests/ai/contracts -q` passes.
- `uv run python scripts/ai/check_catalog.py` passes.
- `uv run python scripts/ai/check_examples.py` passes.
- `uv build` passes.
- Contract suites cover the retained provider adapters.
- Root stable API exports have a snapshot test.
- Normalization, error, stream terminal, retry, cancellation, and catalog
  invariants have behavior tests.
- AI core statement coverage is at least 90%.
- Provider adapter aggregate coverage is at least 85%.
- Built-in catalog provider, endpoint, and model counts stay within the plan
  budgets.
- Core code has no provider ID or base URL compatibility guessing.
- Built-in catalog has no legacy `compat`.
- Unknown pricing yields `None`, not zero cost.
- Offline examples execute successfully.
- No pending asyncio task warnings remain in the validated stream/runtime tests.
- No secret appears in trace snapshots or serialized error details.
- P0 and P1 review findings are zero before the branch is considered complete.

## Architecture Decision Summary

The hardening branch is governed by these decisions:

1. `loushang.ai` is a lower-level SDK boundary. Agent and coding products may use
   it, but the package must not import or orchestrate those upper layers.
2. Model capability, endpoint protocol support, wire dialect, transport, routing,
   and upstream model binding are separate facts with separate owners.
3. Public callers may pass typed objects or supported compatibility dictionaries,
   but provider adapters receive only normalized canonical inputs.
4. Provider adapters map normalized requests to vendor payloads and vendor
   events to raw parts. They do not own public event stream construction,
   generic retry, cancellation, or final message assembly.
5. Error semantics are typed and stable across configuration, auth, validation,
   provider, stream, timeout, rate limit, cancellation, and protocol failures.
6. The built-in catalog is curated evidence, not a broad model index. Long-tail
   providers and models remain available through custom catalog loading.
7. Tests, examples, docs, and review reports are part of each vertical slice, not
   optional follow-up work for user-visible behavior.

## Execution Discipline

Each `AIQ-*` work package is one independently verifiable commit. The branch
uses the AI worktree lane, keeps commits ordered by the execution plan, runs
focused checks before broader gates, and does not push code without an explicit
user request.
