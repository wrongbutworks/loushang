# Harness Workspace Execution Boundary

## Status

Status: accepted for `lane/harness`.

This document defines ownership for bounded workspace output and process
execution. It moves product-neutral execution mechanics into
`loushang.harness.workspace` while preserving the existing
`loushang.coding.exec` and `loushang.coding.tools.truncate` import paths.

## Decision

Harness owns two focused workspace capabilities:

- `loushang.harness.workspace.truncation` owns deterministic line/byte bounded
  text truncation, UTF-8 suffix handling, neutral truncation metadata, and the
  shared baseline limits already used by tools and exec previews.
- `loushang.harness.workspace.exec` owns process request/result records,
  incremental output records, backend/update callback protocols, and the local
  `ExecService` implementation.

Coding remains a product adapter. It owns command risk classification,
approval policy, session cwd resolution, extension semantics, tool result
projection, prompt wording, user-facing notices, and SDK compatibility paths.

## Truncation Split

Move to harness:

- `DEFAULT_MAX_LINES`
- `DEFAULT_MAX_BYTES`
- `TruncationKind`
- `TruncationResult`
- `truncate_head`
- `truncate_tail`
- limit validation, line/byte accounting, and UTF-8-safe suffix helpers

Keep in coding:

- `GREP_MAX_LINE_LENGTH`
- `LineTruncationResult`
- `truncate_line` and its product-facing suffix
- `format_size`
- `truncation_details` and Pi-style detail projection
- camelCase SDK compatibility aliases

`harness.presentation.collapse_text` remains a rendering helper. It adds display
wording and does not replace byte-bounded capture or artifact decisions.

## Execution Split

Move to harness:

- `ExecRequest`
- `ExecOutputChunk`
- `ExecUpdateCallback`
- `ExecResult`
- `ExecBackend`
- `ExecService`
- local subprocess, cancellation, streaming, rolling capture, preview, and
  artifact mechanics

Keep in coding:

- policy evaluation for command content and paths
- relative cwd resolution against a coding session
- extension runtime binding behavior
- bash tool result conversion and notices
- public exports from `loushang.coding` and `loushang.coding.exec`

The request capture fields remain caller-supplied neutral configuration. Their
current defaults are preserved for compatibility; harness does not decide which
commands a product may run.

## Compatibility

Harness-owned classes keep their harness `__module__` and are not exported from
top-level `loushang.harness.__all__`. Coding compatibility modules re-export the
same class and protocol objects so existing imports continue to work:

```python
from loushang.coding import ExecRequest, ExecService
from loushang.coding.tools.truncate import TruncationResult
```

Product-internal code should import the focused harness modules after the owner
move. Compatibility shims exist for public SDK paths, not as duplicate
implementations.

## Dependency Direction

The target direction is:

```text
coding tools / sessions / extensions / policy
  -> loushang.harness.workspace.exec
  -> loushang.harness.workspace.truncation
```

Harness workspace modules must not import coding, TUI, work, method, or AI.
This move does not introduce a neutral execution context and does not by itself
satisfy the neutrality evidence gate for that contract.

## Validation

The migration must prove:

- neutral truncation behavior and UTF-8 byte limits under the harness path;
- exec subprocess, streaming, timeout, cancellation, rolling capture, preview,
  custom backend, and artifact behavior under the harness path;
- coding compatibility imports preserve object identity;
- coding tools, policy, extension, session, and prompt behavior remain intact;
- architecture import boundaries and top-level export discipline still pass.
