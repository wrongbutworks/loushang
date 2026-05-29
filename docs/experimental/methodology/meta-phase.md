# 元阶段定义（Meta-Phase）

## 概述

楼上的元阶段是**价值流的五个检查点**，不是刚性流水线。它们回答项目执行中最本质的五个问题：

| 阶段 | 核心问题 | 本质 | 元角色 | 温度 |
|------|----------|------|--------|------|
| **PLAN** | WHY? | 理解价值，定义标准 | PLANNER | 0.6 |
| **EXPLORE** | WHAT COULD BE? | 探索可能性 | EXPLORER | 0.8 |
| **DESIGN** | HOW TO ORGANIZE? | 设计结构 | DESIGNER | 0.5 |
| **BUILD** | HOW TO REALIZE? | 构建交付 | DELIVER | 0.2 |
| **VERIFY** | IS VALUE DELIVERED? | 验证价值 | VALIDATOR | 0.1 |

### 关键特性

1. **价值驱动**：从"任务执行"转向"价值交付"
2. **动态调度**：可前进、回退、跳过、循环，由 CONDUCTOR 根据上下文决定
3. **跨领域适用**：不仅适用于软件开发，也适用于咨询、内容创作、产品规划等
4. **SPEM 2.0 对齐**：与 OMG 软件过程工程元模型标准对齐

### 一句话总结

> **元阶段不是刚性流水线，而是价值流的检查点。**

---

## 术语定义（与 SPEM 2.0 对齐）

**方法元**（Method Element）：所有方法论元素的统称，包括 Phase、Activity、Task、Role、Guidance、Workproduct 等。

| 术语 | SPEM 2.0 | 中文 | 定义 |
|------|----------|------|------|
| **Phase** | Phase | **阶段** | 特殊的 Activity，代表价值流的里程碑，以决策检查点结束 |
| **Activity** | Activity | **活动** | 工作单元的执行上下文，引用 Task 并定义步骤 |
| **Step** | Step | **步骤** | Task 的细化执行单元，定义"具体怎么做" |
| **Task** | Task | **任务** | 方法内容，定义"做什么"（输入、输出、前置/后置条件）|
| **Guidance** | Guidance | **指南** | 补充说明"如何做"（最佳实践、检查清单、示例）|
| **Role** | Role | **角色** | 执行者的职责定义（即 5+1 元角色）|
| **Workproduct** | Work Product | **工作产品** | 输入/输出的工件 (简写: wp) |

## 核心设计

**Phase 是一种 Activity**（SPEM 2.0 继承关系），同时**Phase 包含 Activity**（组合关系）。

阶段（Phase）是价值流动的里程碑，不是严格的时间顺序。各阶段可以回退、跳过或循环。

```
┌─────────────────────────────────────────────────────────────┐
│                     价值流阶段（Value Flow）                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    │
│   │  PLAN  │───▶│ EXPLORE│───▶│ DESIGN │───▶│ BUILD  │    │
│   │(理解)  │    │(探索)  │    │(设计)  │    │(构建)  │    │
│   └────────┘    └────────┘    └───┬────┘    └────┬───┘    │
│       ▲            │              │              │        │
│       │            ▼              ▼              ▼        │
│       │       ┌─────────────────────────────────────┐     │
│       └───────│            VERIFY                   │     │
│               │           (验证)                     │     │
│               │   "价值是否实现？否则回到 PLAN"       │     │
│               └─────────────────────────────────────┘     │
│                                                             │
│   CONDUCTOR: 根据上下文决定阶段切换（前进/回退/跳过/重复）   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 三层结构：Phase > Activity > Task > Step

阶段（Phase）不是最细粒度的执行单元，它包含活动（Activity），Activity 引用 Task，Task 包含 Step。

> **SPEM 2.0 对齐**：Step 是 Task 的组成部分，Task 定义"做什么"，Step 定义"具体怎么做"。

```
┌─────────────────────────────────────────────────────────────┐
│                    四层执行结构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase（阶段）                                               │
│  ├── 价值流的里程碑                                          │
│  ├── 由 CONDUCTOR 调度                                     │
│  └── 示例: DESIGN（设计）                                    │
│                                                             │
│       │                                                     │
│       ▼ 包含                                                │
│                                                             │
│       Activity（活动）                                       │
│       ├── 阶段内的原子工作单元                               │
│       ├── 引用 Task 定义工作内容                             │
│       └── 示例: 概要设计、详细设计                           │
│                                                             │
│            │                                                │
│            ▼ 引用                                           │
│                                                             │
│            Task（任务）                                      │
│            ├── 定义"做什么"（输入、输出、约束）              │
│            ├── 包含 Step（执行步骤）                         │
│            └── 示例: architect、detailed-design              │
│                                                             │
│                 │                                           │
│                 ▼ 包含                                      │
│                                                             │
│                 Step（步骤）                                 │
│                 ├── Task 的细化执行单元                      │
│                 ├── 可选（简单 Task 可直接执行）             │
│                 └── 示例: 识别组件、定义接口、绘制架构图      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 层级关系

