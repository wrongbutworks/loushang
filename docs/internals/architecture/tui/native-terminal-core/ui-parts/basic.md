# Basic UI Parts

Basic UI parts are small renderable building blocks used by transcript views,
surfaces, frame regions, extension widgets, and product adapters. They are
generic TUI primitives and must not know coding-session semantics.

## Parts

| UI Part | Purpose |
| --- | --- |
| `Text` | Render multiline text with ANSI-aware wrapping, padding, optional background, and optional theme token. |
| `TruncatedText` | Render the first logical line truncated to the available cell width. |
| `Spacer` | Reserve empty logical rows without terminal writes of its own. |
| `Box` | Compose child renderables with padding and optional background/theme styling. |
| `Rule` / `DynamicBorder` | Render a width-filling divider with an optional label. |
| `Loader` | Render a deterministic spinner/message line from injected time state. |
| `CancellableLoader` | Loader variant that emits an abort intent on normalized abort input. |
| `WorkedDivider` | Render the committed "worked for" divider after a run completes. |

## Render Rules

- Basic parts return `RenderResult`; they never write stdout, move the hardware
  cursor, or clear terminal rows.
- All visible lines must obey cell width constraints after ANSI control
  sequences are ignored.
- Text wrapping and truncation are ANSI-aware and East Asian Width aware.
- ANSI handling must track SGR attributes independently, preserve foreground and
  background colors across soft wraps, close underline at physical line breaks,
  and re-open OSC 8 hyperlinks on continuation lines.
- Explicit newline characters create separate logical lines; soft wraps are
  produced from the current render width.
- Ordinary text-like parts return unpadded logical lines by default. The render
  loop owns stale-row erasure through clear-line operations.
- Width-filling parts such as `Rule`, `DynamicBorder`, status rows, and bordered
  boxes are opt-in full-width parts. When they render inside the bottom frame or
  next to the hardware cursor, they must be autowrap-safe by reserving the final
  terminal cell or by being followed by runtime-managed cursor positioning.
- Empty `Text` and empty `Box` instances render no rows, matching the reference
  container behavior used for optional UI regions.
- `Loader` must be deterministic under test by accepting an injected clock; it
  must not schedule timers or terminal writes itself.
- Animated basic parts expose their next animation frame due time to the runtime
  scheduler. The scheduler requests a timer render when the frame is due, and
  the render loop diff updates only the changed loader line when possible.

## Theme And Cache

- Theme styling is expressed through structured tokens resolved by
  `ThemeResolver`.
- Existing callable style hooks remain supported for migration compatibility,
  but theme tokens are the preferred architecture-level API.
- Theme changes increment resolver version. Cached styled output must include
  the theme version and resolved style signature, so a token update invalidates
  rendered output on the next render pass.
- A theme-only change should flow through the normal line-level diff path in the
  render loop when the changed row is still visible.

## Reference Alignment

| Reference behavior | Loushang behavior |
| --- | --- |
| `Text`, `Box`, `Spacer`, and `TruncatedText` are small components returning line arrays. | Basic UI parts are renderables returning `RenderResult` with logical lines. |
| Components cache output by width/content and expose `invalidate()`. | Basic UI parts cache by width/content/background/theme signature and expose `invalidate()`. |
| Style is often passed as functions from the product theme. | Callable style hooks are supported; structured theme tokens are preferred. |
| Loader updates its text and asks `ui.requestRender()` from an internal interval. | Loader remains pure and reports next frame due time; runtime/scheduler owns timer render requests. |
| Loader and divider lines are ordinary logical lines diffed by the TUI. | Loader, rule, and worked divider render logical lines diffed by `RenderLoop`. |

## Test Obligations

- Render fixtures cover width, padding, wrapping, truncation, ANSI preservation,
  OSC 8 hyperlink wrapping, styled truncation resets, and East Asian Width
  behavior.
- Theme fixtures prove resolved ANSI styling does not change visible width.
- Cache tests prove text/background/theme changes alter output without direct
  terminal writes.
- Render-loop integration proves a Basic theme change produces a line-level
  changed-range update rather than a full repaint.
- Loader scheduler integration proves due animation frames request timer renders,
  stopped or single-frame loaders do not, and frame changes use line-level diff.
