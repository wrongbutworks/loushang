# ARD-002: AI Coverage Gate Scope

## Status

Accepted

## Context

The quality hardening charter requires:

- AI core statement coverage >= 90%.
- Provider adapter aggregate coverage >= 85%.

The package-level `pytest-cov` run also includes CLI entrypoints, contrib
integrations, credential browser flows, live-provider helpers, and optional auth
storage paths. Those paths are important, but they do not have the same release
meaning as the runtime core and retained provider adapters:

- CLI and contrib paths have separate smoke and import-boundary checks.
- Browser/OAuth flows require platform and credential conditions that are not
  stable in the offline release gate.
- Provider adapters have their own aggregate threshold because their SDK event
  mapping risk differs from core model/runtime code.

Without a written scope, the numeric target can drift between "all files under
`src/loushang/ai`" and "runtime core", making the release gate hard to reproduce.

## Decision

`make check-ai` keeps the package-level coverage floor at 80% and adds explicit
target checks from `.artifacts/ai/coverage.xml`:

1. `ai-runtime-core >= 90%`
   - Includes the AI runtime, public API, model/catalog domain, context,
     messages, events, provider runtime/resolution, tools, structured output,
     usage, pricing, trace, and utility modules.
   - Excludes `auth/`, `cli/`, `contrib/`, and `providers/`.
2. `provider-adapters >= 85%`
   - Includes the retained production adapters and their shared helper modules:
     `providers/anthropic.py`, `providers/anthropic_base.py`,
     `providers/openai_completions.py`, `providers/openai_responses.py`,
     `providers/openai_responses_shared.py`, and
     `providers/provider_helpers.py`.
3. `production-adapter-modules >= 85%`
   - Includes only the three retained production adapter modules:
     `providers/anthropic.py`, `providers/openai_completions.py`, and
     `providers/openai_responses.py`.

The package-level 80% floor remains in place to prevent broad regression outside
the scoped targets.

## Rationale

This makes the charter's coverage requirements executable without pretending
that interactive auth, CLI, and contrib code have the same offline test shape as
the runtime core. It also prevents adapter coverage from being hidden inside a
single package-wide percentage.

The coverage gate complements, but does not replace, behavior tests, contract
tests, offline examples, catalog checks, live smoke when credentials are
available, and final review.

## Consequences

Positive:

- The coverage target is reproducible with one command: `make check-ai`.
- Runtime core and adapter coverage can fail independently.
- Package-level coverage remains visible and enforced at 80%.

Negative:

- Auth, CLI, and contrib coverage are not treated as part of the 90% runtime
  core target.
- Final release review still needs to inspect auth/CLI/contrib risk instead of
  relying on the scoped coverage target alone.

## Implementation

- `scripts/ai/check_coverage_targets.py`
- `Makefile` target `check-ai-coverage`
- `tests/ai/test_coverage_targets.py`
