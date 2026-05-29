# Loushang Coding Component Interface Notes

## Purpose

本目录用于放置 `loushang-coding` 各组件的单独接口说明。

它和总览文档的分工是：

- 总览文档负责全局接口面与跨组件一致性
- 本目录负责单组件 one-pager

对应总览文档：

- [Loushang Coding Component Interfaces](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-interfaces.md)
- [Loushang Coding Component Inventory](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-inventory.md)

## Writing Rule

每个组件文档都应保持简洁明了，优先回答：

- 这个组件负责什么
- 它拥有什么边界
- 它依赖谁
- 它对外暴露什么 Commands / Queries / Events

本目录仍属于 `architecture` 文档集。

因此，这里的组件接口说明可以表达：

- 已接受的组件级接口设计
- 当前代码尚未完全落地的目标接口面

但这类文档不应用来记录：

- 当前开发状态
- 当前实现完成度
- 当前迭代的临时方案

不应在单组件文档里重复展开：

- 大段背景说明
- 长时序图
- 字段级 schema
- 实现细节
- 阶段性优先级与推进判断

具体实现状态以代码与测试为准；这次迭代的临时接口设计应继续放在 spec / plan 中。

## File Naming

- 每个组件一个文件
- 文件名直接使用组件名
- 例：`session.md`、`store.md`、`prompt.md`

## Template

新建组件接口文档时，优先复制：

- [_template.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/_template.md)

## Current Notes

- [session.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/session.md)
- [store.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/store.md)
- [control.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/control.md)
- [prompt.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/prompt.md)
- [tools.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/tools.md)
- [exec.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/exec.md)
- [policy.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/policy.md)
- [bootstrap.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/bootstrap.md)
- [runtime.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/runtime.md)
- [loader.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/loader.md)
- [plugin.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/plugin.md)
- [compaction.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/compaction.md)
- [message.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/message.md)
- [event.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/event.md)
- [sdk.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/sdk.md)
- [cli.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/cli.md)
- [mode.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/mode.md)
- [diagnostics.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/diagnostics.md)
- [skill.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/skill.md)
- [extensions.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/extensions.md)
- [method.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/method.md)
- [utils.md](/home/dev/workspace/loushang/docs/architecture/coding/component-interfaces/utils.md)
