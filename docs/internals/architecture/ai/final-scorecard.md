# Loushang AI Final Scorecard

Last updated: 2026-06-22.

This scorecard records the current release readiness of the AI quality hardening
branch against the execution plan in
[`2026-06-20-loushang-ai-quality-hardening-execution-plan.md`](../../plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md).
It is an owner-level status document, not a replacement for the final review.

## Release Recommendation

Do not tag a release that claims broader live-provider coverage than the
credential-backed evidence below. For the scoped AI package quality-hardening
work, local gates are closed.

The branch has largely reached the intended SDK shape: a curated catalog, narrow
root API, protocol-level core adapters, explicit contrib boundaries, normalized
errors, executable offline examples, and local AI quality gates. Optional
additional live smoke should not expand the public API.

## Objective Score

| Dimension | Target | Current | Status |
|---|---:|---:|---|
| Architecture boundaries | 9.0 | 8.6 | Mostly met |
| Stable API consistency | 8.5 | 8.7 | Met |
| Message and tool normalization | 9.0 | 8.8 | Mostly met |
| Compat and endpoint contract | 9.0 | 8.6 | Mostly met |
| Error and reliability semantics | 8.5 | 8.5 | Met |
| Streaming and cancellation | 8.5 | 8.6 | Met |
| Provider consistency | 8.5 | 8.5 | Met |
| Auth security | 8.0 | 8.1 | Met |
| Model catalog governance | 9.0 | 9.0 | Met |
| Tests, examples, and docs | 9.0 | 9.0 | Met |

Current composite score: 8.6/10.

## Evidence Summary

| Area | Current evidence |
|---|---|
| Root API surface | `tests/ai/test_options.py` verifies root exports stay narrow and provider-specific options remain outside `loushang.ai.__all__`. |
| Catalog budget | `scripts/ai/check_catalog.py` enforces provider <= 11, model <= 20, evidence files, provider matrix alignment, preferred-endpoint uniqueness, and supported modalities. |
| Curated provider facts | `docs/internals/architecture/ai/catalog-evidence/*.md` records official docs, included models, omitted facts, and live-smoke status for each curated provider. |
| Legacy catalog archive | `docs/internals/archive/ai/model-catalog/README.md` records the compressed v1 catalog archive and SHA verification command. |
| Provider boundary | `ProviderRequest` is the single `stream_raw` argument for registered raw providers; contract tests lock the signature, builtin registration, and legacy-signature rejection. |
| Structured output mapping | `tests/ai/test_structured_output.py` verifies structured-output requests are accepted only when the selected provider adapter declares mapping support, not by a core hard-coded API allowlist. |
| Public SDK docs | `docs/en/sdk/README.md`, `docs/zh-CN/sdk/README.md`, and the v2 migration guides document the public path, catalog, auth, errors, examples, and migration rules. |
| Offline examples | `scripts/ai/check_examples.py` executes numbered `examples/ai/[0-9][0-9]_*.py` with live provider keys removed. |
| Import boundaries | `scripts/ai/check_import_boundaries.py` prevents `loushang.ai` from importing agent/coding layers, prevents removed core providers from returning, and keeps top-level examples on stable AI imports. |
| AI gate | `make check-ai` runs lint, mypy, catalog checks, import checks, offline examples, package coverage, scoped core coverage, and adapter coverage; latest run reached 83.36% package coverage, 90.09% runtime-core coverage, and 85.66% provider-adapter coverage with 691 passed and 9 live tests deselected. |
| Full offline test suite | `env -u <provider keys> uv run pytest tests -m "not live" -q` passed on 2026-06-22 with 4260 passed and 9 deselected. |
| Build | `uv build` passed on 2026-06-22 after the final fixes and produced both sdist and wheel artifacts. |
| Live provider smoke | DashScope Responses stream/tools and DeepSeek OpenAI-compatible complete/stream passed on 2026-06-22 with valid local credentials. Moonshot was attempted but rejected by the provider with HTTP 401, so it is not counted as live proof. |

## Final Checklist Status

