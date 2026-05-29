# ARD-003: Resize Repaint And History Policy

## Status

Accepted for the native terminal core draft.

## Context

The reference TUI is visually stable during resize because it treats width and
height changes as full-render events. It rebuilds the current logical lines and
repaints the visible UI instead of trying to preserve stale row mappings through
complex incremental patches.

Earlier loushang drafts emphasized terminal history preservation too strongly.
That risks making resize behavior fragile: soft wraps change, overlay geometry
changes, cursor rows move, and the bottom frame can shift while streaming.

## Decision

Prefer deterministic visual stability for resize:

- width and height changes trigger full recompose of current logical lines
- resize normally uses resize repaint of runtime-managed visible UI
- line-level diff after resize is allowed only when it is demonstrably as stable
  as resize repaint
- clear scrollback is part of the default resize repaint path
- clear scrollback remains policy-controlled and may be disabled for deployments
  that prioritize preserving shell history

The default product tradeoff is:

1. steady-state streaming uses line-level diff and append update
2. resize prioritizes full recompose plus deterministic resize repaint, including
   clear scrollback by default
3. unsafe viewport transitions use recovery repaint or another safe re-anchor
   path
4. terminal scrollback clearing outside resize remains disabled unless explicit
   user policy enables it

## Consequences

- The implementation can avoid fragile resize diff logic and still keep the
  steady-state line-level diff loop.
- Terminal history preservation becomes best effort, not the primary resize
  invariant.
- Tests must distinguish resize clear scrollback from steady-state and recovery
  clear scrollback.
- Render diagnostics must expose repaint kind and clear-scrollback policy.

## Rejected Alternatives

### Safe Diff First On Resize

Rejected because width and height changes often invalidate logical-to-physical
row mapping. A safe-diff-first policy can reintroduce duplicated transcript
blocks, stale rows, and cursor displacement.

### Never Clear Scrollback By Default

Rejected because it keeps resize too fragile for the deterministic stability
target.
History-preserving resize remains available as an explicit policy, but the
default favors deterministic resize behavior.
