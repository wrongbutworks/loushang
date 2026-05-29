# Methodology Orchestration Extension: Multi-Agent Collaboration

> **Experimental**: Extension to Loushang's meta-methodology system to define how multiple agents collaborate. Supports both **fixed** (predefined) and **autonomous** (LLM-planned) execution modes.
>
> **Core Principle**: Meta-framework (5 phases + 5+1 roles + temperature) is the fixed skeleton. Specific methodologies are the flesh — they can be rigid recipes or flexible capability declarations that CONDUCTOR dynamically composes.

---

## Two Modes of Execution

Loushang supports both execution modes, selectable per project or per task:

| Dimension | Fixed Mode | Autonomous Mode |
|-----------|-----------|-----------------|
| **Flow control** | Predefined in methodology file | CONDUCTOR dynamically plans at runtime |
| **Role assignment** | Fixed to specific roles | CONDUCTOR selects from `required_roles` pool |
| **Task ordering** | Sequential / parallel / handoff declared explicitly | CONDUCTOR generates dependency graph |
| **Adaptability** | Low — follows recipe | High — adapts to context, can skip/merge/add tasks |
| **Use case** | Well-understood domains (TDD, code review) | Novel / complex / cross-domain projects |
| **Audit** | Easy — deviation is an error | Easy — plan + decision log is recorded |

**A methodology file declares which mode(s) it supports.** A project can use fixed mode for some phases and autonomous mode for others.

---

## Methodology Definition Structure (Unified)

```yaml
# methods/software/methodology/tdd/SKILL.md
methodology: tdd
name: Test-Driven Development
version: "1.0.0"

# ── Meta alignment ──
meta:
  phases: [PLAN, BUILD, VERIFY]           # Which meta-phases this method covers
  primary_role: DELIVER                   # Primary executor role
  temperature_profile:
    PLAN: 0.5
    BUILD: 0.2
    VERIFY: 0.1

# ── Mode declaration ──
execution_mode: fixed                     # fixed | autonomous | hybrid

# ── Capability declaration (used by both modes) ──
applicability:
  domains: [software, backend, frontend]
  complexity: [quick, standard]
  when:
    - "需要长期维护的生产代码"
    - "复杂业务逻辑开发"
  when_not:
    - "一次性原型/脚本"
    - "紧急热修复"

required_roles:
  - DELIVER.implementor
  - VALIDATOR.tester

suggested_tasks:
  - task: write-failing-test
    description: "编写一个会失败的测试"
    estimated_duration: "5min"
  - task: write-minimal-code
    description: "编写最少代码让测试通过"
    estimated_duration: "10min"
  - task: refactor
    description: "重构代码，保持测试通过"
    estimated_duration: "10min"

work_products:
  - type: test-suite
    description: "完整的测试集合"
  - type: production-code
    description: "通过所有测试的生产代码"

constraints:
  - "测试必须先于实现代码"
  - "重构时测试必须保持通过"

orchestration_hints:                      # Non-binding suggestions for CONDUCTOR
  - "write-failing-test → write-minimal-code → refactor 必须严格顺序执行"
  - "循环执行直到功能完成"
```

### Mode-Specific Extensions

#### Fixed Mode: Explicit Orchestration

When `execution_mode: fixed`, the methodology **must** declare the full orchestration:

```yaml
execution_mode: fixed

orchestration:
  strategy: sequential                    # sequential | parallel | handoff | swarm | hybrid
  
  phases:
    - phase: PLAN
      mode: sequential
      tasks:
        - task: understand-requirements
          role: PLANNER.scoper
          
    - phase: BUILD
      mode: sequential
      loop: until-feature-complete        # Loop this phase
      tasks:
        - task: write-failing-test
          role: DELIVER.implementor
        - task: write-minimal-code
          role: DELIVER.implementor
        - task: refactor
          role: DELIVER.implementor
          
    - phase: VERIFY
      mode: sequential
      tasks:
        - task: run-test-suite
          role: VALIDATOR.tester
          
  handoffs:
    - from: phase/BUILD
      to: phase/VERIFY
      contract: all-tests-pass
      fallback: return-to-phase/BUILD
```

