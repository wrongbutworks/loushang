# KD-002: Input Event Routing

## Purpose

Define how terminal input becomes product intents without leaking raw key events
through the whole system.

## Design

InputReader converts terminal bytes, paste markers, resize events, focus events,
mouse events, and signals into normalized input events. The runtime routes input
in this order:

1. lifecycle and emergency terminal restoration
2. active overlay or surface with focus capture
3. focused renderable, normally the composer
4. product adapter command routing
5. global keybindings

The generic prompt route uses a `PromptInputTarget` boundary. `InputRouter`
owns routing priority and prompt intents, while concrete editors provide
operations through target adapters such as `ComposerInputTarget`. Product
adapters may reuse target helper functions, but they keep their own routing
order when product semantics differ.

Keybindings are configuration-owned by the runtime or product adapter. The
coding product adapter loads configured keybindings from settings and passes
them into the native input router. UI parts may handle routed events, but they
should return semantic intents such as submit, move selection, close surface,
approval decision, abort, change model, or open command surface.

## Capability Detection And Startup Handshake

The runtime performs terminal capability detection during startup before normal
input routing begins. Capability queries may temporarily intercept terminal
responses needed to detect keyboard protocol, bracketed paste, focus events,
cell size, image protocol support, synchronized output, or color depth.

During the handshake, ordinary user input must either be buffered as normalized
events for later routing or ignored only when it is unambiguously part of a
terminal query response. Query handling must complete or time out quickly enough
that startup does not block interactive input indefinitely.

## Paste And IME

Bracketed paste is enabled when supported. Paste text is delivered as paste
input, not as a sequence of ordinary keys. Pasted newlines insert explicit
newlines into the composer buffer and do not submit the prompt.

Paste handling must neutralize terminal control sequences before they can be
written back to the terminal. The product policy decides whether such content is
inserted as inert text, escaped for display, filtered, or rejected with a concise
error.

Some terminal hosts can encode control bytes inside bracketed paste as CSI-u
Ctrl+letter sequences. The paste path should decode those sequences before
control filtering so pasted newlines and tabs remain literal content instead of
leaking CSI-u tails into the editor.

Large pasted content may be represented by paste markers, including either many
lines or a long single line. Paste markers are logical editor atoms for cursor
movement and deletion while preserving the full payload for submission and undo.
Path-like paste that starts with `/`, `~`, or `.` may insert a leading space
when pasted after a word character, so dragged or copied file paths do not
visually merge with the preceding command text.

Focused renderables declare cursor position with cursor markers so the runtime
can place the hardware cursor for IME candidate windows.

## Editor State Model

The composer should provide terminal-native editor primitives while keeping them behind
normalized input events:

- soft wrap is visual only and does not mutate the editor buffer
- explicit newline is an editor buffer character produced by a configured
  keybinding
- undo stack groups semantic edit operations such as paste, delete word, kill
  line, and completion apply
- kill ring stores cut text for yank/yank-pop without creating transcript
  records
- character jump is a transient router mode: the jump key enters forward or
  backward search, and the next printable text event moves the composer cursor
  to that character without inserting text
- resize events update the router's current render width before subsequent
  visual cursor movement, so up/down navigation follows the same wrapping as the
  rendered composer
- paste marker is an editor atom that may stand in for a large payload while the
  full payload remains available for submission

These editor primitives are local to the focused prompt target until the product
adapter receives a submit, steer, or follow-up intent.

## Test Obligations

- active surfaces receive Esc before run abort handling
- paste newlines do not accidentally submit prompts
- paste control sequences are not executed
- CSI-u Ctrl+letter encodings inside bracketed paste become literal paste text
- large paste markers behave atomically for cursor movement and deletion
- long single-line paste can be collapsed into a paste marker
- path-like paste after a word character inserts one readability space
- undo stack and kill ring operations do not create transcript records before
  submit
- capability query responses do not leak as prompt text
- composer cursor mapping remains correct after wrapping
- resize signals trigger render invalidation, not prompt submission