| 层级 | SPEM 对应 | 说明 | 是否必须 | 调度者 |
|------|-----------|------|----------|--------|
| **Phase** | Phase | 特殊的 Activity，价值流里程碑 | 是 | CONDUCTOR |
| **Activity** | Activity | 阶段内的原子工作单元，引用 Task | 是 | Phase 内顺序执行 |
| **Task** | Task | 方法内容，定义"做什么"（输入/输出/步骤） | 是 | Activity 引用 |
| **Step** | Step | Task 的细化执行单元，定义"具体怎么做" | 否（可选） | Task 内顺序执行 |

### 与 SPEM 2.0 的对齐

```
SPEM 2.0 结构：
├── Method Content（方法内容）
│   ├── Task（任务）         → 定义"做什么"
│   ├── Role（角色）         → 定义"谁做"
│   ├── Work Product（工作产品） → 定义"输入/输出"
│   └── Guidance（指南）     → 定义"如何做"
│
└── Process（过程）
    ├── Phase（阶段）        → 特殊的 Activity，有里程碑
    ├── Activity（活动）     → 引用 Task，定义执行步骤
    └── Step（步骤）         → 具体执行单元

我们的映射：
- Phase = 5 元阶段（PLAN/EXPLORE/DESIGN/BUILD/VERIFY）
- Activity = 阶段内的工作单元，引用 Task
- Task = 方法内容，定义"做什么"，包含 Steps
- Step = Task 的细化执行单元
- Role = 5+1 元角色
```

### 关键原则

1. **Phase 是价值骨架**
   - 必须存在（PLAN → EXPLORE → DESIGN → BUILD → VERIFY）
   - 体现价值流动的逻辑
   - 可在 Phase 间回退、跳过

2. **Activity 是工作单元**
   - 每个 Phase 包含 1 个或多个 Activity
   - 对应 `mechanism/activity/{name}` 方法元
   - Activity 之间可切换（如 DESIGN 阶段的变体切换）

3. **Task 是方法内容的载体**
   - Activity 必须引用 Task（显式或隐式）
   - Task 定义输入、输出、前置/后置条件
   - Task 是"做什么"的抽象，不涉及阶段切换决策

4. **Step 是可选的细化**
   - 简单 Task 无需 Step 分解（如"运行测试"）
   - 复杂 Task 可分解为多个 Steps
   - Step 定义"具体怎么做"

### 示例：DESIGN 阶段的四层结构

```yaml
# ========== Phase 层 ==========
# 文件: methods/phase/DESIGN/SKILL.md
phase: DESIGN
name: 设计阶段
meta-role: DESIGNER

# Phase 包含多个 Activity
contains:
  - activity: architect             # 引用 Activity
    performs: task/architect
    role: DESIGNER.architect

  - activity: detailed-design
    performs: task/detailed-design
    role: DESIGNER.detailed-designer
```

