# Multi-Agent Scenarios Driven by Methodology

> **Experimental**: These scenarios explore how Loushang's methodology system (SPEM 2.0 aligned) combined with the skill system can enable automated, evolvable multi-agent collaboration. Not yet validated by implementation.

---

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Methodology** | Process definition: Phase > Activity > Task > Step (SKILL.md format) |
| **Role** | Execution identity with temperature, tools, and system prompt (5+1 meta-roles) |
| **Skill** | Injectable capability via `skills/{name}/SKILL.md` (system prompt enhancement) |
| **CONDUCTOR** | LLM-based scheduler that decides next role based on context |
| **Soul** | Self-evolving layer: skills auto-precipitate, methodologies auto-optimize, agent preferences adapt |

---

## Scenarios by Collaboration Pattern

### 1. Sequential (Relay)

Agent A completes work → hands off to Agent B → B reviews/modifies → hands off to C.

| # | Scenario | Agent A → Output | Agent B → Output | Agent C → Output |
|---|----------|------------------|------------------|------------------|
| 1 | **Architecture → Review → Revision** | ARCHITECT designs system → `architecture.md` | VALIDATOR reviews → `review-report.md` (issue list) | ARCHITECT revises → `architecture-v2.md` |
| 2 | **Requirements → Tech Selection → Implementation** | PLANNER decomposes → `prd.md` + acceptance criteria | EXPLORER researches 3 options → `tech-comparison.md` | DELIVER implements chosen → code + `api-spec.md` |
| 3 | **Code → Test → Fix** | DELIVER writes feature → PR | VALIDATOR writes tests + runs → `test-report.md` (failures) | DELIVER fixes → PR update |
| 4 | **Bug Report → Root Cause → Fix Verification** | EXPLORER reproduces + analyzes → `root-cause-analysis.md` | DELIVER fixes → PR | VALIDATOR regression tests → `verification-report.md` |
| 5 | **Documentation → Review → Publish** | DELIVER writes draft → `doc-draft.md` | VALIDATOR reviews (accuracy + readability) → `review-comments.md` | DELIVER finalizes → `doc-final.md` |

**Handoff mechanism**: WorkProduct from A becomes input constraint for B. Session may be shared (retain context) or independent (clean slate).

---

### 2. Parallel (Expert Panel)

Multiple agents work simultaneously, results merged by CONDUCTOR.

| # | Scenario | Parallel Agents | Individual Outputs | Merged Output |
|---|----------|-----------------|-------------------|---------------|
| 6 | **Multi-solution Exploration** | EXPLORER.A: solution A → `solution-a.md` | EXPLORER.B: solution B → `solution-b.md` | CONDUCTOR merges → `decision-matrix.md` |
| 7 | **Frontend + Backend Parallel** | DELIVER.backend: API code + `api-spec.yaml` | DELIVER.frontend: UI code | VALIDATOR integration tests → `integration-report.md` |
| 8 | **Security + Performance + Function Parallel Review** | VALIDATOR.security → `security-audit.md` | VALIDATOR.performance → `perf-benchmark.md` | VALIDATOR.function → `test-report.md` | CONDUCTOR merges → `comprehensive-review.md` |
| 9 | **Multi-language Documentation** | DELIVER.zh → `README.zh.md` | DELIVER.en → `README.en.md` | DELIVER.ja → `README.ja.md` | Auto-merge publish |

**Merge strategies**: CONDUCTOR decides based on conflict type — additive (concatenate), selective (pick best), or integrative (synthesize).

---

### 3. Handoff (A's Output Is B's Input)

Explicit contract passing between phases.

| # | Scenario | Agent A Output | Handoff Contract | Agent B Output |
|---|----------|---------------|------------------|----------------|
| 10 | **Architecture → Detailed Design → Implementation** | ARCHITECT: `c4-diagrams.md` + interface contracts | Contract injected as constraint into B's context | DESIGNER: `detailed-design.md` → DELIVER: code |
| 11 | **Data Model → API → Frontend** | DESIGNER: `schema.prisma` | Auto-generated TypeScript types | DELIVER.backend: REST API → DELIVER.frontend: integration code |
| 12 | **Prototype → Visual → Frontend** | DESIGNER: low-fi prototype → `prototype.md` | Visual spec as constraint | DESIGNER.ui: `design-system.md` → DELIVER.frontend: component code |
| 13 | **Code → Deployment → Ops** | DELIVER: app code + `Dockerfile` | Image + config templates | DELIVER.devops: `k8s-manifests.yaml` → auto-deploy |

