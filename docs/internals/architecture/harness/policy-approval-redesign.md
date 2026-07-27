# Policy And Approval Redesign

Status: proposed replacement architecture

Owner: `loushang.harness`

Compatibility: no compatibility guarantee for the current Policy/Approval API

## 1. Decision

Replace the current tool-shaped Policy/Approval implementation with a
product-neutral **authorization runtime**:

```text
Action proposal
  -> canonical action + requested effects
  -> policy evaluation
  -> allow / deny / require approval
  -> optional approval and scoped grant
  -> execution-time revalidation
  -> constrained execution
  -> audit events
```

The new owner is:

```text
loushang.harness.authorization
```

`Policy` remains the decision mechanism inside this package. `Approval` is a
separate consent lifecycle. A sandbox or another executor is the enforcement
mechanism. These three concepts must not be collapsed:

| Concern | Question | Owner |
|---|---|---|
| Policy | May this actor attempt this exact action? | authorization runtime |
| Approval | Who may grant a bounded exception, and for how long? | approval coordinator |
| Enforcement | What can the process actually read, write, execute, or reach? | executor/sandbox using the authorized profile |

This design is intentionally not a compatibility extension of
`PolicyDecision(allow|deny|ask)` and `ApprovalDecision(allow|deny)`. Those
types are too small to represent rule provenance, delegated authority,
session grants, durable pending approval, or execution-time validation.

## 2. Scope

This architecture governs effectful actions initiated by:

- a user or CLI command;
- a root or child Agent;
- a Product runtime;
- an extension;
- an MCP server or connector;
- a Method/Work executor;
- a daemon.

It covers:

- tool calls and process execution;
- filesystem and workspace effects;
- network access;
- Git publication and workspace integration;
- secret access;
- child-Agent creation and delegated capabilities;
- MCP connection and tool invocation;
- daemon and durable Work control actions;
- Product-specific effects such as export or upload.

It does **not** replace:

- extension activation policy;
- package or resource source trust;
- Product planning policy;
- model selection policy;
- Method scheduling semantics.

Those domains may call the authorization runtime before an effect, but they
retain their own domain models.

## 3. Why The Current Design Should Be Replaced

The current implementation has useful foundations—immutable requests,
command normalization, evaluator composition, pending request correlation,
TUI presentation, and Work event projection—but its central model is not
strong enough.

### 3.1 Policy is tool-shaped and under-specified

Current policy subjects are primarily tool, command, and path values. The
default engine relies heavily on string and substring matching and falls back
to allow. It does not model:

- the caller identity and delegation chain;
- requested effects and resources;
- managed constraints versus user preferences;
- an effective filesystem/network/process permission profile;
- risk, obligations, or matched-rule provenance;
- a stable action fingerprint;
- whether an approval can legally widen the current authority.

### 3.2 Approval is only a boolean

The current request carries a tool name, arguments, and a reason. The result is
only allow or deny. It cannot express:

- allow once versus allow for this session;
- a safely scoped persistent rule;
- an amended command or permission profile;
- abort, timeout, cancellation, or supersession;
- the identity and source of the reviewer;
- an expiry or revocation;
- a durable pending request across daemon restart.

### 3.3 Presentation owns too much lifecycle

The current interactive broker is bound to one event loop and one live
presenter. That is adequate for a single interactive session, but not for:

- a TUI detaching and reattaching;
- multiple authenticated review channels;
- Work waiting durably for approval;
- a daemon restart;
- remote approval with stale-response rejection.

The presenter must be a projection of pending state, not the owner of pending
state.

### 3.4 Enforcement is scattered

Workspace tools call `enforce_tool_policy()` individually. This makes it
difficult to guarantee that every effectful path performs:

1. the same canonicalization;
2. the same policy evaluation;
3. the same approval flow;
4. the same execution-time revalidation;
5. the same audit publication.

Approval also must not silently remove sandbox restrictions or managed denies.

## 4. Lessons Adopted From Codex And Claude Code

The local Codex and Claude Code implementations are used as design references,
not as APIs to copy.

### 4.1 Adopt from Codex

- Keep approval mode and sandbox policy separate.
- Approve an exact command/action snapshot, including its execution context.
- Support one-shot, session, and carefully validated policy amendments.
- Record whether a decision came from the user, a hook, or an automated
  reviewer.
- Represent deny, timeout, and abort as different terminal outcomes.
- Never let approval bypass hard filesystem or sandbox restrictions.
- Treat network access as a typed permission with host-scoped amendments.

### 4.2 Adopt from Claude Code

- Make permission modes a user-experience and fallback policy, not the
  enforcement mechanism itself.
- Preserve rule provenance and persistence destination.
- Let tools provide typed matchers and safe authorization suggestions.
- Return an explainable decision reason and matched rule.
- Re-evaluate permission immediately before execution.
- Arbitrate multiple approval channels with complete-once semantics.
- Reject stale approval responses.
- Let managed settings impose a ceiling that local or session settings cannot
  widen.
