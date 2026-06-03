# Superpowers 方法元化重构设计

## 背景

本文档探讨如何将 [Superpowers](https://github.com/obra/superpowers) 从"执行技能集"升级为"系统化工程方法论"，通过 Loushang 的方法元体系进行重构。

## 当前 Superpowers 的结构性缺口

Superpowers 提供了优秀的软件开发工作流：

```
brainstorming → plan → implement → review → finish
```

但存在以下缺口：

| 缺口 | 说明 | 风险 |
|------|------|------|
| ❌ 缺少显式架构设计阶段 | brainstorming 是需求澄清，不是架构设计 | 实现与架构脱节 |
| ❌ 缺少系统工程视角 | 直接跳到实现任务，跳过架构分层 | 技术债务累积 |
| ❌ 缺少组件建模 | 没有显式的组件边界、接口契约 | 模块耦合严重 |
| ❌ 缺少架构治理 | 实现过程无架构合规检查 | 架构漂移 |

## 方法元增强版架构

### 分层角色模型

```
┌─────────────────────────────────────────────────────────────┐
│  探索层 (Explorer)                                          │
│  ├── requirements-discovery     需求发现                     │
│  └── opportunity-exploration    机会探索                     │
├─────────────────────────────────────────────────────────────┤
│  分析层 (Analyst)                                           │
│  ├── feasibility-analysis       可行性分析                   │
│  └── risk-assessment            风险识别                     │
├─────────────────────────────────────────────────────────────┤
│  架构层 (Architect) ⭐ 核心新增                              │
│  ├── system-architecture        系统架构                     │
│  ├── component-modeling         组件建模                     │
│  ├── interface-design           接口设计                     │
│  └── dependency-planning        依赖规划                     │
├─────────────────────────────────────────────────────────────┤
│  设计层 (Designer) ⭐ 细化                                    │
│  ├── domain-modeling            领域模型                     │
│  ├── data-modeling              数据模型                     │
│  └── algorithm-design           算法设计                     │
├─────────────────────────────────────────────────────────────┤
│  规划层 (Planner)                                           │
│  └── implementation-planning    实现计划                     │
├─────────────────────────────────────────────────────────────┤
│  实现层 (Implementor)                                       │
│  ├── tdd-development            TDD 开发                     │
│  └── subagent-driven-dev        子代理开发                   │
├─────────────────────────────────────────────────────────────┤
│  验证层 (Validator)                                         │
│  ├── code-review                代码审查                     │
│  ├── architecture-compliance    架构合规 ⭐                  │
│  └── integration-verification   集成验证                     │
├─────────────────────────────────────────────────────────────┤
│  治理层 (Governor) ⭐ 贯穿始终                               │
│  └── architecture-governance    架构守护                     │
└─────────────────────────────────────────────────────────────┘
```

## 新增方法元设计

### 1. 系统架构方法元

```yaml
# methods/software/architecture/system-design
meta:
  id: software/architecture/system-design
  name: 系统架构设计
  role: architect
  temperature: 0.7
  mechanism: workflow

applicability:
  when:
    - 需要设计新系统或重构现有系统
    - 涉及多个子域或模块
  whenNot:
    - 单一组件的小改动
    - 纯 UI/UX 调整

workflow:
  1-subdomain-identification:
    name: 识别子域
    description: 使用领域驱动设计识别 bounded contexts
    output: 子域地图

  2-context-mapping:
    name: 定义上下文映射
    description: 确定子域间关系
    output: 上下文映射图

  3-architecture-pattern:
    name: 选择架构模式
    description: 微服务/单体/模块化单体/事件驱动
    output: 架构决策记录 (ADR)

  4-communication-pattern:
    name: 定义通信模式
    description: 同步/异步/事件总线/消息队列
    output: 通信契约文档

  5-tech-selection:
    name: 技术选型
    description: 数据库、框架、中间件选择
    output: 技术栈清单 + 选型理由
```

### 2. 组件建模方法元

```yaml
# methods/software/design/component-modeling
meta:
  id: software/design/component-modeling
  name: 组件建模
  role: architect/designer
  temperature: 0.5
  mechanism: workflow

workflow:
  1-component-identification:
    name: 识别组件
    description: 基于职责单一原则划分组件
    output: 组件列表 + 职责描述

  2-interface-definition:
    name: 定义接口
    description: 输入/输出、错误处理、版本策略
    output: 接口契约 (OpenAPI/AsyncAPI)

  3-dependency-mapping:
    name: 梳理依赖
    description: 依赖方向、循环依赖检测
    output: 依赖图

  4-anti-corruption-layer:
    name: 防腐层设计
    description: 外部依赖抽象、适配器模式
    output: 防腐层接口定义
```

### 3. 架构治理方法元

```yaml
# methods/software/governance/architecture-governance
meta:
  id: software/governance/architecture-governance
  name: 架构治理
  role: governor
  temperature: 0.3
  mechanism: practice
  trigger: "任何代码变更"

checks:
  - id: boundary-check
    name: 组件边界检查
    query: 是否违反已定义的组件边界？

  - id: interface-check
    name: 接口合规检查
    query: 是否绕过已定义的接口？

  - id: dependency-check
    name: 依赖合规检查
    query: 是否引入未批准的外部依赖？

  - id: pattern-check
    name: 架构模式检查
    query: 是否破坏已定义的架构模式？

actions:
  - type: block
    condition: critical
    description: 阻止不符合架构的变更

  - type: warn
    condition: medium
    description: 警告潜在的架构漂移

  - type: suggest
    condition: all
    description: 建议符合架构的替代方案
```

## 工作流对比

### 原 Superpowers（7步）

```
brainstorm → worktree → plan → implement → tdd → review → finish
(需求)      → (环境)   → (计划) → (实现)   → (测试) → (审查) → (收尾)
```

### 方法元增强版（分层+角色）

```
Phase 1: 探索 (Explorer)
  ├── requirements-discovery    需求发现
  └── opportunity-exploration   机会探索

Phase 2: 分析 (Analyst)
  ├── feasibility-analysis      可行性分析
  └── risk-assessment           风险评估

Phase 3: 架构 (Architect) ⭐ 核心新增
  ├── system-architecture       系统架构
  ├── component-modeling        组件建模
  └── architecture-decisions    架构决策

Phase 4: 设计 (Designer)
  ├── domain-modeling           领域模型
  ├── data-modeling             数据模型
  └── algorithm-design          算法设计

Phase 5: 规划 (Planner)
  └── implementation-planning   实现计划

Phase 6: 实现 (Implementor)
  ├── git-worktree-setup
  ├── tdd-development
  └── subagent-driven-development

Phase 7: 验证 (Validator)
  ├── code-review
  ├── architecture-compliance-review ⭐
  └── integration-verification

Phase 8: 收尾 (Coordinator)
  └── branch-finishing
```

## 方法元带来的核心优势

| 优势 | 原 Superpowers | 方法元增强版 |
|------|----------------|--------------|
| **显式架构阶段** | ❌ 直接跳实现 | ✅ 系统架构 → 组件建模 → 实现 |
| **分层设计** | ❌ 平铺任务 | ✅ 系统级 → 组件级 → 实现级 |
| **接口契约优先** | ❌ 边做边定 | ✅ 先契约后实现 |
| **架构治理** | ❌ 无 | ✅ Governor 角色持续检查 |
| **温度适配** | ❌ 固定严格 | ✅ 架构0.7探索，实现0.2严格 |
| **可追溯** | ❌ 代码难追溯设计 | ✅ ADR记录每个架构决策 |
| **可演进** | ⚠️ 依赖Skill更新 | ✅ Pack生态持续演进 |

## 实施路线图

### 阶段 1：包装集成（短期）

将现有 Superpowers 作为 Loushang 的一个 Pack：

```typescript
// packs/superpowers/pack.json
{
  "id": "superpowers",
  "name": "Superpowers Integration",
  "version": "1.0.0",
  "type": "legacy-integration",
  "methodologies": [
    "brainstorming",
    "writing-plans",
    "subagent-driven-development",
    "test-driven-development"
  ]
}
```

### 阶段 2：插入架构层（中期）

在现有流程前插入架构方法元：

```typescript
const enhancedFlow = [
  // 新增前置阶段
  'exploring/requirements-discovery',
  'architecture/system-design',           // ⭐ 新增
  'architecture/component-modeling',      // ⭐ 新增
  'design/domain-modeling',               // ⭐ 新增

  // 原 Superpowers
  'planning/implementation-planning',
  'building/subagent-driven-development',

  // 新增验证阶段
  'verifying/architecture-compliance',    // ⭐ 新增
  'finishing/branch-cleanup'
];
```

### 阶段 3：温度动态适配（长期）

根据角色动态调整温度：

```typescript
const temperatureMap = {
  'explorer': 0.8,        // 高度发散，探索可能
  'analyst': 0.6,         // 平衡分析
  'architect': 0.7,       // 结构约束下的探索
  'designer': 0.5,        // 结构确定，细节可调
  'planner': 0.4,         // 规划需要确定性
  'implementor': 0.2,     // 严格执行
  'validator': 0.1,       // 严格检查
  'governor': 0.3         // 长期视角，允许演进
};
```

### 阶段 4：增强 TDD 方法元

将架构检查嵌入 TDD 循环：

```
架构上下文加载 (Architect)
  ↓
组件契约回顾 (Designer)
  ↓
红 → 绿 → 重构 (Implementor)
  ↓
架构合规检查 (Governor): "是否破坏组件边界？"
  ↓
接口契约验证 (Validator): "是否符合契约？"
```

## 具体示例：子代理开发增强

原 Superpowers `subagent-driven-development`：

```
dispatch implementer → spec review → code quality review
```

方法元增强版：

```
load architecture-context     # Architect 上下文
  ↓
component-contract-review     # Designer 契约检查
  ↓
dispatch implementer          # Implementor 实现
  ↓
spec compliance review        # Validator 规格合规
  ↓
code quality review           # Validator 代码质量
  ↓
architecture compliance       # Governor 架构合规 ⭐新增
  ↓
interface contract validation # Validator 契约验证 ⭐新增
```

## 总结

用方法元重写 Superpowers 的**核心价值**：

1. **补全架构缺口** - 从需求直接到实现 → 先架构后实现
2. **增加治理机制** - 无架构检查 → Governor 持续守护
3. **分层递进** - 平铺流程 → 分层（探索→分析→架构→设计→实现）
4. **温度适配** - 一刀切严格 → 按角色动态调整
5. **生态集成** - 独立 Skill → Pack 生态可演进

**这不是替代 Superpowers，而是将其从"执行技能集"升级为"系统化工程方法论"**。

---

*关联讨论: Superpowers 分析、方法元角色设计*