### Code

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Core only has three protocol adapters | Met | `core-provider-adapter-contract-matrix.md`; `loushang.ai.bootstrap.register_builtin_ai_providers`. |
| Bedrock/Azure not in core | Met | `scripts/ai/check_import_boundaries.py` blocks removed core provider modules. |
| Codex is contrib and explicitly registered | Met | `loushang.ai.contrib.openai_codex.register_openai_codex_contrib`. |
| Core has no provider-id/base-url compat guessing | Mostly met | Compat boundary tests cover provider/runtime leakage; keep any future provider-specific behavior behind endpoint contracts or contrib. |
| Built-in catalog has no legacy full-catalog runtime path | Met | Package data points to `models.curated.v2.json`; full v1 catalog is archived under docs. |
| Provider boundary accepts only normalized context/request facts | Met | Registered raw providers receive one `ProviderRequest` object containing `model`, normalized `context`, `options`, and resolved request facts; old positional provider signatures are rejected. |
| Core has no bare `except Exception: pass` | Met | `rg -n -U "except Exception:\n\s*pass" src/loushang/ai tests/ai tests/providers` returns no matches. |
| Stream queue is bounded | Met | `AssistantMessageEventStream` uses a bounded queue; provider runtime tests cover backpressure and event stream tests cover full-queue terminal preservation. |
| Cancellation closes upstream | Met | Provider runtime closes async sources through `aclose`/`close`; provider runtime tests cover cancellation. |
| Parallel tool calls can interleave | Met | Tool and provider tests cover multi-tool event assembly and parallel tool examples. |
| Structured output is verifiable | Met | Structured output API and tests cover schema parsing and errors. |
| Text/image declarations match implementation | Mostly met | Catalog checker rejects unsupported modalities; advanced video/audio/image-output facts remain omitted. |
| OAuth files are safe | Met | OAuth storage uses locked atomic writes; local POSIX smoke verified `0o700` credential directories and `0o600` store/lock files. |
| Unknown pricing is not zero cost | Met | Pricing and assembler tests preserve unknown cost as `None`. |

### Catalog

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Original catalog archived and SHA-verifiable | Met | `docs/internals/archive/ai/model-catalog/README.md`. |
| Provider <= 11 | Met | `scripts/ai/check_catalog.py`. |
| Model <= 20 | Met | `scripts/ai/check_catalog.py`. |
| Issue #102-#108 have evidence and status | Met | Evidence files exist for Tencent Hunyuan, Z.AI, DeepSeek, MiniMax, Volcano Ark, Baidu Qianfan, and StepFun. |
| Each model has at most one preferred endpoint | Met | `scripts/ai/check_catalog.py`. |
| No unsupported modality in built-in catalog | Met | `scripts/ai/check_catalog.py` allows only text and image. |
| Uncertain facts omitted or marked unknown | Met | Evidence files list unknown/omitted facts; pricing and modality tests preserve unknown values. |

### API

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Root `__all__` has snapshot coverage | Met | `tests/ai/test_options.py`. |
| Full/simple semantics are clear | Met | SDK docs and option tests document `CallOptions` and `SimpleCallOptions`. |
| Unsupported parameters fail instead of being silently ignored | Mostly met | Capability and option tests cover major public paths; keep provider-specific additions behind explicit advanced options. |
| `complete()` raises typed errors | Met | Streaming/API tests cover terminal error conversion to typed `AIError`. |
| Stable error code documented | Met | SDK README and migration guide document `AIError` payload fields and stable codes. |
| Migration guide complete | Met | `docs/en/sdk/migration-v2.md` and `docs/zh-CN/sdk/migration-v2.md`. |