- Keep hard safety checks active even in an unrestricted mode.

### 4.3 Deliberate Loushang differences

- The core action and approval types are cross-product Harness types.
- Child Agents are first-class actors with delegated authority.
- Work and daemon execution use the same approval state machine as an
  interactive session.
- MCP connection trust and MCP invocation authorization are separate actions.
- Product adapters describe effects and presentation; they do not replace the
  coordinator.

## 5. Low-friction Default

The target experience is:

> Normal coding should run dozens of tool calls without approval. Interrupt the
> user only for destructive, publishing, privileged, secret-bearing, or
> externally effectful actions.

This is a hard product requirement, not an optional presentation refinement.
Approval count is a quality metric.

### 5.1 Approve boundary crossings, not command strings

Policy should not ask because an argument changed. It should ask only when the
new action crosses a security boundary.

```text
typed action
  -> capability family
  -> resource scope
  -> gated effects
  -> effective execution containment
  -> allow or require approval
```

The standard Coding profile automatically allows:

| Action | Default |
|---|---|
| read, grep, list, inspect | allow |
| edit/write inside the active workspace | allow |
| formatting, tests, type checks, compilation | allow |
| local Git inspection, staging, commits, and branches | allow |
| bounded temporary/build-output cleanup | allow |
| public network reads without credentials or execution | allow through the network policy |

It requires approval when any of these gates is present:

| Gate | Examples |
|---|---|
| destructive or poorly recoverable | recursive deletion, `git reset --hard`, `git clean -fdx`, overwrite of broad/untracked data |
| publication or external mutation | `git push`, deploy, publish package, send message, upload artifact |
| privilege or system escape | `sudo`, system configuration, writes outside admitted roots |
| secret access | credentials, private keys, protected environment values |
| external code/effect | package install scripts, downloaded code execution, authenticated POST, remote administration |

This is broader and safer than a rule that prompts only for `rm -rf`.
Destructive behavior can also be expressed through Git, redirection, Python,
`find -delete`, `dd`, installer scripts, or Product-specific APIs.

### 5.2 The safe coding capsule

Most automatic permission comes from containment, not from trusting the
command name:

```text
active workspace roots    read/write
declared temporary roots  read/write
repository metadata       bounded local VCS operations
outside roots             read-only or denied
secrets                    absent unless explicitly granted
network                    public read profile or denied
privilege escalation      denied
external publication      denied
```

When enabled and available, the capsule lets an unknown command run without
approval while preventing the five gated effects. It is a defense-in-depth
mechanism and a way to reduce approval frequency; it is not a prerequisite for
ordinary Coding in the default profile. The default configuration does not
enable an OS sandbox.

If the platform sandbox is unavailable, `standard` mode falls back to typed
action classification and the Product risk rules:

- recognized routine local coding remains automatically allowed;
- detected gated effects still require approval;
- ambiguous actions may require approval, but the session does not fail merely
  because an OS sandbox backend is absent.

The Coding adapter may additionally use Git/checkpoint recovery to make broad
workspace changes reversible. Recovery reduces unnecessary prompts, but it
does not authorize publication, privilege escalation, secret access, or
effects outside the checkpoint.

### 5.3 Capability grants, not full argument grants

“Allow for this session” stores a typed matcher. It does not normally store
the complete argument vector.

For example:

```text
uv run pytest tests/a.py -q
```

may propose:

```text
capability: process.run_tests
runner: uv
test_runner: pytest
workspace: <current workspace>
scope: session
```

The grant also covers `pytest tests/b.py`, but it does not cover `uv publish`
or a process outside the workspace.

Security-relevant arguments remain part of the matcher:

| Action family | Parameters retained in the grant |
|---|---|
| tests/format/lint | runner identity, workspace, containment profile |
| Git read/local operations | repository and allowed subcommand family |
| Git publish | remote, repository, ref scope, force policy |
| network | scheme, host, port, method, credential and upload policy |
| filesystem deletion | canonical targets, breadth, recoverability |
| MCP | server identity, tool identity, schema version |

If the adapter cannot safely generalize an action, it offers only “allow
once”. Raw model-authored prefixes are never persisted directly.

### 5.4 Minimal approval choices

The common approval surface should normally show only:

1. **Allow once**
2. **Allow this capability for the session**, when a safe proposal exists
3. **Deny**, optionally with feedback

Persistent user/project rules are managed through `/permissions` or an
expanded details flow. They should not be the prominent default choice on
every prompt. High-risk actions may deliberately omit the session option.

The approval summary leads with the crossed boundary:

```text
Publish commits to origin/main
External effect: updates a shared remote branch
```

The full canonical command remains available in details but is not the
permission identity shown as “always allow”.

### 5.5 Fallback for unclassified commands

```text
known safe semantic adapter
  -> execute within its profile

unknown action + all gated effects enforceably blocked
  -> execute in the restricted capsule

unknown action + detected gated effect
  -> require approval

unknown action + no detected gated effect + standard mode
  -> allow with audit, using the best available containment

incomplete semantic classification in standard mode
  -> allow or require approval according to detected effects

invalid action schema or canonicalization
  -> deny

unavailable enforcement when the deployment explicitly requires a sandbox
  -> deny
```

