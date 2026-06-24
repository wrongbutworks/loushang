# Loushang AI Core Freeze Target Checklist

This checklist records the target architecture for `ai/core-freeze-v1`.

Source plan:
[2026-06-24-loushang-ai-core-freeze-goal.md](../../plans/2026-06-24-loushang-ai-core-freeze-goal.md)

## Concept Cleanup

- [x] No legacy compat production code remains.
- [x] No runtime `schemaVersion` migration track remains.
- [x] No protocol/dialect/compat round-trip projection remains.
- [x] No `ResolvedEndpoint` / `ResolvedRequest` double request layer remains.
- [x] No empty core `AdapterRuntimeConfig` base class remains.
- [x] No Simple API or options alias remains.
- [x] No deprecated provider-specific core options remain.
- [x] No `Model` instance invocation facade remains.
- [x] Context normalization runs once per public call.
- [x] Core has no provider account quota special case.
- [x] Core has one auth configuration type.
- [x] Core exposes one public usage type.

## Model And Registry

- [x] Built-in runtime model file is `src/loushang/ai/model/models.json`.
- [x] The legacy large catalog backup is under `backup/ai/` and is not package
  data.
- [x] The default registry lazily loads built-in models and
  `~/.loushang/models/*.json`.
- [x] Explicit file and directory loaders are available.
- [x] Built-in and user model JSON use the same parser and validation path.
- [x] Duplicate full model IDs fail clearly.
- [x] Evidence markdown is not a registry gate.
- [x] JSON-only model extension is proven by tests.

## Invocation Boundary

- [x] `complete()` uses non-streaming upstream requests where the protocol
  supports them.
- [x] `stream()` uses streaming upstream requests.
- [x] Stream capability gates only `stream()`, not `complete()`.
- [x] OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages adapters
  support both invocation modes.
- [x] Tools, reasoning, structured output, image input, usage, cost, retry,
  timeout, cancellation, and typed errors do not regress.
- [x] Explicit unsupported options fail before the provider call.

## Reliability

- [x] Retry only happens before visible output.
- [x] Pre-visible retry buffering is bounded.
- [x] Cancellation closes upstream resources.
- [x] The event queue stays bounded.
- [x] Each stream has exactly one terminal event.
- [x] `AIError` output is stable and secret-safe.
- [x] Credential storage remains atomic, private, and protected against
  concurrent writes.
- [x] Unknown pricing yields `None`, not zero cost.

## Validation And Review

- [x] Every AIF goal is committed separately.
- [x] Every AIF commit records the actual focused validation that ran.
- [x] Every AIF commit has a review report under `.artifacts/ai-reviews/`.
- [x] `make check-ai` passes at each phase gate.
- [x] Final `uv run pytest tests -q` passes.
- [x] Final `uv build` passes.
- [x] Main offline examples pass.
- [ ] Final review has P0=0 and P1=0.
