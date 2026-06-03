# Loushang Coding Core Data Object Notes

## Purpose

本目录用于放置 `loushang-coding` 核心数据对象的分组说明。

它和总览文档的分工是：

- 总览文档负责对象分类、命名规则与阅读入口
- 本目录负责对象族级别的说明

对应总览文档：

- [Loushang Coding Core Data Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-data-objects.md)
- [Loushang Coding JSON Mode Design](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-json-mode-design.md)

## Writing Rule

每篇对象族文档优先回答：

- 这一组对象属于哪个组件或对象族
- 每个对象的角色是什么
- 它承载什么核心语义
- 它是权威对象、记录对象、投影对象还是配置对象
- 与 `pi-coding-agent` 的对齐关系是什么

如果某个对象同时出现在多个组件边界中，还应明确：

- 哪一侧是权威记录或重建来源
- 哪一侧只是消费、投影、转发或展示该对象

不应在单篇对象文档里展开：

- 字段级 schema
- 存储编码细节
- 详细运行时序
- 阶段性开发状态

## File Naming

- 每个对象族一个文件
- 文件名直接使用对象族名称
- 例：`runtime-state.md`、`entry-family.md`

## Template

新建对象族文档时，优先复制：

- [_template.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/_template.md)

## Current Notes

- [runtime-state.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/runtime-state.md)
- [session-records.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/session-records.md)
- [entry-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/entry-family.md)
- [message-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/message-family.md)
- [event-family.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/event-family.md)
- [control-configs.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/control-configs.md)
- [tool-exec-policy.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/tool-exec-policy.md)
- [prompt-compaction.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/prompt-compaction.md)
- [resource-descriptors.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/resource-descriptors.md)
- [diagnostics.md](/home/dev/workspace/loushang/docs/architecture/coding/core-data-objects/diagnostics.md)