This avoids approval fatigue in the default experience while retaining a
fail-closed enforcement setting for deployments that explicitly require it.

### 5.6 Measurable acceptance target

The Coding playback suite must include representative sessions containing:

- code inspection;
- several edits;
- formatter, tests, and type checks;
- local Git inspection and commit preparation;
- one destructive action;
- one publish action.

For the standard profile:

- routine local coding should generate zero approval requests;
- destructive and publish actions should each generate exactly one request;
- changing non-security test arguments should not invalidate the session
  capability grant;
- changing a remote, target root, credential mode, or effect class must
  invalidate it.

Telemetry and diagnostics should report approvals per 100 tool calls, grouped
by action family and matched rule, without storing secrets or full sensitive
arguments.

## 6. Security Invariants

The implementation must enforce these invariants:

1. **Every effectful execution has one canonical `ActionRequest`.**
2. **Hard and managed denies cannot be overridden by approval.**
3. **A child cannot gain more authority than its delegated envelope.**
4. **A grant is bounded by actor, action matcher, resource scope, lifetime, and
   issuing authority.**
5. **The action executed must match the action approved.**
6. **A pending approval has at most one accepted terminal resolution.**
7. **A stale, duplicate, unauthenticated, or mismatched resolution has no
   effect.**
8. **Non-interactive execution never waits forever for a presenter.**
9. **Policy or adapter failure cannot become an implicit allow.**
10. **Audit data is sufficient to explain the decision without leaking
    secrets.**
11. **Approval is not a substitute for an executor sandbox.**
12. **Persistent grants can only be created from prevalidated proposals, never
    from arbitrary model-authored rule text.**

## 7. Core Domain Model

The examples below define the intended shape, not final Python syntax.

### 7.1 Actor

```python
ActorKind = Literal[
    "user",
    "root_agent",
    "child_agent",
    "product",
    "extension",
    "mcp_peer",
    "work",
    "daemon",
]

@dataclass(frozen=True)
class ActorRef:
    kind: ActorKind
    actor_id: str
    product_id: str
    session_id: str | None
    parent_actor_id: str | None = None
    work_run_id: str | None = None
```

Actor identity is explicit. A tool call no longer implies that the root Agent
is the caller.

### 7.2 Action

```python
@dataclass(frozen=True)
class ActionRequest:
    action_id: str
    revision: int
    actor: ActorRef
    kind: ActionKind
    parameters: JsonObject
    resources: tuple[ResourceClaim, ...]
    effects: EffectSet
    context: ExecutionContext
    origin: ActionOrigin
    fingerprint: str
```

`action_id` identifies the logical proposal. `revision` increments whenever a
security-relevant input changes. Each actual run also receives a distinct
execution-attempt ID in the event stream. An allow-once grant binds to one
action revision and is consumed by one execution attempt; retries do not
silently reuse it.

`ActionKind` is extensible but namespaced:

```text
tool.call
process.exec
filesystem.read
filesystem.write
filesystem.delete
network.connect
secret.read
workspace.create
workspace.integrate
vcs.publish
agent.spawn
mcp.connect
mcp.invoke
daemon.control
product.export
```

An action adapter must:

- validate and freeze parameters;
- resolve paths relative to the actual execution directory;
- identify resources and effects;
- redact secret-bearing values for presentation and events;
- produce a deterministic fingerprint over the executable snapshot.

The fingerprint covers security-relevant values such as:

- actor and delegation envelope;
- action kind;
- executable/arguments/stdin;
- resolved cwd and paths;
- relevant environment names and non-secret values;
- network host/port/protocol;
- MCP server identity, tool name, and schema/version;
- workspace and branch identity;
- requested permission delta.

### 7.3 Resource claims and effects

```python
@dataclass(frozen=True)
class ResourceClaim:
    kind: Literal[
        "path", "network_host", "secret", "workspace",
        "repository", "mcp_server", "agent_tree", "product_resource"
    ]
    identifier: str
    access: tuple[str, ...]

@dataclass(frozen=True)
class EffectSet:
    filesystem: frozenset[str]
    process: frozenset[str]
    network: frozenset[str]
    vcs: frozenset[str]
    external: frozenset[str]
    orchestration: frozenset[str]
```

Tool-specific semantic adapters are preferred over universal substring rules.
For example, Coding's Bash adapter may parse command prefixes and pipelines,
while a PPT adapter describes an external asset upload without pretending it
is a shell command.

### 7.4 Permission profile

```python
@dataclass(frozen=True)
class PermissionProfile:
    filesystem: FilesystemPermissions
    process: ProcessPermissions
    network: NetworkPermissions
    secrets: SecretPermissions
    tools: ToolPermissions
    workspace: WorkspacePermissions
    agents: AgentPermissions
    mcp: McpPermissions
```