**Contract types**: OpenAPI spec, Prisma schema, C4 model, design tokens, test assertions.

---

### 4. Swarm (Same Role, Multiple Instances)

Multiple agents with same role tackle sub-tasks in parallel.

| # | Scenario | Swarm Members | Task Split | Merge Result |
|---|----------|--------------|-----------|--------------|
| 14 | **Batch Code Review** | VALIDATOR.1 ~ VALIDATOR.5 | By file/module | Unified `review-report.md` (dedup + priority sort) |
| 15 | **Batch Test Generation** | DELIVER.1 ~ DELIVER.3 | By feature module | `test-suite/` directory |
| 16 | **Multi-file Refactoring** | DELIVER.1 ~ DELIVER.4 | By component boundary | Unified PR (conflict auto-detect) |
| 17 | **Large-scale Data Migration** | DELIVER.1 ~ DELIVER.N | By data shard | Unified migration report |

**Split strategy**: Deterministic (hash-based), semantic (component boundary), or CONDUCTOR-guided (load balancing).

---

### 5. Human-in-the-Loop (Hybrid)

Human intervenes at critical decision points.

| # | Scenario | Agent Action | Human Intervention | Output |
|---|----------|-------------|-------------------|--------|
| 18 | **Option Selection** | EXPLORER generates 3 options → `options.md` | Human selects + comments | ARCHITECT deepens chosen |
| 19 | **Critical Decision Confirmation** | ARCHITECT outputs decision → `adr-001.md` | Human confirms/rejects/modifies | Finalized or returned |
| 20 | **Post-Review Arbitration** | VALIDATOR outputs review → `review.md` | Human judges which issues to fix | DELIVER fixes per arbitration |
| 21 | **Release Approval** | VALIDATOR outputs test report + risk assessment | Human decides release/rollback | Release or abort |
| 22 | **Requirement Clarification** | PLANNER outputs understanding → `req-summary.md` | Human confirms correctness | Proceed to next phase |

**Human interaction = next turn, not tool**: Agent outputs request → loop ends → human inputs via Terminal → new prompt continues session.

---

### 6. Self-Evolution / Meta (Methodology & Skill Evolution)

Agents improve the system itself.

| # | Scenario | Trigger | Executor | Output |
|---|----------|---------|----------|--------|
| 23 | **Skill Auto-Precipitation** | Project delivery complete | EXPLORER.miner + DESIGNER.packer | New Skill: `project-{name}-patterns` |
| 24 | **Methodology Self-Optimization** | Execution history accumulates | CONDUCTOR (self-training) | Adjusted phase order, role temperature, task granularity |
| 25 | **Cross-Project Migration** | New project starts | EXPLORER.mapper + DESIGNER.adapter | Migrated skill set |
| 26 | **Failure Retrospective** | Task fails/rolls back | EXPLORER.analyzer + VALIDATOR.critic | `lessons-learned.md` → updated Guidance |

---

## Output Types Reference

| Output | Format | Storage |
|--------|--------|---------|
| Architecture doc | `architecture.md`, `c4-diagrams.md` | WorkProduct / Git |
| Review report | `review-report.md` | PR comment / Git |
| API contract | `api-spec.yaml`, `openapi.json` | Git |
| Test report | `test-report.md` | CI artifact / Git |
| Decision record | `adr-xxx.md` | `docs/adr/` |
| Skill | `SKILL.md` | `skills/` |
| Code | `.py`, `.ts`, etc. | Git PR |

---

## Open Questions

1. **Session model**: Do sequential agents share one session (context retained) or independent sessions (clean slate)?
2. **Parallel merge**: How does CONDUCTOR resolve conflicts when parallel agents produce contradictory outputs?
3. **Human arbitration**: Should human commands ("stop", "switch role") go through CONDUCTOR or directly interrupt the orchestrator?
4. **Skill evolution**: How does a skill auto-update after each execution without human review?
5. **Audit trail**: How to reconstruct "who did what when" across multiple sessions and role switches?

---

*Created: 2026-05-04*
*Status: Experimental exploration*
