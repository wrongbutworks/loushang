# Loushang AI Core Freeze Target Checklist

This checklist records the target architecture for `ai/core-freeze-v1`. It is a
tracking document only; AIF-001 does not implement the items below.

Source plan:
[2026-06-24-loushang-ai-core-freeze-goal.md](../../plans/2026-06-24-loushang-ai-core-freeze-goal.md)

## Concept Cleanup

- [ ] No legacy compat production code remains.
- [ ] No runtime `schemaVersion` migration track remains.
- [ ] No protocol/dialect/compat round-trip projection remains.
- [ ] No `ResolvedEndpoint` / `ResolvedRequest` double request layer remains.
- [x] No empty core `AdapterRuntimeConfig` base class remains.
- [ ] No Simple API or options alias remains.
- [ ] No deprecated provider-specific core options remain.
- [ ] No `Model` instance invocation facade remains.
- [ ] Context normalization runs once per public call.
- [x] Core has no provider account quota special case.
- [ ] Core has one auth configuration type.
- [x] Core exposes one public usage type.

## Model And Registry

- [ ] Built-in runtime model file is `src/loushang/ai/model/models.json`.
- [ ] The legacy large catalog backup is under `backup/ai/` and is not package
  data.
- [ ] The default registry lazily loads built-in models and
  `~/.loushang/models/*.json`.
- [ ] Explicit file and directory loaders are available.
- [ ] Built-in and user model JSON use the same parser and validation path.
- [ ] Duplicate full model IDs fail clearly.
- [ ] Evidence markdown is not a registry gate.
- [ ] JSON-only model extension is proven by tests.

## Invocation Boundary

- [ ] `complete()` uses non-streaming upstream requests where the protocol
  supports them.
- [ ] `stream()` uses streaming upstream requests.
- [ ] Stream capability gates only `stream()`, not `complete()`.
- [ ] OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages adapters
  support both invocation modes.
- [ ] Tools, reasoning, structured output, image input, usage, cost, retry,
  timeout, cancellation, and typed errors do not regress.
- [ ] Explicit unsupported options fail before the provider call.

## Reliability

- [ ] Retry only happens before visible output.
- [ ] Pre-visible retry buffering is bounded.
- [ ] Cancellation closes upstream resources.
- [ ] The event queue stays bounded.
- [ ] Each stream has exactly one terminal event.
- [ ] `AIError` output is stable and secret-safe.
- [ ] Credential storage remains atomic, private, and protected against
  concurrent writes.
- [ ] Unknown pricing yields `None`, not zero cost.

## Validation And Review

- [ ] Every AIF goal is committed separately.
- [ ] Every AIF commit records the actual focused validation that ran.
- [ ] Every AIF commit has a review report under `.artifacts/ai-reviews/`.
- [ ] `make check-ai` passes at each phase gate.
- [ ] Final `uv run pytest tests -q` passes.
- [ ] Final `uv build` passes.
- [ ] Main offline examples pass.
- [ ] Final review has P0=0 and P1=0.
