# Loushang AI Final Scorecard

Last updated: 2026-06-23.

This scorecard records the current release readiness of the AI quality hardening
branch against the execution plan in
[`2026-06-20-loushang-ai-quality-hardening-execution-plan.md`](../../plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md).
It is an owner-level status document, not a replacement for the final review.

## Release Recommendation

Do not tag a release that claims broader live-provider coverage than the
evidence below. Local code, architecture, example, build, and offline test gates
are closed for the final-review fix package.

The branch has reached the intended SDK shape: a curated catalog, narrow root
API, protocol-level core adapters, explicit endpoint contracts, explicit contrib
boundaries, normalized errors, executable offline examples, and local AI quality
gates. Runtime provider/base-url compatibility guessing has been removed from
shared compatibility resolution; custom schema v2 OpenAI-compatible endpoints
with a concrete `baseUrl` or `baseUrlEnv` must now declare typed `protocol` or
`dialect` contract facts.

## Objective Score

| Dimension | Target | Current | Status |
|---|---:|---:|---|
| Architecture boundaries | 9.0 | 9.0 | Met |
| Stable API consistency | 8.5 | 8.7 | Met |
| Message and tool normalization | 9.0 | 8.9 | Mostly met |
| Compat and endpoint contract | 9.0 | 9.0 | Met |
| Error and reliability semantics | 8.5 | 8.5 | Met |
| Streaming and cancellation | 8.5 | 8.6 | Met |
| Provider consistency | 8.5 | 8.5 | Met |
| Auth security | 8.0 | 8.1 | Met |
| Model catalog governance | 9.0 | 9.0 | Met |
| Tests, examples, and docs | 9.0 | 9.0 | Met |

Current composite score: 8.8/10.

## Evidence Summary

| Area | Current evidence |
|---|---|
| Root API surface | `tests/ai/test_options.py` verifies root exports stay narrow and provider-specific options remain outside `loushang.ai.__all__`. |
| Catalog budget | `scripts/ai/check_catalog.py` enforces provider <= 11, model <= 20, evidence files, provider matrix alignment, preferred-endpoint uniqueness, and supported modalities. |
| Curated provider facts | `docs/internals/architecture/ai/catalog-evidence/*.md` records official docs, included models, omitted facts, and live-smoke status for each curated provider. |
| Legacy catalog backup | `backup/ai/README.md` records the compressed legacy catalog backup and SHA verification command. |
| Provider boundary | `ProviderRequest` is the single `invoke_raw` argument for registered raw providers; contract tests lock the signature, builtin registration, and legacy-signature rejection. |
| Structured output mapping | `tests/ai/test_structured_output.py` verifies structured-output requests are accepted only when the selected provider adapter declares mapping support, not by a core hard-coded API allowlist. |
| Public SDK docs | `docs/en/sdk/README.md`, `docs/zh-CN/sdk/README.md`, and the v2 migration guides document the public path, catalog, auth, errors, examples, and migration rules. |
| Offline examples | `scripts/ai/check_examples.py` executes numbered `examples/ai/[0-9][0-9]_*.py` with live provider keys removed. |
| Import boundaries | `scripts/ai/check_import_boundaries.py` prevents `loushang.ai` from importing agent/coding layers, prevents removed core providers from returning, and keeps top-level examples on stable AI imports. |
| AI gate | `make check-ai` runs lint, mypy, catalog checks, import checks, offline examples, package coverage, scoped core coverage, and adapter coverage; latest run reached 83.56% package coverage, 90.13% runtime-core coverage, 85.74% provider-adapter coverage, and 85.28% production-adapter-module coverage with 726 passed and 9 live tests deselected. |
| Full test suite | `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -q` passed on 2026-06-23 with 4312 passed and 6 skipped. |
| Build | `UV_CACHE_DIR=/tmp/uv-cache uv build` passed on 2026-06-23 and produced both sdist and wheel artifacts. |
| Live provider smoke | DashScope Responses stream/tools passed with 2 tests. DeepSeek OpenAI-compatible complete/stream examples passed. Moonshot OpenAI complete/stream were attempted and skipped because the provider rejected the configured credential, so Moonshot is not counted as live proof. |

## Final Checklist Status

