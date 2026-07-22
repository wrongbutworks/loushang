# CLI Product Host Collapse

## Boundary

Product CLI argument grammar, product startup policy, Method/Work bindings, and
product wording remain product-owned. Harness owns reusable CLI operations over
injected session and settings capabilities. Channel continues to own stream
binding, stdout protection, turn ordering, and disposal through
`ProductHostLifecycle`.

This slice extends the existing `loushang.harness.cli` runtime. It does not add
a second CLI parser, transport, session runtime, or product host.

## Shared Contracts

- `CliOperationSequence` executes product-selected operations in declared order
  and returns on the first handled exit code.
- `CliOperationStage` binds a stable operation id to a synchronous or
  asynchronous handler. Products can add, remove, or reorder stages without
  changing Harness.
- `CliLaunchPlan` normalizes TTY selection, structured-output protection,
  session-restore conflicts, Work/Method/Channel compatibility, and
  observability mode without receiving a Product argument object.
- `harness.cli.host_operations` owns common request execution, output writing,
  and stable error-to-exit-code behavior for standard session, resource,
  package, and catalog operations.

Harness receives already parsed request values and explicit callbacks. It does
not inspect a Coding argument object and does not import Coding, Method, Work,
TUI, or a product wire schema.

## Coding Binding

Coding declares the operation order and constructs shared request objects from
`CliArgs`. It retains:

- `CliArgs` and help text;
- Coding bootstrap and tool/resource policy selection;
- package source security and diagnostics callbacks;
- Method discovery/compilation and Work event-log bindings;
- final prompt, RPC, Channel, print, and TUI mode selection.

The old Coding helpers are deleted once the equivalent Harness operations are
used directly. Compatibility facades are not retained.

## Behavior Contract

The migration preserves operation precedence, output formats, error text, and
exit codes. Multiple command-style flags continue to execute only the first
operation in the existing order. No external CLI or RPC field is renamed in
this slice.

## Dependency Rule

`loushang.harness.cli` may depend on public Harness, Agent, and AI value/codec
APIs needed by standard Agent-product CLI operations. It must not import
`loushang.coding`, `loushang.method`, `loushang.work`, or terminal UI packages.
`loushang.channel` remains independent of Harness and Product packages.
