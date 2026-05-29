# 元框架适配机制：方法论如何映射到元阶段与元角色

## 概述

Loushang 的元框架（Meta-Framework）提供了一套**抽象的价值流结构**，但具体的方法论可以**灵活适配**这个结构。

```
┌─────────────────────────────────────────────────────────────┐
│                      元层 (Meta)                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │  PLAN   │  │ EXPLORE │  │ DESIGN  │  │  BUILD  │        │
│  │(PLANNER)│  │(EXPLORER)│  │(DESIGNER)│  │(DELIVER)│       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│                                                             │
│  元阶段 = 价值流的检查点（WHAT 检查点存在）                  │
│  元角色 = 认知模式（WHO 来思考）                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 实例化
┌─────────────────────────────────────────────────────────────┐
│                    具体方法论层                               │
│                                                             │
│  软件/TDD:                                                  │
│    PLAN(理解需求) → EXPLORE(探索测试策略) → DESIGN(设计接口) │
│    → BUILD(红绿重构循环) → VERIFY(测试覆盖)                  │
│                                                             │
│  咨询/方案设计:                                              │
│    PLAN(诊断问题) → EXPLORE(研究行业) → DESIGN(方案框架)     │
│    → BUILD(PPT制作) → VERIFY(内部评审)                       │
│                                                             │
│  内容/写作:                                                  │
│    PLAN(选题策划) → EXPLORE(资料收集) → DESIGN(内容结构)     │
│    → BUILD(撰写内容) → VERIFY(编辑审核)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**：元框架是"骨架"，方法论是"血肉"。骨架固定，血肉可变。

---

## 适应机制 1：阶段映射（可跳过/合并）

元阶段不是**必须全部执行**，而是**按需选用**：

```yaml
# 简单方法论：阶段合并
methodology: code-review
phases:
  - PLAN:          # 理解审查目标（5分钟）
      skip-if: "目标已明确"

  - EXPLORE:       # 探索代码（快速浏览）
      merge-with: PLAN  # 可以合并

  - DESIGN:        # 跳过设计阶段
      skip: true   # 代码审查不需要设计

  - BUILD:         # 执行审查（写评论）
      main-phase: true

  - VERIFY:        # 确认审查完整性
      duration: "2分钟"
```

```yaml
# 复杂方法论：阶段扩展
methodology: enterprise-architecture
phases:
  - PLAN:
      sub-phases:
        - business-strategy    # 业务战略
        - technology-strategy  # 技术战略

  - EXPLORE:
      duration: "2周"  # 可以很长

  - DESIGN:
      sub-phases:
        - conceptual-architecture   # 概念架构
        - logical-architecture      # 逻辑架构
        - physical-architecture     # 物理架构

  - BUILD:
      sub-phases:
        - pilot-implementation      # 试点实施
        - rollout-planning          # 推广规划

  - VERIFY:
      sub-phases:
        - architecture-review       # 架构评审
        - compliance-check          # 合规检查
```

---

## 适应机制 2：角色变体（领域特化）

元角色是**认知模式**，具体方法论定义**角色变体**：

```yaml
# 元角色：DESIGNER（设计结构）
meta-role: DESIGNER
essence: "设计结构，组织系统"

# 软件领域变体
variant: software/architect
name: 架构师
focus: "系统组件、接口、数据流"
tools: [diagram, code-review, prototype]
output: [architecture-doc, c4-diagrams]

# 咨询领域变体
variant: consulting/solution-designer
name: 方案设计师
focus: "方案框架、Storyline、逻辑结构"
tools: [ppt, workshop, interview]
output: [solution-framework, storyline]

# 产品领域变体
variant: product/product-designer
name: 产品设计师
focus: "功能架构、用户流程、交互设计"
tools: [figma, prototype, user-testing]
output: [prd, user-flow, wireframe]

# 内容领域变体
variant: content/content-designer
name: 内容设计师
focus: "内容结构、叙事逻辑、案例安排"
tools: [outline, storyboard, research]
output: [content-outline, narrative-structure]
```

**关键**：变体继承元角色的**认知模式**（HOW TO ORGANIZE），但具体**方法、工具、输出**完全不同。

---

## 适应机制 3：适用性声明（运行时选择）

每个方法元声明**何时适用**，Loushang 自动匹配：

```yaml
# methods/software/task/tdd/SKILL.md
task: tdd
name: 测试驱动开发