```yaml
# ========== Activity 层 ==========
# 文件: methods/activity/architect/SKILL.md
activity: architect
name: 概要设计

# Activity 引用 Task
performs: task/architect            # 必须引用 Task
role: DESIGNER.architect

# Activity 可覆盖/扩展 Task 的 Steps
steps:
  - step: "识别系统边界"
    duration: "5-10m"
    output: "系统上下文图"

  - step: "划分核心组件"
    duration: "10-15m"
    output: "组件列表及职责"
```

```yaml
# ========== Task 层 ==========
# 文件: methods/task/architect/SKILL.md
task: architect
name: 架构设计

# Task 定义输入/输出
input:
  - "需求文档"
  - "约束条件"
output:
  - "架构图"
  - "接口定义"

# Task 包含 Steps（默认步骤，可被 Activity 覆盖）
steps:
  - step: "理解需求"
    description: "分析功能和非功能需求"

  - step: "识别组件"
    description: "识别系统核心组件"

  - step: "定义交互"
    description: "定义组件间接口和交互"

  - step: "验证设计"
    description: "验证架构是否满足需求"
```

```yaml
# ========== Step 层 ==========
# Step 是 Task 的细化执行单元
# 在 Task 或 Activity 中定义

step: "识别系统边界"
description: "确定系统与外部环境的边界"
duration: "5-10m"
input: "需求文档"
output: "系统上下文图"
tools: ["画图工具"]
```

### 何时需要 Step 细化？

```yaml
step-elaboration-needed:
  required:
    - "Task 预计耗时 > 30 分钟"
    - "涉及多个明确的子步骤"
    - "需要中间检查点"
    - "多人协作需要分工"

  not-required:
    - "Task 简单明确（< 15 分钟）"
    - "是原子性操作（如'运行测试'）"
    - "Activity 已覆盖/扩展了足够的 Steps"

decision: "默认使用 Task 的 Steps，Activity 需要时再细化"
```

### 四层与 SKILL.md 的对应

所有方法元（Phase、Activity、Task、Role、Guidance、Workproduct）都使用统一的 SKILL.md 格式描述：

```
methods/
├── phase/
│   └── design/
│       └── SKILL.md           # Phase 定义（特殊的 Activity）
│
├── activity/
│   └── architect/
│       └── SKILL.md           # Activity 定义（引用 Task）
│
├── task/
│   └── architect/
│       └── SKILL.md           # Task 定义（方法内容）
│
├── role/
│   └── designer/
│       └── SKILL.md           # Role 定义（5+1 元角色）
│
└── guidance/
    └── design-principles/
        └── SKILL.md           # Guidance 定义（指南）
```

---

## 阶段详解

### 1. PLAN（规划）- 理解 WHY

```yaml
phase: PLAN
name: 规划
essence: "理解价值，定义成功标准"
meta-role: PLANNER

duration: "10-30分钟（简单任务可跳过）"

entry:
  trigger: "新任务启动"
  preconditions:
    - "任务描述已提供"
    - "相关上下文已加载"

activities:
  - "理解问题本质"
  - "识别核心价值"
  - "明确成功标准"
  - "制定战略方向"
  - "规划实现路径"

exit-criteria:
  must-have:
    - "问题本质已理解"
    - "成功标准已定义"
  nice-to-have:
    - "实现路径已规划"
    - "风险已识别"

output:
  - "价值主张陈述"
  - "成功标准定义"
  - "约束条件清单"
  - "战略方向（可选）"

next-phases:
  primary: EXPLORE
  skip-if: "需求非常明确，无需探索"
  rollback-to: null  # PLAN 是起点，无回退

temperature: 0.6
```

**关键问题：**
- 我们真正要解决什么问题？
- 对用户/业务的价值是什么？
- 为什么现在做？
- 成功的标准是什么？

---

### 2. EXPLORE（探索）- 发现 WHAT

