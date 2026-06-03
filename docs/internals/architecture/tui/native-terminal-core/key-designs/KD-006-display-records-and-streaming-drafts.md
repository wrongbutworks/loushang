# KD-006: Display Records And Streaming Drafts

## Purpose

Keep transcript rendering deterministic while assistant output, tool output, and
thinking content update over time.

## Design

Product adapters convert product events into display records. Display records are
data. Renderers convert them into UI parts or logical lines. The runtime diff
loop only sees logical lines.

The generic TUI core owns the display record family definitions and lifecycle
rules. Product adapters own projection from product-specific events into concrete
record instances. Coding-specific event names, tool policies, model names, and
diagnostics do not become generic TUI core concepts.

Streaming assistant output is a draft record until the product adapter marks it
stable. Tool execution updates mutate one tool execution record through running,
completed, failed, cancelled, and truncated states. Thinking blocks render only
when supplied by product data and according to thinking visibility policy.

Commit turns a draft record into stable transcript content. After commit,
transient UI must not mutate that block.

When a submitted idle composer draft becomes a new user prompt record, the
product adapter must let the runtime render the composer-cleared transient frame
before appending the user prompt record. Without that handoff, the previous live
composer row can be pushed into terminal scrollback and visually duplicate the
newly committed user prompt.

## Test Obligations

- token chunks update one draft record rather than appending records
- submitted composer text clears from transient UI before becoming a transcript
  record
- completion commits one assistant message block
- tool elapsed/took markers update the tool execution record, not the run
  worked divider
- thinking visibility never invents hidden reasoning
- concise errors do not dump traceback unless verbose diagnostics are enabled