### Tests

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| `make check-ai` passes | Met | Passed on 2026-06-22 with 691 passed and 9 live tests deselected. `test-ai` and `check-ai-coverage` explicitly run `pytest ... -m "not live"` so default AI gates stay offline. |
| `uv run pytest tests -m "not live" -q` passes | Met | Passed on 2026-06-22 with provider keys removed: 4260 passed, 9 deselected. |
| `uv run pytest tests/ai/contracts -q` passes | Met | `tests/ai/contracts/test_core_provider_contracts.py` covers the core adapter protocol and builtin registration contract. |
| `uv run python scripts/ai/check_catalog.py` passes | Met | Catalog gate. |
| `uv run python scripts/ai/check_examples.py` passes | Met | Offline example gate. |
| `uv build` passes | Met | Passed on 2026-06-22 after the final fixes. |
| Core coverage >= 90% | Met | `scripts/ai/check_coverage_targets.py` enforces scoped runtime-core coverage; latest `make check-ai` reported 90.09%. Scope is recorded in `ARD-002-ai-coverage-gate-scope.md`. |
| Adapter aggregate coverage >= 85% | Met | `scripts/ai/check_coverage_targets.py` enforces retained provider adapter aggregate coverage; latest `make check-ai` reported 85.66%. |
| No pending asyncio task | Met | Provider runtime and event stream tests cover cancellation, close behavior, bounded queues, and terminal preservation; current full offline suite passed after those fixes. |
| No secret trace snapshot | Met | Error payload redaction and Codex request-body trace summarization are tested; `.artifacts` and `dist` were scanned for current provider environment secret values with no matches. |

### Examples And Docs

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| All offline examples execute | Met | Numbered offline examples are executed by `scripts/ai/check_examples.py`; advanced offline examples are covered by `tests/examples/test_ai_examples.py`. |
| Each key capability has an example | Met | Numbered examples cover complete, stream, typed context, tools, parallel tools, reasoning, structured output, image input, errors/retry, usage, provider matrix, and provider smoke. |
| Main examples use only stable API | Met | `scripts/ai/check_import_boundaries.py`. |
| Advanced examples are marked clearly | Met | Advanced examples live under `examples/ai/advanced`. |
| Chinese and English docs are aligned | Mostly met | SDK README and migration guides exist in both languages; final copy review should compare them before release. |
| Provider matrix and catalog stay aligned | Met | `scripts/ai/check_catalog.py`. |

### Review

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Each AIQ commit has a focused review | Accepted | Per-commit review frequency was intentionally reduced during execution; final owner review covered the assembled branch instead. |
| Each phase has a range review | Accepted | Several phase gates were validated by commands; the final owner review covered the latest assembled branch after follow-up fixes. |
| Final branch has a full review | Met | Final owner review on 2026-06-22 found no P0/P1 after the final fixes; checks covered hard indicators, stale provider signatures, public import boundaries, catalog/examples gates, full offline tests, build, OAuth file modes, and artifact secret values. |
| P0/P1 = 0 | Met | No P0/P1 findings remain in the final owner review; all earlier final-review blockers and later full-suite failures were fixed and covered by targeted tests plus `make check-ai`. |
| P2 resolved or tracked | Met | Low-cost docs/example P2s, Codex request-body trace summarization, default Codex HTTP client close ownership, legacy provider fallback removal, provider-declared structured-output mapping, advanced-only provider options, and terminal queue edge cases were fixed. |

## Issue #102-#108 Status

| Issue | Provider | Status | Evidence |
|---|---|---|---|
| #102 | Tencent Hunyuan | Included, one model | `catalog-evidence/tencent-hunyuan.md` |
| #103 | Zhipu GLM / Z.AI | Included, two models | `catalog-evidence/zai.md` |
| #104 | DeepSeek | Included, two models | `catalog-evidence/deepseek.md` |
| #105 | MiniMax | Included, one model | `catalog-evidence/minimax.md` |
| #106 | Doubao / Volcano Ark | Included, one model | `catalog-evidence/volcano-ark.md` |
| #107 | Baidu Qianfan / Wenxin | Included, one model | `catalog-evidence/baidu-qianfan.md` |
| #108 | StepFun | Included, one model | `catalog-evidence/stepfun.md` |

All seven entries are catalog-accepted with official evidence and offline
contract checks. Live smoke verification is not claimed unless the matching
provider evidence file records a valid credential-backed run.

## Residual Notes

No required open issue remains for this local quality-hardening branch. Optional
additional live provider smoke can be run with valid credentials, but current
accepted live proof only covers DashScope and DeepSeek.