### Code

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Core only has three protocol adapters | Met | `core-provider-adapter-contract-matrix.md`; `loushang.ai.bootstrap.register_builtin_ai_providers`. |
| Bedrock/Azure not in core | Met | `scripts/ai/check_import_boundaries.py` blocks removed core provider modules. |
| Codex is contrib and explicitly registered | Met | `loushang.ai.contrib.openai_codex.register_openai_codex_contrib`. |
| Core has no provider-id/base-url compat guessing | Met | `compat_schema.py` compatibility resolution no longer accepts provider/base-url identity inputs; request resolution consumes typed protocol/dialect/transport/routing facts. Schema v2 custom OpenAI-compatible endpoints with `baseUrl` or `baseUrlEnv` must declare `protocol` or `dialect`. |
| Built-in catalog has no legacy full-catalog runtime path | Met | Package data points to `models.json`; the full legacy catalog is kept under `backup/ai/` only. |
| Provider boundary accepts only normalized context/request facts | Met | Registered raw providers receive one `ProviderRequest` object containing `model`, normalized `context`, `options`, and resolved request facts; old positional provider signatures are rejected. |
| Core has no bare `except Exception: pass` | Met | `rg -n -U "except Exception:\n\s*pass" src/loushang/ai tests/ai tests/providers` returns no matches. |
| Stream queue is bounded | Met | `AssistantMessageEventStream` uses a bounded queue; provider runtime tests cover backpressure and event stream tests cover full-queue terminal preservation. |
| Cancellation closes upstream | Met | Provider runtime and event streams close async sources through `aclose`/`close`; targeted tests cover consumer-close cancellation and producer cleanup. |
| Parallel tool calls can interleave | Met | Tool and provider tests cover multi-tool event assembly and parallel tool examples. |
| Structured output is verifiable | Met | Structured output API and tests cover schema parsing and errors. |
| Text/image declarations match implementation | Met | Catalog checker rejects unsupported modalities; advanced video/audio/image-output facts remain omitted instead of being declared without implementation support. |
| OAuth files are safe | Met | OAuth storage uses locked atomic writes, hardens existing stores on read, and local POSIX smoke verified `0o700` credential directories and `0o600` store/lock files. POSIX-only lock portability remains tracked as P2. |
| Unknown pricing is not zero cost | Met | Pricing and assembler tests preserve unknown cost as `None`. |

### Catalog

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| Original catalog archived and SHA-verifiable | Met | `backup/ai/README.md`. |
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
| Root invocation semantics are clear | Met | SDK docs and option tests document `stream` / `complete` with `CallOptions`; simple APIs are intentionally removed from the root public surface. |
| Unsupported parameters fail instead of being silently ignored | Met | Capability, structured-output, and option tests cover public failure paths; stable `CallOptions` no longer exposes a generic `provider_options` escape hatch. |
| `complete()` raises typed errors | Met | Streaming/API tests cover terminal error conversion and capability preflight failures as typed `AIError`/`UnsupportedCapabilityError`. |
| Stable error code documented | Met | SDK README and migration guide document `AIError` payload fields and stable codes. |
| Migration guide complete | Met | `docs/en/sdk/migration-v2.md` and `docs/zh-CN/sdk/migration-v2.md`. |

### Tests

| Requirement | Status | Evidence or remaining work |
|---|---|---|
| `make check-ai` passes | Met | Passed on 2026-06-23 with 726 passed and 9 live tests deselected. `test-ai` and `check-ai-coverage` explicitly run `pytest ... -m "not live"` so default AI gates stay offline. |
| `uv run pytest tests -q` passes | Met | Passed on 2026-06-23: 4312 passed, 6 skipped. |
| `uv run pytest tests/ai/contracts -q` passes | Met | `tests/ai/contracts/test_core_provider_contracts.py` covers the core adapter protocol and builtin registration contract. |
| `uv run python scripts/ai/check_catalog.py` passes | Met | Catalog gate. |
| `uv run python scripts/ai/check_examples.py` passes | Met | Offline example gate. |
| `uv build` passes | Met | Passed on 2026-06-23 and produced `dist/loushang-0.1.0.tar.gz` and `dist/loushang-0.1.0-py3-none-any.whl`. |
| Core coverage >= 90% | Met | `scripts/ai/check_coverage_targets.py` enforces scoped runtime-core coverage; latest `make check-ai` reported 90.13%. Scope is recorded in `ARD-002-ai-coverage-gate-scope.md`. |
| Adapter aggregate coverage >= 85% | Met | `scripts/ai/check_coverage_targets.py` enforces retained provider adapter aggregate coverage; latest `make check-ai` reported 85.74%. Production-adapter-module coverage was 85.28%. |
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
| Final branch has a full review | Met | Final owner review on 2026-06-22 is recorded in `final-owner-review-2026-06-22.md`; it found no P0, fixed runtime/security/API/architecture P1s, and records remaining non-blocking caveats. |
| P0/P1 = 0 | Met | P0 = 0 and P1 = 0 after the final fix package and local review. |
| P2 resolved or tracked | Met | Low-cost docs/example P2s, Codex request-body trace summarization, default Codex HTTP client close ownership, legacy provider fallback removal, provider-declared structured-output mapping, advanced-only provider options, terminal queue edge cases, and remaining portability/follow-up items are either fixed or tracked in the final owner review. |

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
contract checks. DeepSeek has current valid live proof. Tencent Hunyuan, Z.AI,
MiniMax, Volcano Ark, Baidu Qianfan, and StepFun were not live-smoked on this
machine because the matching environment variables were not present; live proof
is not claimed for those providers.

## Residual Notes

No P0/P1 code or architecture findings remain from the final owner review.
Optional additional live provider smoke can be run when valid Tencent Hunyuan,
Z.AI, MiniMax, Volcano Ark, Baidu Qianfan, or StepFun credentials are available.
Current accepted live proof covers DashScope and DeepSeek only.
