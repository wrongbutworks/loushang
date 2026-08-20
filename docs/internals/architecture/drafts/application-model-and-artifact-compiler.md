# Loushang Application Model And Artifact Compiler Architecture

## Status

- Scope: proposed `application` subsystem
- Parent: Loushang cross-product architecture
- Authority: normative target proposal
- Design status: proposed
- Implementation status: not implemented as this subsystem
- Review date: 2026-08-20

This document refines the Application Model and deterministic Artifact Compiler boundary proposed by
[Ontology-Driven Application Engineering](ontology-driven-application-engineering.md). It does not
claim that the proposed public package, compiler, target backends, materializer, or build Product
currently exist.

## 1. Outcome

The proposed subsystem should turn locked semantic and interaction inputs into deterministic,
verifiable application artifact plans:

```text
OntologyPackageArtifact
  + ApplicationPackageArtifact
  + optional Process/Policy artifacts
  + Source/Target locks
  + CompilerIdentity
  -> CompiledApplicationModel
  -> ArtifactPlan
  -> MigrationPlan
  -> ConformancePlan
```

It does not replace Coding. The compiler produces reproducible contracts and base artifacts; Coding
uses Agent and AI capabilities to implement explicit extensions and repair build or test failures.

## 2. Current Foundation And Gap

The current repository already provides useful lower-level foundations:

- `loushang.ontology.schema.OntologyCompiler` validates drafts and produces immutable compiled
  Ontology schemas without registry, storage, filesystem, network, or process effects;
- Ontology schema evolution produces deterministic change classification and diagnostics;
- Ontology package artifacts and deployment profiles use content digests and exact locks;
- Harness owns workspace read/write/edit, process execution, tool policy, approval, sandbox, resource,
  extension, and runtime composition mechanisms;
- Coding owns coding-specific Product composition, AI coding behavior, LSP, architecture analysis,
  CLI, SDK, and TUI surfaces.

The missing boundary is not another Agent prompt. The repository lacks an accepted Application Model,
canonical Application IR, Target Profile, generator protocol, ArtifactPlan, migration planner,
materializer, conformance verifier, and generated-artifact ownership contract.

## 3. Ownership

The proposed `application` owner is responsible for:

- Application Package draft and compiled value contracts;
- bindings from application interactions to stable Ontology semantic IDs;
- pure validation and compilation to a canonical Application IR;
- target capability requirements and Target Profile validation;
- deterministic ArtifactPlan, MigrationPlan, and ConformancePlan values;
- Target Backend protocol and detached output conformance checks;
- diagnostics and compatibility classification for application changes.

It does not own:

- Ontology Schema, Facts, source authority, projection, or Action execution;
- Product identity, organization, authorization, credentials, or audit decisions;
- enterprise process-instance execution;
- filesystem mutation, process execution, Git, sandbox, approval, or Agent loops;
- Coding prompts, sessions, tools, LSP runtime, or TUI;
- concrete vendor connectors or production deployment.

## 4. Requirements

| ID | Requirement |
| --- | --- |
| APP-FR-001 | Every semantic binding resolves by stable Ontology semantic ID against exact locked Schema identities. |
| APP-FR-002 | The compiler returns all deterministic diagnostics in a stable order and produces no partial compiled model on error. |
| APP-FR-003 | Equivalent canonical input produces byte-identical canonical plans and digests. |
| APP-FR-004 | Application fields may add interaction constraints but cannot mutate the referenced Property definition. |
| APP-FR-005 | The compiler validates target capabilities before invoking or selecting any Target Backend. |
| APP-FR-006 | Generated artifacts identify ownership zone, semantic inputs, target backend, compiler identity, and content digest. |
| APP-FR-007 | Extension requirements are explicit contracts; missing implementations fail conformance rather than silently receiving generated stubs that appear complete. |
| APP-FR-008 | Model evolution reports application, target, API, process, policy, data, and migration impact where the required inputs are present. |
| APP-FR-009 | Artifact materialization can be repeated into an empty workspace without consulting an LLM. |
| APP-FR-010 | Generated-artifact drift is detected and never adopted as model truth automatically. |
| APP-FR-011 | Target Backend output is checked against the exact ArtifactPlan before it can enter a manifest. |
| APP-FR-012 | Coding and AI can contribute extensions only through declared ownership zones and contracts. |

## 5. Application Model

### 5.1 Package

A conceptual package shape is:

```text
ApplicationPackageDraft
  package_id
  namespace
  version
  ontology_dependencies
  query_views
  forms
  object_views
  action_interactions
  agent_tool_bindings
  process_interactions
  navigation
  metadata
```