This profile is the maximum effective authority passed to execution. Policy
may narrow it. Approval may select a grant within the applicable ceiling. No
decision may widen it beyond managed, Product, parent-delegated, or executor
constraints.

Implementation checkpoint (2026-07-27): the first enforcement-facing slice is
implemented as `harness.authorization.EffectiveExecutionProfile`. It carries
the currently enforceable filesystem roots and network authority, intersects a
requested profile with its ceiling, adapts current Policy/Approval decisions,
and projects into `SandboxScopeRequest`. Secret filtering, privilege and
external-effect permissions remain in the authorization delivery batches; they
must not be claimed as sandbox enforcement before their gateways migrate.

### 7.5 Policy verdict

```python
PolicyDisposition = Literal["allow", "deny", "require_approval"]

@dataclass(frozen=True)
class PolicyVerdict:
    disposition: PolicyDisposition
    code: str
    reason: str
    risk: RiskLevel
    trace: PolicyTrace
    effective_permissions: PermissionProfile
    obligations: tuple[PolicyObligation, ...]
    approval_plan: ApprovalPlan | None = None
```

`PolicyTrace` records evaluated sources and matched rule IDs. `obligations`
represent required behavior such as audit, sandboxing, redaction, rate limits,
or an explicit user reviewer.

The old ambiguous `ask` name is replaced by `require_approval`: it is a policy
verdict, not an instruction to a particular UI.

## 8. Policy Model

### 8.1 Constraints and decision rules are different

A simple “last rule wins” order is unsafe. The runtime uses two phases:

1. **Compute the authority ceiling**
   - hard Harness invariants;
   - managed/organization constraints;
   - Product constraints;
   - executor/sandbox capabilities;
   - parent-to-child delegation.
2. **Choose behavior inside the ceiling**
   - explicit denies;
   - existing grants;
   - user/project/session rules;
   - mode fallback.

An allow rule can choose behavior only inside the ceiling. It cannot erase a
deny in the ceiling.

### 8.2 Policy sources

```text
hard Harness invariant        immutable
managed policy                organization-controlled, read-only locally
Product policy profile        Product-owned semantic constraints
user policy                   user-owned durable preferences
trusted project policy        repository-local, trust-gated
session policy and grants     ephemeral
action grant                  one-shot
```

For competing behavioral rules at the same legal authority:

```text
deny > require_approval > allow
```

A user may always narrow authority. Project content cannot silently grant
itself more authority. An extension contributes rules only within the
extension's registered trust and capability envelope.

### 8.3 Modes

Modes select fallback behavior; they do not override constraints:

| Mode | Default behavior |
|---|---|
| `standard` | allow routine local coding and actions without detected gated effects; require approval for broader effects |
| `plan` | allow bounded reads; deny mutations and publication |
| `accept_workspace_edits` | allow bounded workspace edits; still gate shell, network, secrets, and publication |
| `non_interactive` | convert unresolved approval requirements to deny unless a valid grant exists |
| `unrestricted` | allow up to the configured ceiling; hard invariants remain |

Products may choose a default mode and presentation labels, but the meanings
above are common.

Sandbox configuration is orthogonal to these modes. With no configuration, the
OS sandbox is disabled and `standard` relies on semantic Policy. When sandboxing
is explicitly enabled, `sandbox_requirement=best_effort|required` is separate
and defaults to `best_effort`; unavailable best-effort enforcement degrades
gracefully to semantic Policy. A managed deployment may select `required` and
fail startup or execution when no backend is available. Enabling the Phase A-C
sandbox alone retains host networking so routine `git`, `gh`, `curl`, and
dependency discovery keep working. The future effective permission profile,
not the sandbox enable switch, narrows individual actions to public-read,
restricted, or denied network access.

### 8.4 Evaluation failures

Each policy contribution declares whether failure means:

- `deny`;
- `require_approval`;
- `abstain`.

Only a trusted, non-mandatory advisory source may abstain. Managed, Product
constraint, canonicalization, and action-adapter failures fail closed. There is
no generic exception path that defaults to allow.

## 9. Grants

Approval produces a resolution and may create a grant:

```python
GrantScope = Literal[
    "action",
    "turn",
    "session",
    "work_run",
    "workspace",
    "project",
    "user",
]

@dataclass(frozen=True)
class AuthorizationGrant:
    grant_id: str
    subject: ActorMatcher
    action: ActionMatcher
    resources: tuple[ResourceConstraint, ...]
    permissions: PermissionProfile
    scope: GrantScope
    issued_by: ReviewerRef
    issued_at: datetime
    expires_at: datetime | None
    source_request_id: str
    revocable: bool = True
```

### 9.1 Grant proposals

An approval screen may offer:

- allow this exact action once;
- allow this safe matcher for the session;
- add a validated user/project rule;
- deny;
- deny with feedback;
- abort the owning turn or run.

These options are generated by policy and action adapters. The model cannot
invent a persistence destination or an unbounded matcher.

Examples:

- process: allow the exact canonical command once;
- process: allow a validated executable prefix in this workspace for the
  session;
