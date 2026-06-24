# Loushang AI Final Owner Review - 2026-06-22

Scope: branch `ai/quality-hardening-v2` against the AI quality-hardening
execution plan sections 22-24.

This review intentionally closes the assembled branch instead of reviewing every
small patch independently. The review frequency was reduced during final
execution so the remaining work could move faster without losing the owner-level
quality check.

## Review Method

- Stable API and architecture boundaries.
- Message, context, and tool-result normalization.
- Error semantics, retry behavior, streaming, and cancellation.
- Credential security and auth resolution behavior.
- Provider adapter consistency.

Catalog and examples were covered by local gates and scorecard inspection rather
than another broad manual pass.

## Validation After Final Fixes

- `make check-ai` passed on 2026-06-22 with 708 passed and 9 live tests
  deselected.
- The same run reported total coverage 83.55%, AI runtime-core coverage 90.00%,
  provider-adapter coverage 85.84%, and production-adapter-module coverage
  85.39%.
- Targeted and broad non-AI validation covered proxy, auth, and advanced
  examples:
  `uv run ruff check examples/ai/advanced src/loushang/agent/proxy.py tests/agent/test_proxy.py tests/auth tests/examples/test_ai_examples.py`
  and `env -u <provider keys> UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests -m "not live" -q`.
- The full offline suite passed with 4284 passed and 9 live tests deselected.
- `UV_CACHE_DIR=/tmp/uv-cache uv build` passed and produced both sdist and
  wheel artifacts.
- Live smoke passed for DashScope Responses stream/tools and DeepSeek
  OpenAI-compatible complete/stream examples. Moonshot OpenAI complete/stream
  were attempted but skipped because the provider rejected the configured
  credential.

## P0 Findings

None found.

## P1 Findings Fixed In This Package

- OAuth refresh/load failures no longer fall through to lower-priority
  credentials.
- Existing OAuth credential-store files are hardened on read before parsing.
- OpenAI Responses function-call argument deltas resolve the same composite tool
  call id used by start/done events.
- `NormalizedContext` no longer accepts arbitrary `Mapping` messages after the
  public normalization boundary; custom mappings are canonicalized first.
- Strict tool-result pairing errors now carry stable diagnostic codes and
  locations.
- Capability preflight failures and unsupported structured-output mappings raise
  typed `UnsupportedCapabilityError` instead of plain `ValueError`.
- `EventStream.aclose()` now cancels and awaits the attached producer task before
  returning.
- `stream_proxy()` attaches its producer task to the returned stream so consumer
  close cancels the producer.
- OpenAI Codex WebSocket cancellation closes and evicts the in-flight cached
  socket instead of returning it to the cache.
- Stable `CallOptions` no longer exposes a generic `provider_options` escape
  hatch.
- Runtime provider/base-url compatibility guessing was removed from shared
  compat resolution; runtime request resolution now consumes typed
  protocol/dialect/transport/routing facts.
- Schema v2 custom OpenAI-compatible endpoints with a concrete `baseUrl` or
  `baseUrlEnv` now fail at loader time unless they declare `protocol` or
  `dialect`.
- Explicit unsupported `cache_retention` and `session_id` requests now fail with
  typed `UnsupportedCapabilityError` instead of being silently dropped.
- Ambiguous provider routing request overrides now fail instead of being routed
  by provider or base-url identity.
- Trace redaction now covers token, OAuth, credential, and credentials keys while
  preserving non-secret usage fields such as `total_tokens`.
- Empty OAuth access-token entries no longer block fallback credentials, and
  explicit OAuth credentials no longer persist by default.
- `EventStream.result()` now waits for producer cleanup after terminal events.
- `stream_proxy()` abort signals now cancel blocked SSE reads and emit an
  aborted terminal error.

## P1 Closure

No P0/P1 findings remain after the final fix package and local review. The only
remaining live-provider caveat is evidence scope: Tencent Hunyuan, Z.AI,
MiniMax, Volcano Ark, Baidu Qianfan, and StepFun were not live-smoked on this
machine because their matching environment variables were not present.

## P2 Items Tracked

- Credential file locking remains POSIX-oriented.
- Provider-side tool-result repair is narrower than the public normalization
  repair path.
- Some parallel-tool examples and docs can still overstate provider interleaving
  behavior.
- Codex contrib behavior is still visible to CLI/core integration points.
- Legacy adapter entrypoints, raw-part typing strictness, Bedrock overflow regex
  matching, root namespace leakage, raw pre-visible buffering, and retry trace
  request context need follow-up hardening.

## Recommendation

Local gates are closed for this final-review fix package. The branch can be
pushed after the final local commit, but release notes should not claim live
provider proof beyond the providers listed in the scorecard.