The compiler produces a detached immutable `CompiledApplicationPackage` whose Ontology references are
resolved to exact Schema identities and semantic IDs.

### 5.2 QueryView

`QueryView` defines a reusable observation contract:

```text
query_view_id
root object or interface semantic ID
selected properties and links
filter and sort capabilities
aggregation capabilities
required authorization capability reference
presentation-neutral result shape
```

The portable definition does not embed SQL, a search-engine query, or a vendor-specific API call. A
Target Backend may compile it only when the selected query provider declares the required capability.

### 5.3 Form And FieldBinding

`Form` is an ordered interaction composition. `FieldBinding` binds one interaction field to a Property,
Action parameter, Query parameter, or explicitly declared transient value.

```text
Form
  form_id
  purpose = create | edit | action | search | process-task
  target semantic or Action ID
  fields
  layout hints
  validation bindings
  submit interaction

FieldBinding
  field_id
  semantic reference
  value direction
  required / read-only / visibility policy references
  formatter / parser capability
  presentation hints
```

`field_id` is stable inside the Application Package but is not a substitute for a Property semantic ID.
Presentation hints remain optional and target-neutral where possible.

### 5.4 ActionInteraction

`ActionInteraction` connects one published Action to a human or application surface:

```text
action semantic ID
parameter bindings
confirmation and reason requirements
success/failure presentation
policy and process requirement references
bulk or single-target behavior
```

The interaction cannot weaken Action parameter validation or Product authorization. Hiding a button is
not an enforcement mechanism.

### 5.5 AgentToolBinding

`AgentToolBinding` describes how a selected Query or Action is exposed as a tool:

```text
stable tool identity
semantic Query or Action reference
input/output projection
description and examples
required scopes and policy references
delegation and runtime-context requirements
```

The binding generates a tool contract, not a privileged executor. MCP, Agent SDK, or Product Tool
handlers route through the normal Product Query or Action boundary.

### 5.6 ProcessInteraction

`ProcessInteraction` binds a process activity to:

- a versioned Form or ActionInteraction;
- participant input and output mappings;
- field visibility or edit policy references;
- semantic Actions that may complete or reject the task;
- process-provider capability requirements.

Portable process meaning does not embed an engine page URL, database task table, or mutable workflow
instance identifier.

## 6. Canonical Application IR

The compiler should normalize drafts and exact dependencies into a canonical IR before target planning:

```text
CompiledApplicationModel
  identity
  resolved_schema_dependencies
  normalized interactions
  normalized bindings
  capability requirements
  dependency graph
  compatibility metadata
```

Canonicalization requirements include:

- stable ordering independent of draft input order where order has no semantic meaning;
- preserved explicit order for fields, layout sequences, and process transitions where order matters;
- canonical strict JSON representation;
- no lazy lookup into a mutable registry during planning;
- no credentials, local paths, timestamps, random identifiers, or machine-specific defaults;
- no model-provider output embedded without first becoming reviewed package content.

## 7. Compilation Pipeline

```text
1. Validate package syntax and local identity
2. Validate exact dependency locks
3. Resolve semantic references
4. Validate value and cardinality compatibility
5. Validate interaction and Action parameter bindings
6. Validate policy/process references structurally
7. Normalize to canonical Application IR
8. Compare with the prior compiled Application model, when supplied
9. Select and validate Target Profile capabilities
10. Ask each Target Backend for a deterministic plan
11. Merge plans and reject path, identity, or ownership conflicts
12. Emit ArtifactPlan, MigrationPlan, ConformancePlan, and diagnostics
```

All diagnostics should carry stable code, severity, package identity, semantic path, optional target,
and an actionable message. Warning acceptance is a review decision outside the pure compiler.

## 8. Target Profile

A Target Profile locks capabilities rather than assuming one technology stack:

```text
TargetProfile
  profile_id and version
  backend targets
  database target and dialect
  API target
  UI renderer target
  MCP/SDK targets
  process provider contract
  identity and authorization provider contracts
  file layout profile
  runtime compatibility constraints
  exact Target Backend artifact locks
```

Secrets, live endpoints, workspace paths, and mutable environment configuration are referenced at
Product deployment time, not embedded in the Target Profile.

## 9. Target Backend Protocol

A backend should be a deterministic planner over immutable values:

```text
TargetBackend
  identity() -> BackendIdentity
  capabilities() -> CapabilitySet
  validate(model, target_profile) -> Diagnostics
  plan(model, target_profile, prior_manifest?) -> BackendArtifactPlan
  validate_output(plan, detached_output) -> ConformanceReport
```