**Characteristics of fixed mode**:
- Orchestrator executes the declared plan exactly
- Deviation is an error (or requires human override)
- Suitable for: TDD, code review checklists, compliance audits

#### Autonomous Mode: Capability Declaration Only

When `execution_mode: autonomous`, the methodology **only** declares capabilities and constraints. CONDUCTOR plans at runtime:

```yaml
execution_mode: autonomous

# No orchestration section — CONDUCTOR generates it dynamically
# But richer capability hints help CONDUCTOR plan better

capability_hints:
  # What this method is good at
  strengths:
    - "保证代码质量"
    - "提供可回归的测试覆盖"
    
  # What it needs from other methods
  dependencies:
    - method: software/design/system-architecture
      reason: "TDD 需要先有接口设计"
      
  # Typical collaboration patterns
  typical_orchestration:
    - "通常与 system-design 方法顺序使用"
    - "可与 code-review 方法并行执行"
    
  # Expected human intervention points
  human_gates:
    - "当测试覆盖率低于阈值时需要人确认"
    - "当重构涉及公共接口时需要人确认"
```

**Characteristics of autonomous mode**:
- CONDUCTOR generates execution plan dynamically
- Plan is recorded for audit but can change mid-flight
- Suitable for: novel projects, cross-domain work, R&D exploration

#### Hybrid Mode: Fixed Skeleton + Autonomous Flesh

```yaml
execution_mode: hybrid

orchestration:
  # Fixed backbone
  phases:
    - phase: PLAN
      mode: fixed                         # Must follow predefined steps
      tasks:
        - task: understand-requirements
          role: PLANNER.scoper
          
    - phase: EXPLORE
      mode: autonomous                    # CONDUCTOR decides how to explore
      constraint: "must produce at least 2 alternatives"
      required_roles: [EXPLORER]
      
    - phase: DESIGN
      mode: fixed
      tasks:
        - task: select-solution
          role: DESIGNER.architect
          human_gate: confirm             # Human must confirm the choice
        - task: detailed-design
          role: DESIGNER.detailed-designer
          
    - phase: BUILD
      mode: autonomous
      required_roles: [DELIVER]
      constraint: "must follow selected design"
      
    - phase: VERIFY
      mode: fixed
      tasks:
        - task: run-tests
          role: VALIDATOR.tester
        - task: security-scan
          role: VALIDATOR.security-expert
```

---

## Cross-Domain Method Composition

Because CONDUCTOR plans dynamically, methods from different domains can be composed:

```yaml
# Project: "Digital Transformation Consulting"
# Combines business + software + content methods

project_method:
  composition_mode: autonomous
  
  available_methods:
    - consulting/strategy/digital-transformation
    - business/analysis/market-research
    - software/design/system-architecture
    - content/writing/ppt-design
    - people/change-management/communication
    
  # CONDUCTOR dynamically selects and orders based on project context
```

**CONDUCTOR's decision process**:

```
Input: "帮我们制定数字化转型方案，需要给CEO汇报"

CONDUCTOR analysis:
  - This involves: strategy diagnosis (business) + system design (software) + presentation (content)
  - CEO audience → high-level, business-focused
  - Digital transformation → change management required

Generated plan:
  Phase 1 (PLAN): consulting/strategy/digital-transformation
    → Role: PLANNER.strategy-consultant
    → Output: problem-diagnosis.md
    
  Phase 2 (EXPLORE): business/analysis/market-research
    → Role: EXPLORER.market-analyst
    → Output: competitive-landscape.md
    
  Phase 3 (DESIGN): software/design/system-architecture
    → Role: DESIGNER.solution-architect
    → Output: target-architecture.md
    
  Phase 4 (BUILD): content/writing/ppt-design
    → Role: DELIVER.presentation-designer
    → Input: [problem-diagnosis, competitive-landscape, target-architecture]
    → Output: ceo-presentation.pptx
    
  Phase 5 (VERIFY): people/change-management/communication
    → Role: VALIDATOR.change-advisor
    → Output: stakeholder-readiness-report.md
```

---

## Runtime Execution Plan Format

Whether fixed or autonomous, the runtime generates a structured execution plan:

