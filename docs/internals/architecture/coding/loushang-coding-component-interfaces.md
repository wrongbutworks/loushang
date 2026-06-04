# Loushang Coding Component Interfaces

## Scope

本文档作为 `loushang-coding` 组件接口设计的总入口。

它主要回答：

- 组件接口文档应该怎么读
- 接口命名与分层遵循什么统一规则
- 每个组件的详细接口应该去哪里看

本文档不再重复展开每个组件的长段接口说明。

详细 one-pager 统一放在：

- [component-interfaces/](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/README.md)

当前组件清单总表见：

- [Loushang Coding Component Inventory](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-inventory.md)

## Design Basis

本文档建立在以下文档之上：

- [Loushang Coding Component Structure And Responsibilities](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-structure-and-responsibilities.md)
- [Loushang Coding Component Dependencies](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-dependencies.md)
- [Loushang Coding Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)
- [Loushang Coding Core Data Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-data-objects.md)
- [Loushang Coding Deployment Unit Terminology](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-du-terminology.md)
- [reference coding agent Internal Dependency Overview](/home/dev/workspace/loushang/docs/architecture/coding/reference/reference-coding-agent/architecture-dependencies.md)

## How To Use This Doc Set

建议按下面顺序阅读：

1. 先看本文档，理解接口命名、分层和跨组件约束
2. 再看 [Component Inventory](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-inventory.md) 了解组件清单与结构分层
3. 最后按需进入 [component-interfaces/](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/README.md) 阅读单组件 one-pager

阅读时还应区分两种口径：

- `architecture` 文档主要表达 should-be 的目标边界与结构约束
- `spec / plan` 文档主要表达某次迭代的临时设计与落地步骤

## Interface Conventions

当前接受以下统一规则：

- 服务对象名尽量对齐 `reference coding agent`
- 方法 / 函数名使用 Python 风格 `snake_case`
- Python SDK surface 通过 `loushang.py.typed` 声明 typed package；新增稳定公开类型时应补顶层
  `loushang.coding` 导出或明确记录只在子包导出
- 单组件文档统一按 `Role / Owns / Depends On / Commands / Queries / Events` 描述
- 组件特定边界以单组件 one-pager 为准

典型命名例子：

- `createAgentSession()` -> `create_agent_session()`
- `createAgentSessionRuntime()` -> `create_agent_session_runtime()`
- `switchSession()` -> `switch_session()`
- `waitForIdle()` -> `wait_for_idle()`
- `continue()` -> `continue_run()`

## Interface Classification

为保持接口面一致，当前统一使用三类接口：

1. `Commands`
   - 推进状态、改变状态、触发运行

2. `Queries`
   - 只读查询、获取当前视图

3. `Events`
   - 对外暴露的稳定事件面

## Component Navigation

### Entry And Surface Layer

- [bootstrap](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/bootstrap.md)
- [sdk](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/sdk.md)
- [cli](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/cli.md)
- [mode](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/mode.md)

### Runtime Core Layer

- [runtime](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/runtime.md)
- [session](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/session.md)
- [store](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/store.md)
- [message](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/message.md)
- [event](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/event.md)

### Execution And Assembly Layer

- [tools](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/tools.md)
- [exec](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/exec.md)
- [compaction](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/compaction.md)

### Resource And Customization Layer

- [prompt](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/prompt.md)
- [skill](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/skill.md)
- [loader](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/loader.md)
- [extensions](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/extensions.md)
- [plugin](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/plugin.md)
- [method](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/method.md)

### Control And Support Layer

- [control](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/control.md)
- [policy](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/policy.md)
- [diagnostics](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/diagnostics.md)
- [utils](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/utils.md)

## Cross-Component Constraints

当前建议把这些约束视为接口一致性的主规则：

- `session` 是业务中心；不要把核心编排下沉到 `cli`、`mode` 或 `bootstrap`
- `store` 负责持久化边界；special summary entry 不应伪装成普通 message
- `message` 与 `event` 应尽量早稳，避免后续 mode/tool/diagnostics 大面积返工
- `prompt` 是资源层到运行层的桥，不应吞并 `skill`、`method` 或 `session` 的职责
- `tools`、`exec`、`policy` 保持分离；不要把工具注册、命令执行和审批逻辑混成单层
- `compaction` 是协调层，不应回流成 `store` 或 `session` 内部的隐式逻辑
- `utils` 只能做薄辅助层，不应承载隐藏业务中心

## Related Docs

- [Loushang Coding Component Inventory](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-inventory.md)
- [Loushang Coding Component Structure And Responsibilities](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-structure-and-responsibilities.md)
- [Loushang Coding Component Dependencies](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-dependencies.md)
- [Loushang Coding Development Priority And Stability Strategy](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-development-priority-and-stability-strategy.md)
- [Component Interface Notes](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/README.md)