- network: allow one exact host for the session;
- filesystem: allow writes below one canonical workspace root;
- MCP: allow one server/tool/schema tuple;
- child Agent: allow one admitted Agent type below the current parent.

Persistent proposals require a stricter validator than session grants.

## 10. Approval Lifecycle

### 10.1 Request and resolution

```python
@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    action: ActionSnapshot
    policy_verdict: PolicyVerdictRef
    available_options: tuple[ApprovalOption, ...]
    presentation: ApprovalPresentation
    created_at: datetime
    expires_at: datetime | None
    revision: int

ApprovalOutcome = Literal[
    "allow_once",
    "allow_with_grant",
    "deny",
    "abort",
    "expired",
    "cancelled",
    "superseded",
]

@dataclass(frozen=True)
class ApprovalResolution:
    request_id: str
    expected_revision: int
    action_fingerprint: str
    outcome: ApprovalOutcome
    selected_option_id: str | None
    reviewer: ReviewerRef
    feedback: str | None
    resolved_at: datetime
```

### 10.2 State machine

```text
proposed
   |
   v
pending -------------------------------+
   |                                   |
   +-> allowed_once                    |
   +-> allowed_with_grant              |
   +-> denied                          | terminal
   +-> aborted                         |
   +-> expired                         |
   +-> cancelled                       |
   +-> superseded ---------------------+
```

Only `pending` accepts a resolution. The coordinator compares request ID,
revision, action fingerprint, reviewer authority, and option ID in one atomic
complete-once operation.

### 10.3 Review channels

The coordinator may expose the same pending request to:

- local TUI;
- CLI/RPC client;
- an authenticated daemon client;
- a policy hook;
- a bounded automated reviewer.

The first valid terminal resolution wins. Later responses are recorded as
stale and ignored. A hook or automated reviewer can decide only within its
configured ceiling; high-risk actions may require a user reviewer.

### 10.4 Presentation is a projection

Closing the TUI surface does not mutate authorization state unless the user
explicitly selects deny or abort. Detaching a client leaves a durable request
pending until expiry or another policy-defined terminal transition.

The presentation model includes:

- actor and parent/child provenance;
- human-readable action summary;
- typed resource/effect summary;
- risk and matched policy reason;
- exact available options;
- expiry and persistence destination;
- redacted technical details.

### 10.5 Ownership and shutdown

Every request has one continuity owner:

- `session`: cancellation or replacement of that session cancels pending
  requests and revokes its session grants;
- `work_run`: TUI/session detachment does not cancel it; the Work lifecycle
  resolves cancellation and restart;
- `daemon`: the daemon store owns expiry and reattachment;
- `action`: the request ends with the one execution attempt.

Closing a child Agent cancels its session-owned pending requests. Closing the
root session recursively cancels session-owned child requests, but it does not
delete a request already transferred to a durable Work owner. Persistence is
therefore an explicit ownership transfer, not an accidental consequence of
writing a request to disk.

## 11. Mandatory Enforcement Gateway

Every effectful tool or Product operation uses one gateway:

```python
result = await authorization.execute(
    proposal=tool_adapter.propose(call),
    executor=tool_executor,
)
```

The executor consumes the gateway's frozen canonical action, not the original
mutable tool-call object. Otherwise a caller could obtain approval for one
snapshot and execute another.

The gateway owns this sequence:

```text
1. validate and canonicalize proposal
2. freeze ActionRequest and fingerprint
3. derive resource claims and requested effects
4. compute authority ceiling
5. evaluate policy and existing grants
6. deny, or create/wait for approval if required
7. validate and install any selected grant
8. materialize the executable request again
9. compare the execution fingerprint with the authorized fingerprint
10. re-evaluate if security-relevant state changed
11. execute with the effective PermissionProfile/sandbox
12. publish terminal audit events
```

Step 8–10 prevents time-of-check/time-of-use bugs caused by changed cwd,
environment, symlinks, MCP schemas, workspace identity, or command material.

Tools retain their executors. They no longer each implement their own approval
algorithm.

## 12. Runtime Components And Ports

```text
AuthorizationRuntime
  |- ActionAdapterRegistry
  |- PolicyRuntime
  |- GrantStore
  |- ApprovalCoordinator
  |- EnforcementGateway
  |- AuthorizationEventSink
  `- PermissionEnforcerPort
```

### 12.1 Policy runtime

```python
class PolicyRuntime(Protocol):
    async def evaluate(
        self,
        action: ActionRequest,
        context: PolicyContext,
    ) -> PolicyVerdict: ...
```

Evaluation is deterministic for the supplied snapshot. The trace is inspectable
and testable without a UI or executor.

### 12.2 Stores

```python
class GrantStore(Protocol):
    async def applicable(self, action: ActionRequest) -> tuple[AuthorizationGrant, ...]: ...
    async def put(self, grant: AuthorizationGrant) -> None: ...
    async def revoke(self, grant_id: str) -> bool: ...

