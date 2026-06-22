# AI Package TODO

## Remaining Issues

- Provider/model support follow-up after `issue-add-model`.
  Current branch has added catalog coverage, colon-to-underscore model ID mapping,
  Cloudflare baseUrl template expansion, Azure OpenAI Responses support, and a
  lightweight Bedrock Converse adapter. Remaining work:
  1. Run live provider verification with real credentials for:
     - OpenRouter colon-normalized models, e.g. `openai/gpt-oss-120b_free`
     - Azure OpenAI Responses
     - Cloudflare AI Gateway and Workers AI
     - Mistral OpenAI-compatible endpoint
     - Google Gemini OpenAI-compatible endpoint
     - Google Vertex OpenAI-compatible endpoint
     - Amazon Bedrock Converse
  2. Complete Bedrock support beyond the current lightweight adapter:
     - real Bedrock streaming event-stream support
     - tool use mapping
     - image input payload mapping
     - Claude thinking/cache/interleaved-thinking compatibility
     - richer stop reason and usage mapping
  3. Improve Google Vertex auth:
     - support ADC or service-account based token acquisition
     - keep explicit `GOOGLE_VERTEX_ACCESS_TOKEN` as the simple override path
  4. Add dedicated CLI flags for provider-specific options where useful:
     - Azure base URL / API version / deployment name
     - Vertex project / location / token source
     - Bedrock region / profile or credential source
  5. Run full repository verification before PR finalization:
     - `uv run pytest tests -q`
     - keep `make check-ai` as the required AI gate
  6. Decide whether provider live tests should be checked in as skipped-by-default
     vendor verification tests, or kept as documented manual verification steps.

- Review follow-up: focus on correcting `loushang.ai` core capability design as a general-purpose AI access package.
  Current scope: prioritize core `ai` package design (`model/`, `auth/`, `api/`, `providers/`, `messages.py`, `context.py`, `event_stream/`, `types.py`, `options.py`).
  Out of primary scope for now: CLI, examples, and tests as external or simulated consumers, except where they have already polluted core package boundaries.
  Priority order:
  1. Done: align builtin auth provider lifecycle so `reset_oauth_providers(with_builtins=True)` restores the same builtin providers as `register_builtin_oauth_providers()`.
  2. Audit and isolate consumer-specific logic that has leaked into core `auth/` and `providers/` layers.
     Partial:
     - Anthropic OAuth requests no longer identify as `claude-cli`; core provider now uses neutral SDK identity headers.
     - Codex CLI local auth-state parsing moved out of core `auth/` into `cli/` helper scope.
     - Anthropic OAuth-specific tool/header compatibility moved out of the generic provider base surface into a dedicated helper module.
  3. Make normalized context the single source of truth between public API and provider adapters; remove duplicate normalize/fallback behavior.
     Partial:
     - Normalized context is now an immutable `NormalizedContext` snapshot; marker dicts are no longer trusted as normalized output.
     - Core providers no longer each own their own normalize path; they consume normalized context or explicitly coerce through the shared helper.
     - `openai_responses` no longer falls back to raw `context["tools"]` after normalization.
  4. Done: make tool-call/tool-result pairing strict by default, with explicit repair as the compatibility mode.
     - Synthetic missing-tool-result content and assistant bridge text now come from shared transform-layer constants instead of scattered provider-local strings.
     - Synthetic tool results are now explicitly marked in `ToolResultMessage.details` with `{"synthetic": true, "reason": "missing_tool_result"}`.
     - Pairing strategy is now a public option (`StreamOptions.pairing_mode`) and propagates through API/provider normalization paths.
     - `ModelCallOptions.pairing_mode` defaults to `strict`; callers must explicitly pass `repair` for legacy transcript repair diagnostics.
  5. Simplify event stream assembly so content ordering/indexing is derived from real content, not hidden assembler layout assumptions.
     Partial:
     - `RawAssembler` no longer forces an empty leading text part for thinking-only or toolcall-only streams.
     - `content_index` for thinking/toolcall events is now derived from real assembled content shape instead of fixed slot assumptions like `thinking == 1`.
  6. Reduce magic-string compatibility/config behavior in `models.json` and provider implementations.
  7. Done: narrow the public API surface so advanced/internal helpers are not exported as if they were primary entry points.
  8. Strengthen typed boundaries for options, protocol objects, and provider adapter inputs.
  9. Evaluate whether `models.json` should remain a package-internal fact source for pricing/defaults/compat metadata or be split by responsibility over time.

