# CLI Product Host Collapse

## Boundary

Product CLI additions, Product startup policy, Method/Work bindings, and
product wording remain product-owned. Harness owns the standard Agent CLI
grammar/value projection, two-pass application lifecycle, and reusable
operations over injected session and settings capabilities. Channel continues
to own stream binding, stdout protection, turn ordering, and disposal through
`ProductHostLifecycle`.

This slice extends the existing `loushang.harness.cli` runtime. It does not add
a second CLI parser, transport, session runtime, or product host.

## Shared Contracts

- `CliOperationSequence` executes product-selected operations in declared order
  and returns on the first handled exit code.
- `StandardCliOperationRequest` binds the standard Agent operation pack;
  `CliOperationInsertion` places Product operations at explicit points without
  rebuilding that pack.
- `CliOperationStage` binds a stable operation id to a synchronous or
  asynchronous handler. Products can add, remove, or reorder stages without
  changing Harness.
- `AgentCliArgs` and `agent_cli_argument_values()` project
  `STANDARD_CLI_PROFILE` once. Products subclass the value object with additive
  fields instead of copying the standard dataclass and namespace projection.
- `CliApplicationRuntime` owns bootstrap parse, static validation, guarded
  runtime construction, session resolution, extension-aware final parse,
  configuration, operation, and host phase ordering over injected ports.
- `run_keyword_cli_turns()` owns first/last image, follow-up, and disposal
  semantics for Product-prepared turn batches.
- `CliLaunchPlan` normalizes TTY selection, structured-output protection,
  session-restore conflicts, Work/Method/Channel compatibility, and
  observability mode without receiving a Product argument object.
- `harness.cli.host_operations` owns common request execution, output writing,
  and stable error-to-exit-code behavior for standard session, resource,
  package, and catalog operations.
- Standard Agent arguments project resource toggles, session listing and
  resolution, catalog operations, ephemeral bootstrap policy, resource-loader
  options, session paths, and image policy through their existing capability
  modules. Products no longer rebuild those requests.
- `configure_agent_cli_session()` owns extension flags, session naming,
  model-selection error containment, and thinking selection while Product
  callbacks retain persistence policy and warning wording.
- `workspace_tool_runtime_settings()` projects shared tool settings into an
  injected policy factory and standard headless approval resolver.
- `run_fake_workflow_cli()` lets fake scenario workflows exit before Product
  runtime construction without moving scenario execution into the CLI layer.

Harness receives already parsed request values and explicit callbacks. It does
not inspect a Coding argument object and does not import Coding, Method, Work,
TUI, or a product wire schema.

## Coding Binding

Coding subclasses `AgentCliArgs` with Method/Work fields, inserts its Method and
package-catalog stages into the standard operation pack, supplies its policy
factory and model-persistence warning, and binds Product callbacks to
`CliApplicationRuntime`. It retains:

- additive Method/Work argument grammar;
- Coding bootstrap and tool/resource policy selection;
- package source security and diagnostics callbacks;
- Method discovery/compilation and Work event-log bindings;
- final prompt, RPC, Channel, print, and TUI mode selection.

The old Coding helpers are deleted once the equivalent Harness operations are
used directly. Compatibility facades are not retained.

## Behavior Contract

The migration preserves operation precedence, two-pass extension flag parsing,
output formats, error text, and exit codes. Multiple command-style flags
continue to execute only the first operation in the existing order. No
external CLI or RPC field is renamed in this slice.

## Dependency Rule

`loushang.harness.cli` may depend on public Harness, Agent, and AI value/codec
APIs needed by standard Agent-product CLI operations. It must not import
`loushang.coding`, `loushang.method`, `loushang.work`, or terminal UI packages.
`loushang.channel` remains independent of Harness and Product packages.