```yaml
phase: EXPLORE
name: 探索
essence: "探索可能性，发现可行方案"
meta-role: EXPLORER

duration: "15-45分钟（取决于复杂度）"

entry:
  trigger: "PLAN 阶段完成，或发现不确定性"
  preconditions:
    - "价值主张已明确"
    - "约束条件已了解"

activities:
  - "发散思考可能的方案"
  - "研究最佳实践"
  - "快速原型验证"
  - "识别约束和边界"
  - "评估可行性"

exit-criteria:
  must-have:
    - "至少有一个可行方案"
    - "方案的优势/劣势已评估"
  nice-to-have:
    - "多个方案对比"
    - "推荐方案已确定"

output:
  - "可行方案列表"
  - "方案评估报告"
  - "推荐方案（如适用）"
  - "新发现的约束"

next-phases:
  primary: DESIGN
  alternative: PLAN  # 如果发现价值假设不成立
  skip-if: "已有明确方案，无需探索"

temperature: 0.8
```

**关键问题：**
- 有哪些可能的解决方案？
- 还有什么没考虑到？
- 最佳实践是什么？
- 约束条件有哪些？

---

### 3. DESIGN（设计）- 设计 HOW

```yaml
phase: DESIGN
name: 设计
essence: "设计结构，组织系统"
meta-role: DESIGNER

duration: "20-60分钟（可多次迭代）"

entry:
  trigger: "方案已选定，需要设计结构"
  preconditions:
    - "可行方案已确定"
    - "关键约束已识别"

activities:
  - "概要设计：整体结构、组件划分"
  - "详细设计：接口定义、算法选择"
  - "验证设计可行性"
  - "识别设计风险"

# 子阶段（变体切换）
sub-phases:
  - name: 概要设计
    variant: architect | solution-designer | product-designer
    activity: "粗粒度结构定义"
    exit-criteria:
      - "整体结构已定义"
      - "关键接口已识别"
    rollback-to: EXPLORE  # 发现方案不可行

  - name: 详细设计
    variant: detailed-designer
    activity: "细粒度实现设计"
    exit-criteria:
      - "实现细节已明确"
      - "技术可行性已验证"
    rollback-to: 概要设计  # 发现概要设计问题

exit-criteria:
  must-have:
    - "结构设计已完成"
    - "关键接口已定义"
    - "实现方案已明确"
  nice-to-have:
    - "详细设计文档"
    - "风险应对策略"

output:
  - "架构图/结构图"
  - "接口定义"
  - "详细设计文档"

next-phases:
  primary: BUILD
  alternative:
    - EXPLORE  # 设计发现需要重新探索
    - PLAN     # 发现价值假设有问题

temperature: 0.5
```

**关键问题：**
- 如何组织系统/方案？
- 组件/模块如何交互？
- 如何保持灵活性？
- 如何控制复杂度？

---

### 4. BUILD（构建）- 实现 OUTCOME

```yaml
phase: BUILD
name: 构建
essence: "交付价值，实现结果"
meta-role: DELIVER

duration: "取决于任务规模"

entry:
  trigger: "设计已完成，准备实现"
  preconditions:
    - "设计方案已确定"
    - "关键接口已定义"

activities:
  - "编码实现"
  - "单元测试"
  - "问题修复"
  - "文档编写"
  - "集成测试"

exit-criteria:
  must-have:
    - "核心功能已实现"
    - "基本测试已通过"
  nice-to-have:
    - "完整测试覆盖"
    - "文档已完善"

output:
  - "可运行的代码/交付物"
  - "测试用例"
  - "文档"

next-phases:
  primary: VERIFY
  alternative:
    - DESIGN  # 实现发现设计问题
    - EXPLORE # 发现根本性障碍

temperature: 0.2
```

**关键问题：**
- 如何高质量交付？
- 边界条件处理了吗？
- 测试覆盖了吗？
- 价值是否真正交付？

---

### 5. VERIFY（验证）- 验证 VALUE

