# 2026-05-11 Component Completion Status

This report closes the current non-UI loushang coding alignment pass against reference coding agent.

## Scope

Counted as gap:

- reference coding agent has the non-UI capability or observable semantic
- loushang coding does not yet provide an equivalent capability or semantic

Not counted as gap:

- UI / interactive TUI behavior
- interaction mode polish such as autocomplete rendering
- method registry / method selection / method injection
- naming style differences
- Python-vs-TypeScript implementation differences
- loushang-only capabilities that go beyond reference implementation
- provider/model configuration divergence, because loushang uses `loushang.ai` Provider -> Endpoint -> Model layering by design

Latest verification for this pass:

- `uv run pytest tests/coding`: 1313 passed
- `uv run ruff check ...`: passed on touched files
- `git diff --check`: passed
- Latest alignment commits:
  - `e78622a feat: harden headless coding surfaces`
  - `c8f6e02 feat: add headless coding alignment surfaces`

## Overall Completion

| Scope | Completion | Gap | Notes |
| --- | ---: | ---: | --- |
| Non-UI / non-interactive / non-method | 98-99% | 1-2% | Main headless runtime, session, store, tools, RPC, extension, diagnostics, policy, compaction, and package paths are usable and regression covered. |
| Strict non-UI including package/security/platform edge cases | 97-98% | 2-3% | Remaining gaps are mostly hardening, stress, and optional trust semantics. |
| Including method | Not scored | Not scored | Method is intentionally deferred. |
| Including TUI / interactive UI | Not scored | Not scored | TUI moved to its own worktree and is outside this pass. |

## Component Snapshot

| Component | Completion | Gap | Status |
| --- | ---: | ---: | --- |
| `bootstrap` | 98% | 2% | Service creation, cwd-bound services, resource/package/extension/settings assembly are complete for headless use. Remaining work is finer startup policy/package diagnostic attribution. |
| `sdk` | 98-99% | 1-2% | Top-level API, smoke coverage, surface snapshot, and compatibility report are present. Remaining work is a versioned baseline / semver contract document. |
| `cli` | 97% | 3% | Non-interactive CLI supports sessions, messages, `@file`, package commands, diagnostics, models, exports, and modes. Remaining work is minor command-combination edge coverage. |
| `mode` / print / RPC | 98% | 2% | Text, JSON, and RPC modes cover event projection, tool rendering, diagnostics, session operations, and headless extension UI state. Remaining work is command matrix edge coverage. |
| `runtime` | 98% | 2% | Session creation, restore, fork, import, switch, index, diagnostics, and lifecycle behavior are covered. Remaining work is rare filesystem and replacement stress. |
| `session` | 98-99% | 1-2% | AgentSession is split into focused controllers. Run, queue, retry, compaction, extension, resource refresh, and diagnostics paths are covered. Remaining work is narrow interleaving stress. |
| `store` | 97-98% | 2-3% | JSONL, index, import/restore, rename/delete, stale index healing, and delayed flush are covered. Remaining work is OS-level permission/race matrix coverage. |
| `message` | 98% | 2% | Session entry, custom message, JSON codec, and projection are stable. Remaining work is richer renderer metadata in downstream consumers. |
| `event` | 98-99% | 1-2% | Session events, JSON projection, tool updates, and diagnostics serialization are stable. Remaining work is more provider-facing schema golden coverage. |
| `tools` | 98-99% | 1-2% | Bash/read/write/edit/grep/find/ls, operations, abort propagation, details schema, external fd/rg, image resize, and render fidelity are covered. Remaining work is rich display polish. |
| `exec` | 98% | 2% | Backend seam, bash operations, interleaved output, and diagnostics are covered. Remaining work is extreme process/PTY stress. |
| `compaction` | 98-99% | 1-2% | Cut points, branch summaries, previous summary update path, quality harness, and fixture evaluation are covered. Remaining work is real model workload tuning. |
| `prompt` | 99% | 1% | System prompt envelope, template args, resource injection, and skill summary behavior are covered. Remaining work is advanced ignore/enablement edge polish. |
| `skill` | 98-99% | 1-2% | Frontmatter, nested discovery, disable-model-invocation, ignore handling, and system prompt projection are covered. Remaining work is advanced resource combination coverage. |
| `loader` / resource | 98-99% | 1-2% | Resource discovery, refresh, collision diagnostics, package roots, and theme diagnostics are covered. Remaining work is deeper theme validation. |
| `extensions` | 97-98% | 2-3% | Hooks, runtime bindings, exec API, lifecycle diagnostics, reload/shutdown behavior, and headless UI state are covered. Remaining work is minor hook edge coverage; TUI consumption is out of scope. |
| `plugin` | 96-98% | 2-4% | Plugin source management, enable/disable, package projection, diagnostics, and package-list behavior are covered. Remaining work is optional trust/signature hardening. |
| `package` | 96-98% | 2-4% | Local/remote lifecycle, Python package source manager, update checks, scope merge, dedupe, and diagnostics are covered. Remaining work is optional security hardening and rare lifecycle stress. |
| `control` / settings | 99% | 1% | Settings breadth, queue modes, tool policy, headless approval, terminal/image/markdown/warning settings are covered. Provider/model divergence is intentional. |
| `policy` | 98% | 2% | Tool policy, approval resolver, package security, and headless settings binding are covered. Remaining work is warning grouping and richer policy projection. |
| `diagnostics` | 98-99% | 1-2% | Summary, query, serialization, runtime/session/package/extension diagnostics are covered. Remaining work is presentation grouping. |
| `platform` | 95-97% | 3-5% | Output guard, footer data provider, git/platform utilities, image/clipboard helpers, and version checks exist. Remaining work is watcher/platform edge hardening. |
| `utils` | 99% | 1% | Thin shared helpers are sufficient for current architecture. |
| `method` | Deferred | Deferred | Deliberately excluded from this pass. |

## Remaining Work Buckets

1. Golden behavior matrix
   - Add a small set of cross-component golden flows:
     - CLI/RPC/SDK -> tool -> policy -> diagnostics -> session store
     - extension exec -> resource refresh -> diagnostics
     - compaction fixture -> summary evaluation -> session continuation

2. Stress / race matrix
   - Focus on:
     - session import/restore filesystem races
     - runtime replacement callback failures
     - extension reload/shutdown interleavings
     - bash abort and interleaved output under load
     - index refresh coalescing under concurrent operations

3. Contract lock
   - Document compatibility boundaries for:
     - SDK surface
     - settings tool policy
     - headless approval resolver
     - extension exec API
     - summary evaluation fixtures

4. Optional hardening
   - Package trust/signature hardening
   - Deeper theme validation
   - Rich static export syntax highlighting
   - Platform watcher edge behavior

## Recommendation

Treat the current non-UI coding MVP as functionally aligned enough for integration use.

Next development should avoid broad feature expansion and focus on:

1. golden behavior fixtures,
2. stress/race tests,
3. compatibility boundary docs,
4. selective hardening only where real usage exposes risk.