- Initialize the default API provider registry more explicitly.
  Right now the top-level provider registry starts empty, so callers must invoke
  `reset_api_providers()` or `register_api_provider(...)` before `get_api_provider(...)`
  is useful.

- Normalize indentation and style in a few files.
  Some modules still use tabs instead of the prevailing project style.

- Unify usage/cost observability semantics across providers.
  The response-level usage (`input/output/cache_*`) and platform quota endpoint (`/usages`)
  are currently mixed in example-level scripts; standardize this inside `loushang.ai`:
  define a single usage payload contract, include provider-specific quota-query support
  (e.g., Kimi `/v1/usages` path), and expose it via a stable API for callers.
  Do not change endpoint catalog files yet; keep this as a design task in `loushang.ai`
  first, then decide whether endpoint metadata should own quota-query descriptors.

### Example context for Kimi

- Current examples to validate (`examples/coding`):
  - `22_usage_inspect.py`: demonstrates response-level usage/cost extraction.
  - `23_kimi_weekly_usage_ledger.py`: writes local weekly ledger and currently queries `/usages` for platform quota.
  - `21_switch_model_route.py`: validates endpoint/model routing behavior.
  - `17_kimi_env_probe.py`: environment/catalog/key-surface checks.
- Expected core behavior after fixing:
  - `loushang.ai` should expose two distinct payload types:
    - `usage_observation`: response usage fields from model call (`input/output/cache_*`).
    - `platform_quota`: account-level quota/remaining/reset data from provider quota endpoint.
    - Examples should consume the standardized contracts instead of URL-specific script-level logic.

- Design note (deferred):
  - Evaluate whether to model platform quota as an endpoint capability in catalog (similar to docs metadata).
  - If adopted, define a dedicated `usage_query` capability section in endpoint metadata
    first (optional, non-breaking), and update callers to use that abstraction later.

### Endpoint metadata design (Kimi /coding case) -- to be done in loushang.ai only first

- Observation:
  - `https://api.kimi.com/coding/v1/usages` is an account-level query endpoint.
  - It is endpoint-scoped rather than model-scoped, and likely shared by multiple models under same endpoint.
  - 现网脚本现在通过硬编码 `/v1/usages` 兜底探测，属于示例层耦合。

- Proposed endpoint-level schema sketch (deferred):
  - Add optional endpoint capability metadata, but keep behavior backward-compatible:
    - `supportsUsageQuery: true/false`
    - `usageQuery: { path: "/v1/usages", method: "GET", authMode: "bearer_or_x_api_key", responseKind: "platform_quota" }`
    - `usageQuery.path` can be absolute URL when endpoint host differs.
  - `loushang.ai` exposes a stable accessor, examples consume via API call only.
  - Example migration sequence:
    1) add abstraction in core (`loushang.ai`) for platform_quota
    2) add Kimi mapping in core/provider layer
    3) keep catalogs unchanged until step 3
    4) optional: surface `usage_query` in catalog metadata and remove special-case script logic

- Acceptance criteria for this TODO:
  - 一个调用同时可拿到两类口径：
    - `usage_observation`（响应 usage）
    - `platform_quota`（账户额度）
  - 不再在示例层硬编码 `/usages` 路径。
  - 控制台对齐（`limit/used/remaining/resetTime`）与模型响应 usage 在文档中明确区分且有字段来源。
