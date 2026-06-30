# Loushang AI Architecture

This directory keeps the current architecture notes for the frozen
`loushang.ai` core. Public usage and API examples live in
[`src/loushang/ai/README.md`](../../../../src/loushang/ai/README.md) and
[`examples/ai`](../../../../examples/ai).

## Active Refactor Inputs

- [AI Refactor Blueprint](./loushang-ai-refactor-blueprint.md)
  is the short entrypoint for the current AI package rebuild structure and
  document reading order.
- [Auth Boundary and Call Credential Design](./loushang-ai-auth-boundary-design.md)
  defines the target boundary for rebuilding auth: `models.json.auth` is the
  default declaration, `CallOptions.auth` is the explicit request-level
  override, and `loushang.ai` resolves the final input into provider request
  auth headers. Upper layers own login, refresh, credential storage, account
  selection, quota, billing, and product-level auth policy.

## Current References

- [ARD List](./ARD-list.md)
- [ARD-001: Async Public Streaming Surface](./ARD-001-async-public-streaming-surface.md)
- [ARD-002: AI Coverage Gate Scope](./ARD-002-ai-coverage-gate-scope.md)
- [ARD-003: AI Core Freeze Contract](./ARD-003-core-freeze-contract.md)
- [Core Freeze Verification](./core-freeze-verification.md)
- [Core Freeze Target Checklist](./core-freeze-target-checklist.md)
- [Core Provider Adapter Contract Matrix](./core-provider-adapter-contract-matrix.md)
- [Trace Events](./loushang-ai-trace-events.md)

## Current Code Domains

- `src/loushang/ai/api/`
- `src/loushang/ai/model/`
- `src/loushang/ai/provider/`
- `src/loushang/ai/auth/`
- `src/loushang/ai/event_stream/`
- `src/loushang/ai/tool/`
- `src/loushang/ai/providers/`
- `src/loushang/ai/contrib/`
- `src/loushang/ai/messages.py`
- `src/loushang/ai/context.py`
- `src/loushang/ai/pricing.py`
- `src/loushang/ai/usage.py`

## Core Boundaries

- `model/` owns domain objects, model-file loading, and registry lookup.
- `api/` owns public `complete`, `stream`, and `complete_structured`.
- `provider/` owns `ProviderRequest`, request resolution, invocation guards,
  retry, cancellation, and provider request validation.
- `providers/` owns the three core protocol adapters:
  `openai-completions`, `openai-responses`, and `anthropic-messages`.
- `contrib/` is limited to explicitly registered, non-default
  provider-specific adapter/catalog integrations such as OpenAI Codex. It must
  not carry OAuth lifecycle, quota, billing, account control-plane, or product
  auth policy back into `loushang.ai` core.
- `usage.py` owns response usage payload helpers only; account or platform quota
  is outside core usage.

Historical design drafts and reference surveys may exist elsewhere under
`docs/internals`, but this index intentionally points only at the current frozen
core contract.