```yaml
phase: VERIFY
name: 验证
essence: "验证价值，确保质量"
meta-role: VALIDATOR

duration: "10-30分钟"

entry:
  trigger: "构建完成，需要验证"
  preconditions:
    - "交付物已完成"
    - "测试已执行"

activities:
  - "验证实现是否符合设计"
  - "验证是否交付预期价值"
  - "检查边界条件"
  - "评估风险"
  - "确认合规性"

exit-criteria:
  must-have:
    - "实现符合设计"
    - "测试通过"
  nice-to-have:
    - "性能达标"
    - "安全合规"

output:
  - "验证报告"
  - "问题清单（如有）"
  - "通过/不通过决策"

next-phases:
  pass:
    - "任务完成"
    - "进入标准化/推广"
  fail:
    - PLAN     # 价值未实现，重新理解
    - DESIGN   # 实现有问题，重新设计
    - BUILD    # 局部问题，重新实现

# 可选：方法论优化反馈
optional-activities:
  - name: "反馈优化方法论"
    trigger: "发现当前使用的方法论有改进空间"
    action: "使用 meta:packaging 更新方法论"
    output: "更新后的方法论文件"

temperature: 0.1
```

**关键问题：**
- 实现是否符合设计？
- 是否交付了预期价值？
- 用户是否满意？
- 是否达到成功标准？
- **使用的方法论是否需要改进？**

---

## 阶段切换规则

### 正常流程

```
PLAN → EXPLORE → DESIGN → BUILD → VERIFY → 完成
```

### 回退场景

| 当前阶段 | 回退到 | 触发条件 |
|----------|--------|----------|
| EXPLORE | PLAN | 发现价值假设不成立 |
| DESIGN | EXPLORE | 发现需要重新探索方案 |
| DESIGN | PLAN | 发现根本性问题，需重新理解 |
| BUILD | DESIGN | 实现发现设计问题 |
| BUILD | EXPLORE | 遇到根本性技术障碍 |
| BUILD | PLAN | 发现价值无法按预期交付 |
| VERIFY | BUILD | 局部问题，重新实现 |
| VERIFY | DESIGN | 实现偏差，重新设计 |
| VERIFY | PLAN | 价值未实现，重新理解 |

### 跳过规则

```yaml
skip-rules:
  PLAN:
    when: "任务简单且明确"
    to: EXPLORE

  EXPLORE:
    when: "已有明确方案"
    to: DESIGN

  DESIGN:
    when: "简单修改，无需设计"
    to: BUILD
    note: "需谨慎使用"
```

---

## 持续改进闭环：VERIFY 阶段的方法论优化

验证阶段不仅验证交付物，还可选择性地**验证和优化所使用的方法论本身**，形成持续改进的闭环。

### 触发条件

在 VERIFY 阶段，VALIDATOR 会评估：
1. 任务是否成功完成？
2. **使用的方法论是否需要改进？**

以下情况触发方法论优化：
- 发现方法论的步骤缺失或冗余
- 检查清单不够实用
- 输出模板需要调整
- 发现了更好的实践方式

### 反馈优化流程

```
┌─────────────────────────────────────────────────────────────┐
│                     VERIFY Phase                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. 验证交付物是否符合预期                              │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  2. 评估方法论有效性（可选）                            │  │
│  │     - 哪些步骤有效？                                    │  │
│  │     - 哪些需要改进？                                    │  │
│  │     - 有什么新发现？                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼ 如果发现改进点                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  3. 启用 meta:packaging 更新方法论                      │  │
│  │     - 自动分析本次执行偏差                              │  │
│  │     - 生成方法论改进建议                                │  │
│  │     - 用户确认后更新 SKILL.md                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  4. 版本记录                                             │  │
│  │     - 版本号 +1（语义化版本）                            │  │
│  │     - 记录改进原因                                       │  │
│  │     - 更新 changelog                                     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### CLI 集成

```bash
# 验证阶段发现方法论需要改进
loushang execute "任务" --method software/task/tdd

# 验证完成后，提示：
# "本次使用的方法论是否有需要改进的地方？"
# 用户回答后，自动触发：