class ApprovalStore(Protocol):
    async def create(self, request: ApprovalRequest) -> None: ...
    async def get(self, request_id: str) -> ApprovalRecord | None: ...
    async def resolve(self, resolution: ApprovalResolution) -> ResolveResult: ...
    async def pending(self, query: ApprovalQuery) -> tuple[ApprovalRecord, ...]: ...
```

Initial interactive sessions use in-memory implementations. Work/daemon uses a
durable implementation with the same semantics.

### 12.3 Reviewer port

```python
class ApprovalReviewChannel(Protocol):
    async def publish(self, request: ApprovalRequest) -> None: ...
    async def withdraw(self, request_id: str, revision: int) -> None: ...
```

Review channels publish resolutions back to the coordinator. They do not
return a boolean directly from `publish()`.

### 12.4 Permission enforcer

```python
class PermissionEnforcerPort(Protocol):
    async def execute(
        self,
        action: ActionRequest,
        permissions: PermissionProfile,
        operation: AuthorizedOperation[T],
    ) -> T: ...
```

Coding may bind process and workspace sandboxing. PPT may bind file/export
constraints. The Harness contract does not pretend that all Products execute
shell commands.

## 13. Events And Audit

Authorization publishes product-neutral events:

```text
authorization.policy_evaluated
authorization.approval_requested
authorization.approval_presented
authorization.approval_resolved
authorization.approval_expired
authorization.approval_cancelled
authorization.grant_created
authorization.grant_revoked
authorization.action_authorized
authorization.action_revalidated
authorization.action_started
authorization.action_completed
authorization.action_failed
```

Each event carries stable references:

- action/request/grant ID;
- actor/session/work references;
- action kind and fingerprint;
- policy code, rule IDs, and risk;
- resolution source and scope;
- redacted resource claims;
- sequence and timestamp.

Full commands, secret values, tokens, and sensitive file content are not copied
blindly into audit events.

Session, Work, daemon, CLI, TUI, and diagnostics project these events rather
than inventing separate approval lifecycles.

## 14. Integration With Existing Loushang Systems

### 14.1 Workspace tools and Coding

Each tool registers an action adapter beside its executor:

| Tool/action | Adapter responsibility |
|---|---|
| `read`, `grep`, `ls` | canonical paths and read scope |
| `write`, `edit` | canonical write set and workspace boundary |
| `bash` | materialized command, cwd, env, stdin, parsed effects |
| Git publish | remote/ref/repository and external publication effect |
| workspace integrate | source workspace, target branch, patch/diff identity |

Coding owns its policy profile, safe command-prefix proposals, risk copy, and
executor binding. It does not fork the approval state machine.

The active mode and a redacted capability summary may be shown to the model so
it can avoid futile calls, but prompts and tool descriptions are advisory.
Enforcement never trusts the model's understanding of its permissions. A
denied or cancelled action returns a structured tool result tied to the action
ID; it is not injected as a second synthetic user message.

### 14.2 Harness TUI

Approval remains a common Harness TUI capability. The current boolean
`ApprovalSurfaceDecision` becomes a typed option selection:

```python
ApprovalSurfaceDecision(
    request_id=...,
    revision=...,
    option_id=...,
    feedback=...,
)
```

The surface reads pending records and can be reopened after `/agents`, session
navigation, or client reattachment. Products may add detail projectors, but
common option semantics and stale-result handling remain Harness-owned.

### 14.3 Multi-agent

A child receives an explicit delegated `PermissionProfile`:

```text
effective child ceiling
  = managed ceiling
  ∩ Product ceiling
  ∩ parent delegated envelope
  ∩ AgentTypeSpec limits
  ∩ workspace/executor limits
```

Child approval is sent to the root approval coordinator with:

- child `ActorRef` and parent chain;
- Agent path and run round;
- tool call/action origin;
- exact action fingerprint.

It is not delivered through the normal model mailbox. Approval does not wake
the parent model. A parent or user may grant only within the child's delegated
ceiling.

### 14.4 Work and Method

Work projects authorization events and owns durable waiting:

```text
running
  -> waiting_for_approval(request_id)
  -> running | denied | cancelled | expired
