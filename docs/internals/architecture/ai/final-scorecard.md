# Loushang AI Final Scorecard

Last updated: 2026-06-22.

This scorecard records the current release readiness of the AI quality hardening
branch against the execution plan in
[`2026-06-20-loushang-ai-quality-hardening-execution-plan.md`](../../plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md).
It is an owner-level status document, not a replacement for the final review.

## Release Recommendation

Do not tag a release that claims broader live-provider coverage or broader
architecture-boundary completion than the evidence below. Local gates are closed
for the final-review fix package, but one architecture-boundary item remains
tracked.

The branch has largely reached the intended SDK shape: a curated catalog, narrow
root API, protocol-level core adapters, explicit contrib boundaries, normalized
errors, executable offline examples, and local AI quality gates. Runtime
provider/base-url compatibility heuristics still need a focused boundary cleanup
or an explicit ADR before the branch is described as fully compliant with the
architecture checklist.

## Objective Score

| Dimension | Target | Current | Status |
|---|---:|---:|---|
| Architecture boundaries | 9.0 | 8.3 | Not fully met |
| Stable API consistency | 8.5 | 8.7 | Met |
| Message and tool normalization | 9.0 | 8.8 | Mostly met |
| Compat and endpoint contract | 9.0 | 8.2 | Not fully met |
| Error and reliability semantics | 8.5 | 8.5 | Met |
| Streaming and cancellation | 8.5 | 8.6 | Met |
| Provider consistency | 8.5 | 8.5 | Met |
| Auth security | 8.0 | 8.1 | Met |
| Model catalog governance | 9.0 | 9.0 | Met |
| Tests, examples, and docs | 9.0 | 9.0 | Met |

Current composite score: 8.5/10.

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
| AI gate | `make check-ai` runs lint, mypy, catalog checks, import checks, offline examples, package coverage, scoped core coverage, and adapter coverage; latest run reached 83.62% package coverage, 90.10% runtime-core coverage, 85.84% provider-adapter coverage, and 85.39% production-adapter-module coverage with 696 passed and 9 live tests deselected. |
| Full offline test suite | `env -u <provider keys> uv run pytest tests -m "not live" -q` passed on 2026-06-22 with 4260 passed and 9 deselected before the final-review P1 fix package. It was not rerun after that package to avoid another broad pass. |
| Build | `uv build` passed on 2026-06-22 before the final-review P1 fix package and produced both sdist and wheel artifacts. It was not rerun after that package. |
| Live provider smoke | DashScope Responses stream/tools and DeepSeek OpenAI-compatible complete/stream passed on 2026-06-22 with valid local credentials. Moonshot was attempted but rejected by the provider with HTTP 401, so it is not counted as live proof. |

## Final Checklist Status

### Code

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Core only has three protocol adapters | Met | `core-provider-adapter-contract-matrix.md`; `loushang.ai.bootstrap.register_builtin_ai_providers`. |
| Bedrock/Azure not in core | Met | `scripts/ai/check_import_boundaries.py` blocks removed core provider modules. |
| Codex is contrib and explicitly registered | Met | `loushang.ai.contrib.openai_codex.register_openai_codex_contrib`. |
| Core has no provider-id/base-url compat guessing | Not fully met | Runtime compatibility code still includes provider/base-url heuristics and provider-specific branches. Move these behind endpoint contracts or record an ADR before claiming this requirement complete. |
| Built-in catalog has no legacy full-catalog runtime path | Met | Package data points to `models.curated.v2.json`; full v1 catalog is archived under docs. |
| Provider boundary accepts only normalized context/request facts | Met | Registered raw providers receive one `ProviderRequest` object containing `model`, normalized `context`, `options`, and resolved request facts; old positional provider signatures are rejected. |
| Core has no bare `except Exception: pass` | Met | `rg -n -U "except Exception:\n\s*pass" src/loushang/ai tests/ai tests/providers` returns no matches. |
| Stream queue is bounded | Met | `AssistantMessageEventStream` uses a bounded queue; provider runtime tests cover backpressure and event stream tests cover full-queue terminal preservation. |
| Cancellation closes upstream | Met | Provider runtime and event streams close async sources through `aclose`/`close`; targeted tests cover consumer-close cancellation and producer cleanup. |
| Parallel tool calls can interleave | Met | Tool and provider tests cover multi-tool event assembly and parallel tool examples. |
| Structured output is verifiable | Met | Structured output API and tests cover schema parsing and errors. |
| Text/image declarations match implementation | Mostly met | Catalog checker rejects unsupported modalities; advanced video/audio/image-output facts remain omitted. |
| OAuth files are safe | Met | OAuth storage uses locked atomic writes, hardens existing stores on read, and local POSIX smoke verified `0o700` credential directories and `0o600` store/lock files. POSIX-only lock portability remains tracked as P2. |
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
| Unsupported parameters fail instead of being silently ignored | Met | Capability, structured-output, and option tests cover public failure paths; stable `CallOptions` no longer exposes a generic `provider_options` escape hatch. |
| `complete()` raises typed errors | Met | Streaming/API tests cover terminal error conversion and capability preflight failures as typed `AIError`/`UnsupportedCapabilityError`. |
| Stable error code documented | Met | SDK README and migration guide document `AIError` payload fields and stable codes. |
| Migration guide complete | Met | `docs/en/sdk/migration-v2.md` and `docs/zh-CN/sdk/migration-v2.md`. |