loushang methodology optimize --from-session --method software/task/tdd
```

### 改进类型

| 改进类型 | 示例 | 版本变化 |
|----------|------|----------|
| **Patch** | 修正错别字、调整措辞 | 1.0.0 → 1.0.1 |
| **Minor** | 新增步骤、补充检查项 | 1.0.0 → 1.1.0 |
| **Major** | 重构流程、改变核心方法 | 1.0.0 → 2.0.0 |

### 价值

- **个人**：每次使用都是学习机会，方法论越用越好
- **团队**：集体智慧沉淀，避免重复踩坑
- **组织**：形成持续改进的文化，方法论资产持续增值

---

## 阶段与元角色映射

| 阶段 | 元角色 | 领域变体示例 |
|------|--------|--------------|
| PLAN | PLANNER | 产品战略、技术战略、业务战略 |
| EXPLORE | EXPLORER | 技术调研、用户研究、市场分析 |
| DESIGN | DESIGNER | 架构师、方案设计师、产品设计师 |
| BUILD | DELIVER | 开发工程师、咨询顾问、内容创作者 |
| VERIFY | VALIDATOR | QA/测试、质量经理、编辑审核 |

---

## 与 PDCA 的映射

| PDCA | 元阶段 | 说明 |
|------|--------|------|
| P (Plan) | PLAN + EXPLORE + DESIGN | 理解价值、探索方案、设计结构 |
| D (Do) | BUILD | 构建交付 |
| C (Check) | VERIFY | 验证价值 |
| A (Act) | 回到 PLAN | 调整方向，重新开始价值流 |

---

## 执行模型：Worktree + Agent Loop

```
每个阶段在独立的 Git Worktree 中执行

┌─────────────────────────────────────────────────────────┐
│  PLAN Phase (Worktree: .claude/worktrees/task-plan)     │
│  └── Agent Loop扮演 PLANNER                              │
│       └── Output: 价值主张、成功标准                     │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  EXPLORE Phase (Worktree: .claude/worktrees/task-exp)   │
│  └── Agent Loop扮演 EXPLORER                             │
│       └── Output: 可行方案                               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  DESIGN Phase (Worktree: .claude/worktrees/task-design) │
│  ├── Sub-phase: 概要设计 (Architect)                     │
│  └── Sub-phase: 详细设计 (Detailed Designer)             │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
                     [BUILD, VERIFY...]
```

---

## 领域特定的阶段变体

### 软件开发

```yaml
software-flow:
  PLAN: 需求理解、技术选型
  EXPLORE: 技术调研、方案对比
  DESIGN:
    - 概要设计: 架构设计（Architect）
    - 详细设计: 类设计、接口设计
  BUILD: 编码、单元测试
  VERIFY: 代码审查、集成测试
```

### 咨询方案

```yaml
consulting-flow:
  PLAN: 问题诊断、项目范围
  EXPLORE: 行业研究、最佳实践
  DESIGN:
    - 概要设计: 方案框架（Solution Designer）
    - 详细设计: 单页内容设计
  BUILD: PPT 制作、数据整理
  VERIFY: 内部评审、客户反馈
```

### 内容创作

```yaml
content-flow:
  PLAN: 选题策划、受众分析
  EXPLORE: 资料收集、角度探索
  DESIGN:
    - 概要设计: 内容结构
    - 详细设计: 段落大纲、案例选择
  BUILD: 内容撰写
  VERIFY: 编辑审核、事实核查
```

---

## 一句话总结

| 阶段 | 核心问题 | 本质 |
|------|----------|------|
| **PLAN** | WHY? | 理解价值，定义标准 |
| **EXPLORE** | WHAT COULD BE? | 探索可能性 |
| **DESIGN** | HOW TO ORGANIZE? | 设计结构 |
| **BUILD** | HOW TO REALIZE? | 构建交付 |
| **VERIFY** | IS VALUE DELIVERED? | 验证价值 |

> **阶段不是刚性流水线，而是价值流的检查点。可以回退、跳过、循环，由 CONDUCTOR 根据上下文动态调度。**

---

*版本: Meta-Phase v1.0*