```

`WorkStepRun.approval_ref` points to the shared approval record. Method may
declare an approval gate, but it does not resolve or persist approval itself.

### 14.5 Daemon

The daemon binds a durable `ApprovalStore` and authenticates review clients.
On restart it:

1. reloads pending requests;
2. restores owning Work checkpoints;
3. republishes still-valid requests;
4. expires invalid requests;
5. rejects stale client responses by revision and fingerprint.

A non-interactive daemon defaults unresolved approval to deny or durable wait
according to the Work profile; it never silently auto-allows.

### 14.6 MCP

MCP uses two separate actions:

1. `mcp.connect`: whether this server/connector is trusted and enabled;
2. `mcp.invoke`: whether this exact server tool call is authorized.

The fingerprint includes server identity, connector identity, tool name, and
schema/version. Managed allowlists and denylists constrain both actions. A
server cannot approve its own invocation unless an explicitly trusted policy
channel permits that narrow behavior.

### 14.7 Extensions

The current “exclusive approval replacement” extension slot is removed.
Extensions may contribute:

- typed action adapters for their own actions;
- bounded decision rules;
- advisory reviewers;
- presentation detail projectors.

They cannot replace `ApprovalCoordinator`, `GrantStore`, or the hard/managed
constraint phase. Contributions declare trust class and failure behavior.

### 14.8 Settings and CLI

Settings expose:

- current authorization mode;
- effective constraints;
- user/project/session rules with provenance;
- active and expired grants;
- pending requests;
- managed fields that cannot be edited locally.

CLI and TUI changes are transactional and validated before persistence.
Suggested commands are:

```text
/permissions
/permissions mode <mode>
/permissions grants
/permissions revoke <grant-id>
```

Products may choose aliases, but they operate on the shared runtime.

## 15. Physical Module Layout

Keep the first implementation compact:

```text
src/loushang/harness/authorization/
  __init__.py
  types.py          # actor, action, claims, profiles, verdicts, grants
  policy.py         # modes, rule sources, evaluation and trace
  approval.py       # request/resolution state and coordinator
  store.py          # in-memory ports and persistence contracts
  enforcement.py    # mandatory gateway and revalidation