The protocol does not give the backend unrestricted filesystem or process access. A backend may return
canonical file content or content-addressed template/render instructions only if the plan fully
determines the resulting digest.

Backends declare supported semantic types, relationship shapes, Action effects, query operations,
layout hints, migration operations, and runtime provider requirements. Unsupported capabilities fail
closed with diagnostics.

## 10. Artifact Contracts

### 10.1 ArtifactPlan

A conceptual value is:

```text
ArtifactPlan
  format
  compiler_identity
  input_locks
  target_profile_lock
  artifacts[]
  extension_requirements[]
  diagnostics[]
  plan_digest

PlannedArtifact
  logical_id
  path
  kind
  ownership = generated | contract | extension | manifest
  generator_backend
  semantic_inputs
  content_digest or required implementation contract
  dependencies
```

Paths are normalized relative paths inside a declared output root. Absolute paths, parent traversal,
duplicate case-folded paths on case-insensitive targets, and conflicting owners are rejected.

### 10.2 MigrationPlan

`MigrationPlan` separates generation from execution:

```text
schema operations
data transformation requirements
compatibility classification
preconditions
validation queries or checks
rollback or recovery requirements
manual approval requirements
```

The compiler never executes DDL. Destructive, lossy, or authority-changing operations require explicit
review and Product authorization. AI may propose a transformation implementation but cannot change the
classified operation silently.

### 10.3 ConformancePlan

`ConformancePlan` identifies evidence required before publication:

```text
canonical regeneration check
generated-file digest check
extension interface completeness
schema and API compatibility tests
UI binding tests
MCP schema and routing tests
authorization enforcement-point tests
process binding tests
migration pre/post-condition tests
target-specific build, typecheck, lint, and test commands
```

Commands are descriptions consumed by an authorized build Product. The compiler does not execute them.

## 11. Artifact Families

### 11.1 Database

Deterministic base generation may include tables, columns, relationship tables, keys, constraints,
indices, projection schemas, and migration operations. Physical mapping is selected by Target Profile;
an Ontology ObjectType is not automatically a table.

AI or human extensions implement data conversion and backfill functions behind migration contracts.

### 11.2 API

The compiler may derive request/response schemas, route contracts, typed errors, OpenAPI, authorization
checkpoints, and SDK input. Domain Action handlers remain extension implementations unless their effects
are completely represented by an accepted deterministic effect definition.

### 11.3 UI

The compiler may derive renderer-neutral Form/List/ObjectView schemas and standard target components.
Special components and product-specific interaction behavior remain extensions. UI visibility never
replaces server-side authorization.

### 11.4 MCP And SDK

The compiler may generate type-safe Query and Action clients, MCP tool schemas, policy requirement
references, and Product routing adapters. Generated tools never obtain direct database or FactStore
write access.

### 11.5 Process

The compiler may emit portable process artifacts and provider bindings. A Product-hosted process
provider owns running instances, tasks, timers, recovery, and provider-specific storage.

### 11.6 Tests And Documentation

Generated tests prove binding, compatibility, permission checkpoints, routing, and regeneration.
Generated documentation records semantic references, API/tool contracts, lineage, target choices, and
manifest identity. Domain examples and operational guidance remain authored content.

## 12. Materializer And Build Product

The pure compiler should not write files. A Product build composition consumes an ArtifactPlan and:

1. validates the output root and plan digest;
2. acquires an isolated workspace or worktree;
3. materializes generated and contract artifacts atomically;
4. preserves extension-owned paths;
5. reports missing extension requirements;
6. invokes authorized build and conformance commands;
7. collects structured results and content digests;
8. emits an Artifact Manifest only after conformance succeeds.

Workspace mutation, process execution, policy, approval, sandbox, output truncation, and cancellation
should reuse Harness public contracts. This reuse does not make Harness or Coding the owner of
Application semantics.

## 13. Coding And AI Integration

The first implementation may mount an `ontology_app_build` capability in Coding:

```text
compile_application
inspect_application_diff
plan_artifacts
materialize_generated_artifacts
list_extension_requirements
verify_artifacts
run_conformance
```

The normal repair loop is:

```text
Compiler produces deterministic plans
  -> Materializer writes generated and contract zones
  -> Coding Agent implements extension requirements
  -> Harness executes build, lint, typecheck, and tests
  -> coding.lsp supplies code diagnostics
  -> coding.arch checks declared dependency boundaries
  -> Coding Agent repairs extension code
  -> Conformance Verifier checks exact contracts and digests
  -> Product emits manifest for review
```

