# KD-007: Resize-Stable Reflow

## Purpose

Make resize behavior a first-class stability constraint, not an incidental
terminal event handler.

## Design

On terminal resize, the runtime invalidates layout and recomputes current logical
lines from the screen root with the new constraints. Reflow covers soft wraps,
region heights, overlay geometry, cursor marker mapping, status truncation, and
pending queue visibility.

Width changes invalidate line wrapping and should normally use full recompose
plus resize repaint. Height changes invalidate viewport anchoring and should
normally use full recompose plus resize repaint unless the runtime can prove a
smaller line-level diff is equally stable.

Resize repaint rewrites runtime-managed visible UI. Default resize repaint uses
clear scrollback to rebuild row mappings deterministically. Clear
scrollback remains policy-controlled and may be disabled for history-preserving
deployments.

## Repaint Decision

The default resize policy is:

- width change: full recompose plus resize repaint
- height change: full recompose plus resize repaint
- content shrink below the working high-water mark: line-level clear when safe,
  otherwise resize/recovery repaint
- content shrink that would move the natural viewport above the previous
  viewport anchor: recovery repaint of the managed viewport, without clearing
  scrollback, so bottom-frame rows do not leave stale prompt/status ghosts
- clear scrollback: on for resize repaint by default, policy-disabled when
  history preservation is preferred

The runtime may use line-level differential rendering after resize only when all
of the following are true:

- current logical lines have been recomputed from the new constraints
- previous rendered rows can still be mapped to physical terminal rows
- the changed line range is inside the visible managed viewport or can be reached
  by append update
- no user scrollback movement or external stdout write has invalidated row
  mapping
- stale rows left by shrink can be cleared without touching unmanaged history

After width reflow, many later logical lines may shift even if their text did not
change. The render loop still treats diffing as line-level: it computes the
changed line range after reflow and either updates visible changed rows or uses
resize repaint. It does not attempt to patch shifted rows with character-level
edits.

## Clear-On-Shrink

Clear-on-shrink is a configurable stability policy. When enabled, shrinking
content below the working area high-water mark may trigger resize/recovery
repaint to avoid stale rows. It still must not imply clear scrollback.

## Test Obligations

- resize during streaming does not duplicate assistant records
- long composer text remains editable after width shrink and expand
- status remains a single bottom row after resize
- cursor marker maps to the correct hardware cursor cell after reflow
- width and height changes default to resize repaint
- clear scrollback is emitted by default resize repaint and can be policy-disabled
- repaint kind is reported in render diagnostics with a reason
- width reflow uses line-level changed ranges or resize repaint, never stale row
  mapping