```

Product adapters remain outside:

```text
src/loushang/coding/authorization.py
src/loushang/harnesstui/...approval...
src/loushang/work/...authorization projection...
```

After cutover, remove:

```text
src/loushang/harness/policy.py
src/loushang/harness/policy_engine.py
src/loushang/harness/approval.py
src/loushang/coding/policy/
```

Command normalization code that remains generally useful should move into the
process action adapter rather than being discarded.

## 16. Current-to-target Cutover Ledger

There must be one cutover, not a permanent legacy bridge:

| Current owner | Target |
|---|---|
| `harness/policy.py` value types and evaluator chain | replace with `authorization/types.py` and `authorization/policy.py` |
| command normalization inside `harness/policy.py` | retain behind Coding/process `ActionAdapter` |
| `harness/policy_engine.py` default string rules | delete; replace with Product profile plus typed rules |
| `harness/approval.py` resolver/broker | replace with `authorization/approval.py` coordinator and stores |
| `harness/tools/workspace/policy.py` | replace with the common enforcement gateway |
| per-tool `policy_engine` / `approval_resolver` arguments | replace with one bound `AuthorizationRuntime` |
| `harness/tools/workspace/factory.py` policy/approval assembly | compose the Product authorization profile and runtime |
| `coding/policy/` | delete after Coding action adapters/profile are active |
| `harness/session/agent_adapter.py` presenter binding | bind/unbind a review channel; pending state stays in the coordinator |
| `harnesstui` boolean approval surface | select typed `ApprovalOption` values |
| `harness/multiagent/context.py` approval resolver | replace with actor/delegation context and root coordinator reference |
| `work/agent_projection.py` tool-specific approval events | project common authorization events |
| `WorkStepRun.approval_ref` | retain as a reference to the common approval record |
| extension `register_approval()` replacement slot | remove; add bounded rule/reviewer/detail contributions |
| extension routing machinery | retain; it is outside the authorization replacement |

Temporary adapters may exist only inside an implementation branch while a
batch is being migrated. They are not public compatibility contracts and must
be removed before the batch exit gate.

## 17. Delivery Plan

### Batch 1 — authorization values and pure policy

- Add actor, action, resource/effect, permission, verdict, trace, and grant
  types.
- Add canonical fingerprinting.
- Add the common capability families and five gated effect classes.
- Implement modes, constraint ceilings, rule provenance, and in-memory grants.
- Add Product profile and action-adapter ports.
- Define the standard Coding profile and safe generalization rules before
  migrating executors.
- No UI or legacy adapter is required.

Exit gate:

- deny/approval/allow precedence is exhaustively tested;
- managed and delegated ceilings cannot be widened;
- changed action snapshots produce different fingerprints;
- non-security argument changes retain the same safe capability matcher;
- remote, target-root, credential, or effect-class changes do not;
- policy traces explain every result.

### Batch 2 — enforcement gateway and core tools

- Add the mandatory gateway and event stream.
- Migrate read/write/edit/bash and workspace integration.
- Bind existing execution/sandbox facilities through
  `PermissionEnforcerPort`.
- Bind the optional safe coding capsule: admitted workspace roots, filtered
  secrets, bounded network, and denied privilege escalation/publication.
- Preserve the experience-first `standard` fallback when no supported sandbox
  backend is available.
- Revalidate immediately before execution.

Implementation checkpoint (2026-07-27): Bash, read, write, and edit now enter a
shared Workspace authorization gateway which freezes canonical arguments and a
deterministic action fingerprint before invoking the current Policy/Approval
adapter. This removes four independent entry paths. The next slice must move the
executor callback and per-action `EffectiveExecutionProfile` into that gateway;
until then the legacy adapter remains the decision backend.

Exit gate:

- no migrated effectful tool bypasses the gateway;
- representative local coding playback produces no approval requests;
- unclassified commands without detected gated effects remain usable in
  `standard`; deployments with `sandbox_requirement=required` still require
  enforceable containment;
- canonical path, symlink, cwd, env, and command mutation tests pass;
- audit events are ordered and redacted.

### Batch 3 — approval coordinator and common TUI

- Add in-memory approval/grant stores.
- Add complete-once coordinator, expiry, cancellation, and stale rejection.
- Replace boolean TUI choices with the minimal policy-generated options:
  allow once, safe session capability, and deny.
- Add session grants and headless/non-interactive behavior.

Exit gate:

- local/remote/timeout/cancel races accept one result;
- closing and reopening a surface does not lose pending state;
- allow-once is consumed once;
- session grants do not leak across actors or sessions.

### Batch 4 — multi-agent, extensions, and MCP

- Delegate child permission envelopes and bubble typed approval provenance.
- Replace extension approval replacement with bounded contributions.
- Add MCP connect/invoke adapters.
- Add Product-specific detail projectors.

Exit gate:

- child authority is an intersection, never a union;
- approval does not enter the parent model mailbox;
- extension failure follows declared fail-closed semantics;
- MCP identity/schema changes invalidate approval.

### Batch 5 — durable Work and daemon

- Implement durable approval storage.
- Add Work waiting/checkpoint transitions.
- Add daemon rehydration and authenticated reviewer clients.
- Add grant revocation and pending-request inspection.

Exit gate:

- restart playback preserves exactly one pending request;
- stale pre-restart responses are rejected;
- expired or revoked grants cannot execute;
- non-interactive runs never wait without an explicit durable-wait policy.

### Batch 6 — remove the old stack

- Delete old Policy/Approval APIs and Product wrappers.
- Delete legacy evaluation coercion and exclusive approval extensions.
- Update diagnostics, event projections, public docs, and examples.
- Run repository-wide import and architecture checks.

## 18. Required Test Matrix

At minimum, cover:

- hard/managed/Product/user/project/session precedence;
- deny winning over every grant;
- plan, edit-accepting, non-interactive, and unrestricted modes;
- action fingerprint mutation and execution-time revalidation;
- shell wrapper, pipeline, stdin, environment, and cwd normalization;
- path traversal and symlink changes;
- one-shot grant consumption;
- session/workspace/project grant scoping and revocation;
- local versus remote versus timeout approval races;
- duplicate and stale resolution rejection;
- presenter detach/reattach;
- Work cancellation while waiting;
- daemon restart with pending approval;
- child delegation and sibling isolation;
- MCP server/tool/schema identity;
- extension evaluator failure;
- audit event ordering and structural redaction;
- TUI playback for queued approvals and navigation between common surfaces.

## 19. Non-goals For The First Three Batches

Do not add these before the local session flow is correct:

- an LLM guardian or automatic safety reviewer;
- organization policy distribution;
- internet-facing remote approval;
- a general user-authored policy DSL;
- a new operating-system sandbox;
- approval voting or multi-party quorum;
- Method-level DAG scheduling changes.

The ports permit these later. The first objective is a small, explainable,
race-safe authorization core that Coding can exercise and other Products can
reuse.

## 20. Acceptance Summary

The redesign is complete only when:

1. the same action model drives Policy, Approval, enforcement, and audit;
2. a user can distinguish allow once, bounded grant, deny, and abort;
3. a changed action cannot reuse an old approval;
4. child and durable executions use the same authorization semantics;
5. TUI/CLI/daemon are review channels rather than lifecycle owners;
6. no approval can exceed managed, Product, delegated, or sandbox ceilings;
7. the old tool-shaped Policy/Approval stack is deleted.

## 21. Reference Implementation Evidence

The design comparison used these local implementation points:

### Codex

- `~/workspace/codex/codex-rs/protocol/src/protocol.rs`
  - approval modes, sandbox policies, and non-boolean review decisions;
- `~/workspace/codex/codex-rs/protocol/src/approvals.rs`
  - exact execution actions, permission amendments, decision options, and
    reviewer provenance;
- `~/workspace/codex/codex-rs/core/src/tools/approvals.rs`
  - centralized approval requirement evaluation and session approval cache;
- `~/workspace/codex/codex-rs/core/src/exec_policy.rs`
  - command policy and safe amendment mechanics.

### Claude Code

- `~/workspace/cc/src/types/permissions.ts`
  - modes, rule sources, decisions, update destinations, and suggestions;
- `~/workspace/cc/src/utils/permissions/permissions.ts`
  - rule/mode evaluation, managed constraints, and bypass-immune checks;
- `~/workspace/cc/src/hooks/toolPermission/handlers/interactiveHandler.ts`
  - competing review channels, complete-once arbitration, and rechecking;
- MCP permission configuration and relay handlers under
  `~/workspace/cc/src/`
  - managed allow/deny constraints and stale/unknown response rejection.

These references justify the selected invariants. They are not dependencies of
Loushang and do not define its public API.
