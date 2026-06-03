# 领域分类设计 (Domain Taxonomy)

## 核心原则

分离 **How（机制）** 与 **What（领域）** 两个正交维度。

```
Task = How (mechanism) × What (domain) × Who (role) × In/Out (interface)
```

## How 维度：方法元类型（与 SPEM 2.0 对齐）

```typescript
interface MethodElement {
  // 方法元类型（SPEM 2.0 概念）
  type: 'phase' | 'activity' | 'task' | 'role' | 'guidance' | 'workproduct';  // workproduct 简写: wp
}
```

### 与 SPEM 2.0 的映射

| 我们的类型 | SPEM 2.0 | 说明 | 存储位置 |
|-----------|----------|------|----------|
| **phase** | Phase | 特殊的 Activity，价值流里程碑 | `methods/phase/{name}/SKILL.md` |
| **activity** | Activity | 引用 Task，定义执行上下文 | `methods/activity/{name}/SKILL.md` |
| **task** | Task | 定义"做什么"（输入、输出、步骤）| `methods/task/{name}/SKILL.md` |
| **role** | Role | 执行者职责（5+1 元角色）| `methods/role/{name}/SKILL.md` |
| **guidance** | Guidance | 补充说明"如何做"| `methods/guidance/{name}/SKILL.md` |
| **workproduct** | Work Product | 输入/输出的工件 | `methods/workproduct/{name}/SKILL.md` (简写: wp) |

### 方法元的组合规则

```typescript
interface CompositionRules {
  // Phase 包含 Activity
  phase: ['activity'];

  // Activity 引用 Task，可定义/覆盖 Steps
  activity: ['step'];

  // Task 包含 Step（SPEM 2.0）
  task: ['step'];

  // Role 与 Task 关联（responsible）
  role: [];

  // Guidance 可应用于任何元素
  guidance: ['phase', 'activity', 'task', 'role'];

  // workproduct 是输入/输出 (简写: wp)
  workProduct: [];
}
```

### 元素间关系（SPEM 2.0 风格）

```yaml
# Phase 包含 Activity
phase: DESIGN
contains:
  - activity: architect
  - activity: detailed-design

# Activity 引用 Task
activity: architect
performs: task/architect  # 引用 Task
role: DESIGNER.architect  # 执行角色

# Task 定义 Steps
task: architect
steps:
  - step: "识别系统边界"
  - step: "划分核心组件"

# Role 定义
type: role
meta-role: DESIGNER
name: 设计师

# Guidance 应用
type: guidance
applies-to: [task/architect, task/detailed-design]
```

## What 维度：顶层域（Top-Level Domains）

```
methods/
├── meta/                    # 元方法元（创建/管理/编排）
│   ├── creating/            # 创建方法元的方法元
│   ├── packaging/           # 沉淀方法元的方法元
│   ├── selecting/           # 如何选择方法论
│   └── composing/           # 如何组合方法论
│
├── software/                # 软件工程
│   ├── exploring/           # 探索理解
│   ├── designing/           # 架构设计
│   ├── building/            # 构建实现
│   ├── verifying/           # 验证测试
│   ├── deploying/           # 部署交付
│   └── operating/           # 运维监控
│
├── business/                # 业务/商业
│   ├── strategy/            # 战略规划
│   ├── transformation/      # 业务转型
│   ├── process/             # 流程优化
│   ├── analysis/            # 商业分析
│   └── modeling/            # 业务建模
│
├── product/                 # 产品
│   ├── discovery/           # 产品发现
│   ├── design/              # 产品设计
│   ├── planning/            # 路线图规划
│   ├── validation/          # 验证
│   └── sunset/              # 产品下线
│
├── content/                 # 内容创作
│   ├── writing/             # 写作
│   ├── editing/             # 编辑
│   ├── researching/         # 研究
│   └── presenting/          # 呈现
│
├── people/                  # 人员/组织
│   ├── managing/            # 管理
│   ├── coaching/            # 辅导
│   ├── hiring/              # 招聘
│   ├── onboarding/          # 入职
│   └── decision-making/     # 决策
│
├── learning/                # 学习/成长
│   ├── skill-acquisition/   # 技能习得
│   ├── knowledge-synthesis/ # 知识整合
│   └── teaching/            # 教学
│
└── problem-solving/         # 通用问题解决
    ├── analysis/            # 分析
    ├── synthesis/           # 综合
    ├── decision/            # 决策
    └── creativity/          # 创意
```

## 域能力声明

每个顶层域声明自己的能力模型：

```json
// methods/business/meta.json
{
  "domain": {
    "id": "business",
    "nature": "analytical-conceptual",
    "artifacts": ["documents", "models", "decisions"],
    "evaluation": "subjective-expert",
    "tools": ["research", "interview", "workshop"],
    "constraints": ["stakeholder-alignment", "market-timing"]
  }
}

// methods/software/meta.json
{
  "domain": {
    "id": "software",
    "nature": "technical-constructive",
    "artifacts": ["code", "tests", "docs"],
    "evaluation": "objective-automated",
    "tools": ["ide", "compiler", "test-runner"],
    "constraints": ["syntax", "runtime", "dependencies"]
  }
}
```