### Tests

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| `make check-ai` passes | Met | Passed on 2026-06-22 with 696 passed and 9 live tests deselected. `test-ai` and `check-ai-coverage` explicitly run `pytest ... -m "not live"` so default AI gates stay offline. |
| `uv run pytest tests -m "not live" -q` passes | Previously met | Passed on 2026-06-22 with provider keys removed: 4260 passed, 9 deselected, before the final-review P1 fix package. It was not rerun after that package. |
| `uv run pytest tests/ai/contracts -q` passes | Met | `tests/ai/contracts/test_core_provider_contracts.py` covers the core adapter protocol and builtin registration contract. |
| `uv run python scripts/ai/check_catalog.py` passes | Met | Catalog gate. |
| `uv run python scripts/ai/check_examples.py` passes | Met | Offline example gate. |
| `uv build` passes | Previously met | Passed on 2026-06-22 before the final-review P1 fix package. It was not rerun after that package. |
| Core coverage >= 90% | Met | `scripts/ai/check_coverage_targets.py` enforces scoped runtime-core coverage; latest `make check-ai` reported 90.10%. Scope is recorded in `ARD-002-ai-coverage-gate-scope.md`. |
| Adapter aggregate coverage >= 85% | Met | `scripts/ai/check_coverage_targets.py` enforces retained provider adapter aggregate coverage; latest `make check-ai` reported 85.84%. Production-adapter-module coverage was 85.39%. |
| No pending asyncio task | Met | Provider runtime, event stream, proxy, and Codex WebSocket tests cover cancellation, close behavior, bounded queues, and terminal preservation. |
| No secret trace snapshot | Met | Error payload redaction and Codex request-body trace summarization are tested; `.artifacts` and `dist` were scanned for current provider environment secret values with no matches. |

### Examples And Docs

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| All offline examples execute | Met | Numbered offline examples are executed by `scripts/ai/check_examples.py`; advanced offline examples are covered by `tests/examples/test_ai_examples.py`. |
| Each key capability has an example | Met | Numbered examples cover complete, stream, typed context, tools, parallel tools, reasoning, structured output, image input, errors/retry, usage, provider matrix, and provider smoke. |
| Main examples use only stable API | Met | `scripts/ai/check_import_boundaries.py`. |
| Advanced examples are marked clearly | Met | Advanced examples live under `examples/ai/advanced`. |
| Chinese and English docs are aligned | Met | SDK README and migration guides exist in both languages with matched section structure, migration topics, examples, advanced boundaries, and live-smoke caveats. |
| Provider matrix and catalog stay aligned | Met | `scripts/ai/check_catalog.py`. |

### Review

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Each AIQ commit has a focused review | Accepted | Per-commit review frequency was intentionally reduced during execution; final owner review covered the assembled branch instead. |
| Each phase has a range review | Accepted | Several phase gates were validated by commands; the final owner review covered the latest assembled branch after follow-up fixes. |
| Final branch has a full review | Met | Final owner review on 2026-06-22 is recorded in `final-owner-review-2026-06-22.md`; it found no P0, fixed several runtime/security/API P1s, and tracks remaining architecture-boundary debt. |
| P0/P1 = 0 | Not met | P0 = 0. Runtime/security/API P1s from final review were fixed, but the provider/base-url compatibility boundary remains a tracked P1 until refactored or accepted by ADR. |
| P2 resolved or tracked | Met | Low-cost docs/example P2s, Codex request-body trace summarization, default Codex HTTP client close ownership, legacy provider fallback removal, provider-declared structured-output mapping, advanced-only provider options, terminal queue edge cases, and the remaining final-review P2s are either fixed or tracked in the final owner review. |

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

One architecture-boundary item remains required before claiming full
execution-plan compliance: remove provider/base-url compatibility heuristics from
shared runtime paths or accept them through an explicit ADR. Optional additional
live provider smoke can be run with valid credentials, but current accepted live
proof only covers DashScope and DeepSeek.