Coding must not edit the compiled model or generated zone merely to make a test pass. A required change
to semantics returns to a reviewed model change and a new compiler run.

Long term, a Studio or another Product may consume the same compiler and Harness mechanisms without
depending on Coding-specific prompts, sessions, or UI.

## 14. Evolution And Drift

Application evolution should compare exact prior and next compiled values and classify at least:

```text
compatible metadata change
compatible additive interaction
behavioral interaction change
breaking application contract
target capability change
generated API/tool change
process or policy impact
data migration impact
manual review required
```

Generated drift handling is fail-closed:

- unchanged generated content is replaced or verified deterministically;
- a changed generated file whose digest no longer matches the prior manifest is reported as drift;
- drift is never imported automatically into the Application Model;
- users may discard drift, move intentional behavior into an extension, or propose an explicit model
  change;
- manifest publication fails while unexplained generated drift exists.

## 15. Failure Semantics

The boundary distinguishes:

- invalid package or unresolved semantic reference;
- incompatible binding or value shape;
- unsupported target capability;
- backend planning failure;
- cross-backend artifact conflict;
- unsafe or incomplete migration;
- materialization path or ownership violation;
- missing extension implementation;
- build, typecheck, lint, or test failure;
- detached output digest or conformance mismatch;
- generated drift;
- publication or deployment failure outside the compiler.

A compiler or backend exception does not authorize partial output. Product may retain diagnostics and a
failed workspace for inspection, but it must not publish a successful Artifact Manifest.

## 16. Intended Dependencies

```text
application.model ----------> ontology schema identities and JSON foundation
application.compiler -------> application.model + ontology package artifacts
application.targets.* ------> application compiler public backend contracts

product.build --------------> application compiler + harness workspace/process contracts
coding Product -------------> product.build + harness/agent/ai public contracts

application ----------------X-> coding / Agent / AI / TUI / credentials / vendor SDK
application.compiler -------X-> filesystem / subprocess / network / registry mutation
ontology -------------------X-> application / product.build / coding
harness --------------------X-> application semantic contracts
```

If target backends are independently packaged, Product owns their discovery, admission, locking, and
execution composition. The pure compiler consumes already admitted immutable backend values.

## 17. First Slice

The first slice should support exactly one target combination:

```text
Ontology input
  object/property/link + narrow Actions

Application input
  one QueryView, one create/edit Form, one ActionInteraction, one AgentToolBinding

Targets
  one database dialect
  one Python backend/API stack
  one web renderer
  one MCP transport adapter
  generated pytest-style conformance
```

Required acceptance evidence:

1. Compiling the same locked inputs twice yields identical canonical plans and generated digests.
2. One Ontology Property is reused by database, API, UI, MCP, and test artifacts.
3. Renaming a display label does not change the semantic binding or physical migration unexpectedly.
4. Removing or changing a Property reports every affected interaction and artifact.
5. Generated files can be deleted and recreated byte-identically.
6. Manual edits to generated files are detected as drift.
7. A missing Action extension fails conformance with a structured diagnostic.
8. Coding can implement the extension without modifying compiler or generated ownership zones.
9. LSP, architecture, build, and test failures prevent manifest publication.
10. The compiler can be invoked without creating a Coding Session or contacting a model provider.

## 18. Non-Goals

- A visual Studio in the first compiler slice.
- A generic low-code runtime that interprets arbitrary mutable drafts in production.
- A generator for every language, framework, database, or workflow engine.
- AI-authored whole-application output without deterministic base contracts.
- Automatic reverse engineering of a business Ontology from physical schemas without review.
- Compiler-owned filesystem, subprocess, network, secrets, deployment, or production migration.
- Treating generated code, form field IDs, physical columns, or process node IDs as semantic authority.

## 19. Open Decisions

1. Final package name and whether `application` is a top-level subsystem or a Product-neutral library
   owned by a future Product architecture.
2. Exact Application Package serialization and stable identity rules.
3. Whether transient Form values are package-defined types or only renderer-local values.
4. The portable expression and validation language, if any; arbitrary JavaScript is not assumed.
5. The Target Backend packaging, compatibility, admission, and lock protocol.
6. Whether plans contain canonical content bytes or only content-addressed renderer inputs.
7. Artifact manifest owner, persistence, retention, signing, and supply-chain metadata.
8. Build evidence integration with HarnessWork versus a dedicated Product build ledger.
9. The first process and authorization provider contracts.
10. Branching, proposals, registry publication, release promotion, and rollback.

These decisions require separate review. This proposal does not authorize new package structure or
implementation work by itself.