## URI 设计

```
loushang://methods/{type}/{id}

# 示例
loushang://methods/role/DESIGNER              # 获取角色定义
loushang://methods/phase/DESIGN               # 获取阶段定义
loushang://methods/task/software/tdd          # 获取任务定义
loushang://methods/activity/architect         # 获取活动定义
loushang://methods/guidance/design-principles # 获取指南
```

## 多维度标签系统

### 维度 1: 任务类型（Task Type）

```
exploring      → 探索理解（读代码、理架构）
coding         → 编码实现（新功能、模块）
debugging      → 调试修复（Bug、异常）
refactoring    → 重构优化（结构调整）
reviewing      → 审查评估（Code Review、Audit）
architecting   → 架构设计（系统设计、技术选型）
packaging      → 知识沉淀（方法论创建、经验萃取）
```

### 维度 2: 技术领域（Tech Domain）

```
frontend, backend, database, devops, ai/ml,
security, performance, accessibility, mobile
```

### 维度 3: 场景上下文（Context）

```
startup-mvp      → 初创公司MVP
enterprise       → 企业级应用
oss-library      → 开源库
legacy-system    → 遗留系统
research         → 研究探索
```

### 维度 4: 复杂度/深度（Complexity）

```
quick        → 快速（5-15分钟，单步骤）
standard     → 标准（30-60分钟，多步骤）
deep         → 深度（数小时，完整流程）
```

## 领域匹配示例

```json
{
  "domains": {
    "primary": ["coding", "backend"],
    "secondary": ["api-design", "testing"],
    "contexts": ["enterprise", "oss-library"],
    "complexity": "standard",
    "lifecycle": ["new-feature", "maintenance"]
  }
}
```

## 跨域组合

```json
{
  "id": "business-transformation-digital",
  "type": "composed",
  "components": [
    {
      "method": "business/transformation/lean-change",
      "phase": "strategy",
      "weight": 0.4
    },
    {
      "method": "software/design/domain-driven",
      "phase": "implementation",
      "weight": 0.3
    },
    {
      "method": "people/change-management/communication",
      "phase": "throughout",
      "weight": 0.3
    }
  ],
  "orchestration": "sequential-with-feedback-loops"
}
```

## 发现与推荐

### 领域感知路由

```typescript
interface MethodologyRouter {
  // 根据任务描述匹配候选方法元
  async match(task: TaskDescription): Promise<ScoredMethodology[]>;

  // 渐进式精化
  async refine(
    candidates: Methodology[],
    feedback: UserFeedback
  ): Promise<Methodology[]>;
}

// 使用示例
const candidates = await router.match({
  intent: "实现用户认证功能",
  context: {
    domain: "backend",
    complexity: "standard",
    team: "startup"
  }
});
// → [coding/tdd, coding/api-first, coding/ddd-lite]
```

### 可视化领域地图

```
loushang map --domain software

software/
├── exploring/
│   ├── code-reading          [quick]
│   ├── architecture-analysis [standard]
│   └── legacy-untangling     [deep]
├── implementing/
│   ├── tdd                   [standard] ← 推荐
│   ├── bdd                   [standard]
│   ├── prototype-first       [quick]
│   └── ddd                   [deep]
├── debugging/
│   ├── binary-search         [quick]
│   ├── root-cause-analysis   [standard]
│   └── system-debugging      [deep]
└── reviewing/
    ├── self-review           [quick]
    └── peer-review           [standard]
```

## 文件结构

所有方法元使用统一的 **SKILL.md** 格式描述：

```
methods/
├── phase/                          # 阶段定义
│   ├── plan/
│   ├── explore/
│   ├── design/
│   ├── build/
│   └── verify/
│
├── activity/                       # 活动定义
│   ├── architect/
│   ├── detailed-design/
│   └── code-review/
│
├── task/                           # 任务定义
│   ├── tdd/
│   ├── refactoring/
│   └── unit-testing/
│
├── role/                           # 角色定义（5+1 元角色）
│   ├── PLANNER/
│   ├── EXPLORER/
│   ├── DESIGNER/
│   ├── DELIVER/
│   ├── VALIDATOR/
│   └── CONDUCTOR/
│
├── guidance/                       # 指南定义
│   ├── design-principles/
│   └── testing-best-practices/
│
└── workproduct/                    # 工作产品定义 (简写: wp)
    ├── architecture-doc/
    └── test-report/
```

每个目录下统一使用 **SKILL.md**：

```
methods/task/tdd/
└── SKILL.md          # 包含元数据 + 正文内容
```

## 设计原则总结

| 原则 | 实现方式 |
|------|---------|
| **渐进发现** | URI 分层 + 三阶段加载 |
| **解耦** | 接口契约 + URI 引用 + 版本语义 |
| **领域描述** | 多维度标签 + applicability 声明 |
| **智能分类** | 任务/技术/场景/复杂度 四维标签 |
| **灵活引用** | 显式 import + 隐式关联 + 运行时组合 |

---
