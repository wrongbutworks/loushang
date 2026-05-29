# 方法元文件结构规范

## 术语定义

**方法元**（Method Element）：所有方法论元素的统称，与 SPEM 2.0 对齐。

| 方法元类型 | SPEM 2.0 | 说明 |
|-----------|----------|------|
| **phase** | Phase | 特殊的 Activity，价值流里程碑 |
| **activity** | Activity | 引用 Task，定义执行上下文 |
| **task** | Task | 定义"做什么"（输入、输出、步骤）|
| **role** | Role | 执行者的职责定义（5+1 元角色）|
| **guidance** | Guidance | 补充说明"如何做"（指南、示例）|
| **workproduct** | Work Product | 输入/输出的工件 | 简写: wp |

## 目录结构

所有方法元使用统一的 **SKILL.md** 格式描述：

```
methods/
├── phase/                          # 阶段定义
│   └── {name}/
│       └── SKILL.md
│
├── activity/                       # 活动定义
│   └── {name}/
│       └── SKILL.md
│
├── task/                           # 任务定义（方法内容）
│   └── {name}/
│       └── SKILL.md
│
├── role/                           # 角色定义
│   └── {name}/
│       └── SKILL.md
│
├── guidance/                       # 指南定义
│   └── {name}/
│       └── SKILL.md
│
└── workproduct/                    # 工作产品定义 (简写: wp)
    └── {name}/
        └── SKILL.md
```

## 旧结构（已弃用）

```
# 不再使用，仅供参考
methods/{domain}/{mechanism}/{name}/
├── meta.json          # 已合并到 SKILL.md Frontmatter
├── prompt.md          # 已合并到 SKILL.md
├── guide.md           # 已合并到 SKILL.md
└── examples/          # 已内联到 SKILL.md
```

## SKILL.md 规范

### 统一格式

所有方法元使用统一的 SKILL.md 格式，通过 `type` 字段区分种类：

```markdown
---
# 方法元标识
id: software/task/tdd
name: 测试驱动开发
type: task              # phase | activity | task | role | guidance | workproduct (wp)
version: 1.0.0

# 领域信息
domain: software
tags: [testing, quality, agile]

# SPEM 关联（根据类型选用）
input: [requirement, test-framework]        # Task 的输入
output: [test-code, impl-code]              # Task 的输出
responsible: DELIVER                        # Task 的执行角色
performs: task/tdd                          # Activity 引用的 Task

# 执行参数
temperature: 0.2
complexity: standard
duration: 30-60分钟

# 适用性
applicability:
  when:
    - 需要长期维护的生产代码
    - 复杂业务逻辑开发
  whenNot:
    - 一次性原型/脚本
    - 探索性研究
---

## 概述

简要描述这个方法元是什么，解决什么问题。

## 步骤（Task/Activity 适用）

### 步骤 1: 编写失败测试

详细说明...

### 步骤 2: 编写最小实现

详细说明...

## 检查清单

- [ ] 测试先失败
- [ ] 实现最小化
- [ ] 消除重复

## 常见陷阱（Guidance 适用）

| 陷阱 | 解决方案 |
|------|----------|
| 陷阱1 | 解决方案1 |

## 示例

### 示例 1: 场景描述

```
具体示例...
```

## 参考

- 相关方法元: [link]
- 外部资源: [link]
```

### 类型特定结构

#### task 类型

```yaml
---
type: task
id: software/task/tdd
name: 测试驱动开发
input: [requirement]
output: [test-code, impl-code]
responsible: DELIVER
steps:
  - step: "编写失败测试"
  - step: "编写最小实现"
  - step: "重构代码"
---

## 概述
...
```

#### activity 类型

```yaml
---
type: activity
id: software/activity/architect
name: 概要设计
performs: task/architect
role: DESIGNER.architect
---

## 执行上下文
...
```

#### role 类型

```yaml
---
type: role
meta-role: DESIGNER
name: 设计师
essence: "设计结构，组织系统"
temperature: 0.5
---

## 职责
...
```

#### guidance 类型

```yaml
---
type: guidance
id: software/guidance/design-principles
name: 设计原则指南
applies-to: [task/architect, task/detailed-design]
---

## 最佳实践
...
```

## URI 规范

### 基础格式

```
loushang://methods/{type}/{id}
```

### 示例

```
loushang://methods/role/DESIGNER              # 获取角色定义
loushang://methods/task/software/tdd          # 获取任务定义
loushang://methods/phase/DESIGN               # 获取阶段定义
loushang://methods/guidance/design-principles # 获取指南
```

### 查询参数

```
loushang://methods?type=task&domain=software  # 筛选软件领域的任务
loushang://methods?role=DESIGNER              # 筛选适合设计师的方法元
```

## 版本管理

### 语义化版本

```yaml
---
id: software/task/tdd
version: 1.2.3
---
```

- **major**: 破坏性变更
- **minor**: 新增功能
- **patch**: bug修复

### 依赖引用

```yaml
---
imports:
  - id: core/testing version=^1.0
  - id: core/refactoring as refactor version=~2.1.0
---
```

---

*版本: Methodology File Structure v2.0 - SPEM Aligned*
