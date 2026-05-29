# Loushang Coding Component Inventory

## Scope

本文档给出 `loushang-coding` 的组件清单总表。

它主要回答：

- 当前接受的组件拓扑是什么
- 组件属于哪一层
- 组件在架构中的职责是什么

本文档不回答：

- 当前是否已实现
- 当前代码路径在哪里
- 当前阶段优先级与推进顺序如何

## Reading Rule

字段含义如下：

- `Layer`: 组件所在结构层

实现状态以代码与测试为准；具体任务推进以 spec / plan 为准。

## Component Table

| Component | Layer | Role |
| --- | --- | --- |
| `bootstrap` | entry | 默认装配入口 |
| `sdk` | entry | 宿主嵌入入口 |
| `cli` | entry | 命令行入口 |
| `mode` | entry | I/O 适配层 |
| `runtime` | core | 活动 session 宿主 |
| `session` | core | 单 session 门面 |
| `store` | core | 持久化与恢复 |
| `message` | core | transcript 对象模型 |
| `event` | core | session 事件协议 |
| `tools` | execution | 工具注册层 |
| `exec` | execution | 命令执行层 |
| `compaction` | execution | 上下文压缩协调层 |
| `prompt` | resource | prompt 装配桥 |
| `skill` | resource | skill 发现与注入 |
| `loader` | resource | 资源发现与加载 |
| `extensions` | resource | 扩展 hook 运行层 |
| `plugin` | resource | plugin bundle 管理与资源展开 |
| `method` | resource | method 注册与选择 |
| `control` | support | settings / model 控制平面 |
| `policy` | support | 权限与审批策略 |
| `diagnostics` | support | 诊断与错误归一化 |
| `utils` | support | 薄通用辅助层 |

## Related Docs

- [Loushang Coding Component Interfaces](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-interfaces.md)
- [Component Interface Notes](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/README.md)
- [Loushang Coding Development Priority And Stability Strategy](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-development-priority-and-stability-strategy.md)