applicability:
  when:
    - "需要长期维护的生产代码"
    - "复杂业务逻辑开发"
    - "团队协作项目"
  whenNot:
    - "一次性原型/脚本"
    - "探索性研究"
    - "紧急热修复"

  complexity: standard    # quick | standard | deep
  team-size: [2, 10]     # 适合的人数范围
  lifecycle: [new-feature, refactoring]

  # 与其他方法元的互斥/依赖
  conflicts-with: [prototype-first]  # 不能同时使用
  requires: [unit-testing-framework] # 需要的前提条件
```

运行时会自动评估：
```bash
loushang execute "实现登录功能"
# → 自动匹配到 software/task/tdd（因为符合 applicability）
```

---

## 适应机制 4：组合与编排

复杂方法论可以**组合**多个简单方法元：

```yaml
# 跨域组合示例：数字化转型咨询
methodology: digital-transformation

components:
  # 业务部分
  - method: business/strategy/lean-change
    phases: [PLAN, EXPLORE]
    weight: 0.3

  # 技术部分
  - method: software/design/domain-driven
    phases: [DESIGN, BUILD]
    weight: 0.4

  # 人员部分
  - method: people/change-management/communication
    phases: [PLAN, BUILD, VERIFY]
    weight: 0.3

# 编排策略
orchestration: parallel-with-feedback-loops

# 阶段间的数据传递
handoffs:
  - from: business/strategy/lean-change
    to: software/design/domain-driven
    data: "业务领域划分 → 限界上下文"

  - from: software/design/domain-driven
    to: people/change-management/communication
    data: "技术变更范围 → 变革影响评估"
```

---

## 适应机制 5：温度与风格自适应

同一方法论可以根据**上下文**调整执行风格：

```yaml
# 温度映射
temperature:
  PLAN: 0.6      # 平衡（理解价值）
  EXPLORE: 0.8   # 高（创新探索）
  DESIGN: 0.5    # 中（谨慎设计）
  BUILD: 0.2     # 低（严格实现）
  VERIFY: 0.1    # 最低（客观验证）

# 风格变体
style-variants:
  startup-mvp:    # 初创公司MVP
    skip: [EXPLORE]           # 跳过探索
    merge: [PLAN, DESIGN]     # 合并规划与设计
    temperature-offset: +0.2  # 整体更激进

  enterprise:     # 企业级
    expand: [DESIGN]          # 扩展设计阶段
    add: [compliance-check]   # 增加合规检查
    temperature-offset: -0.1  # 整体更保守
```

---

## 实际示例：不同方法论如何映射

| 方法论 | PLAN | EXPLORE | DESIGN | BUILD | VERIFY |
|--------|------|---------|--------|-------|--------|
| **TDD 编程** | 理解需求 | 探索测试策略 | 设计接口 | 红绿重构 | 测试覆盖 |
| **代码审查** | 理解审查目标 | 快速浏览代码 | -（跳过）| 写审查评论 | 确认完整性 |
| **架构设计** | 战略意图 | 技术调研 | 概念→逻辑→物理架构 | 架构文档 | 架构评审 |
| **咨询方案** | 问题诊断 | 行业研究 | 方案框架设计 | PPT制作 | 内部评审 |
| **内容创作** | 选题策划 | 资料收集 | 内容结构设计 | 撰写内容 | 编辑审核 |
| **Bug修复** | 理解现象 | 根因分析 | 修复方案 | 实施修复 | 回归测试 |
| **数据分析** | 理解业务问题 | 探索数据 | 分析框架 | 执行分析 | 结果验证 |

---

## 总结

元框架与具体方法论的关系：

| 元层 | 方法论层 | 说明 |
|------|----------|------|
| 5 元阶段 | 可跳过/合并/扩展 | 阶段是检查点，不是必须执行的步骤 |
| 5+1 元角色 | 角色变体 | 认知模式固定，具体职责可变 |
| 价值流 | 具体流程 | 从理解价值到交付价值的逻辑不变 |
| 温度梯度 | 风格调整 | 根据场景调整执行的严谨程度 |

> **元阶段和元角色是"空容器"，具体方法论决定"装什么内容"。**
>
> 就像 **HTTP 方法（GET/POST/PUT/DELETE）** 是固定的，但每个 API 的具体 **Request/Response** 完全不同——框架提供结构，内容自由填充。

---

*版本: Methodology Adaptation v1.0*
