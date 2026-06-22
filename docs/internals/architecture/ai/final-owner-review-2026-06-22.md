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

- `make check-ai` passed on 2026-06-22 with 696 passed and 9 live tests
  deselected.
- The same run reported total coverage 83.62%, AI runtime-core coverage 90.10%,
  provider-adapter coverage 85.84%, and production-adapter-module coverage
  85.39%.
- Targeted non-AI validation also covered proxy cancellation:
  `uv run pytest tests/agent/test_proxy.py::test_stream_proxy_consumer_close_cancels_proxy_task -q`.
- The full offline suite and package build passed earlier on 2026-06-22. They
  were not rerun after the final P1 fix package to keep the closeout focused.

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

## Remaining P1 Boundary Debt

The branch should not claim full architecture-boundary completion yet. Runtime
compatibility code still contains provider/base-url heuristics and
provider-specific branches that need either a narrower endpoint-contract owner or
an explicit ADR accepting the compatibility layer.

This is intentionally tracked instead of being forced into the final fix package;
it is broader than the low-risk closeout work and would need its own focused
review.

## P2 Items Tracked

- Explicit OAuth credentials still persist by default unless callers override
  the option.
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

Local gates are closed for this final-review fix package. Do not tag or announce
the branch as fully compliant with the execution-plan architecture checklist
until the remaining provider/base-url compatibility boundary is either removed or
explicitly accepted by design.