```json
{
  "plan_id": "plan-20260504-001",
  "methodology": "tdd",
  "execution_mode": "fixed",
  "generated_by": "CONDUCTOR",
  "generated_at": "2026-05-04T10:00:00Z",
  "phases": [
    {
      "phase": "BUILD",
      "mode": "sequential",
      "loop": "until-feature-complete",
      "tasks": [
        {
          "task_id": "t1",
          "task": "write-failing-test",
          "role": "DELIVER.implementor",
          "agent_instance": "agent-deliver-001",
          "status": "completed",
          "output": "test_user_auth.py",
          "started_at": "...",
          "completed_at": "..."
        },
        {
          "task_id": "t2",
          "task": "write-minimal-code",
          "role": "DELIVER.implementor",
          "agent_instance": "agent-deliver-001",
          "status": "in_progress",
          "depends_on": ["t1"]
        }
      ]
    }
  ],
  "decision_log": [
    {
      "timestamp": "...",
      "decision": "selected fixed mode for TDD",
      "reason": "TDD is well-understood, predefined flow optimal",
      "confidence": 0.95
    }
  ]
}
```

This plan is:
- **Audit trail**: Full record of what was planned and why
- **Reproducible**: Re-run the same plan for the same inputs
- **Comparable**: Compare fixed vs autonomous plans for the same task
- **Evolvable**: Feed plan outcomes back to improve CONDUCTOR

---

## CONDUCTOR's Role in Each Mode

| Function | Fixed Mode | Autonomous Mode |
|----------|-----------|-----------------|
| **Plan generation** | Validates fixed plan against context | Generates plan from scratch |
| **Deviation handling** | Error or human override | Adapts plan dynamically |
| **Role selection** | Validates fixed role assignments | Selects from `required_roles` pool |
| **Task ordering** | Validates declared order | Generates dependency graph |
| **Human gates** | Triggers at declared points | Decides when human input needed |
| **Method composition** | Validates composition rules | Dynamically composes cross-domain methods |

---

## Backward Compatibility

```yaml
# Legacy methods without execution_mode default to fixed
# Legacy methods without orchestration default to sequential single-agent

execution_mode: fixed                    # default if not specified
orchestration:
  strategy: sequential                   # default if not specified
  phases:
    - phase: BUILD
      mode: sequential                   # default
      tasks: []                          # empty = use suggested_tasks in order
```

---

## Examples by Domain

### Software: TDD (Fixed)
```yaml
methodology: tdd
execution_mode: fixed
orchestration:
  strategy: sequential
  phases:
    - phase: BUILD
      mode: sequential
      loop: until-feature-complete
      tasks: [write-failing-test, write-minimal-code, refactor]
```

### Consulting: Digital Transformation (Autonomous)
```yaml
methodology: digital-transformation
execution_mode: autonomous
required_roles: [PLANNER, EXPLORER, DESIGNER]
suggested_tasks: [stakeholder-interview, as-is-analysis, to-be-design, roadmap]
capability_hints:
  typical_duration: "2-4 weeks"
  human_gates: ["stakeholder-sign-off", "budget-approval"]
```

### Content: PPT Design (Hybrid)
```yaml
methodology: executive-presentation
execution_mode: hybrid
orchestration:
  phases:
    - phase: PLAN
      mode: fixed
      tasks: [understand-audience, define-key-message]
    - phase: DESIGN
      mode: autonomous
      required_roles: [DESIGNER]
      constraint: "must follow corporate-brand-guidelines"
    - phase: VERIFY
      mode: fixed
      tasks: [review-with-stakeholder, final-polish]
```

---

## Open Questions

1. **Mode switching mid-flight**: Can a fixed-mode phase switch to autonomous if unexpected complexity arises?
2. **Plan version control**: How to track plan revisions when autonomous mode adapts dynamically?
3. **Cross-domain method compatibility**: How does CONDUCTOR know which methods can be composed?
4. **Fixed mode rigidity**: Should fixed mode allow optional tasks (e.g., "run security scan if code touches auth")?
5. **Human override scope**: In fixed mode, can humans skip steps? In autonomous mode, can humans impose fixed constraints?

---

*Created: 2026-05-04*
*Depends on: methodology-file-structure.md, methodology-adaptation.md, multi-agent-scenarios.md*
