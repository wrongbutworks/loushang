# Loushang Coding Deployment Unit Terminology

## Scope

本文档定义 `loushang-coding` 架构讨论中的部署单元术语。

这里的 `DU` 指：

- `Deployment Unit`

本文档主要回答：

- `DU` 在这里是什么意思
- `组件`、`服务对象`、`数据对象` 与 `DU` 的关系是什么
- 当前建议使用哪些部署单元类型
- `logical / physical` 标签应如何使用

## Core Rule

当前采用以下规则：

- `DU` = `Deployment Unit`
- 不再把 `DU` 用作 `Decomposition Unit`
- 部署单元类型采用：
  - `BDU`
  - `CDU`
  - `DDU`
- `logical / physical` 作为标签附着在这些部署单元类型上

也就是说，当前推荐的口径不是：

- 裸 `DU`
- 裸 `LDU`
- 裸 `PDU`

而是：

- `logical BDU`
- `physical BDU`
- `logical CDU`
- `physical CDU`
- `logical DDU`
- `physical DDU`

## Component And Deployment Unit

`组件` 和 `部署单元` 不是同一个概念。

它们是两个不同维度：

- `组件`
  - 回答架构边界在哪里
  - 关注职责、依赖和协作关系

- `部署单元`
  - 回答什么东西可以作为部署、运行、隔离、替换的单元来考虑
  - 关注逻辑部署边界与物理部署边界

所以：

- 一个组件可以对应一个部署单元
- 多个组件也可以共同构成一个部署单元
- 一个逻辑部署单元最终可以落在一个或多个物理部署单元上

## Recommended Deployment Unit Types

当前建议保留三种核心部署单元类型。

### 1. BDU

中文：

- 边界部署单元

英文：

- `Boundary Deployment Unit`

缩写：

- `BDU`

承担职责：

- 对外命令入口
- 对外查询入口
- 对外事件出口
- 面向用户的交互表面
- 面向外部系统的接缝表面

### 2. CDU

中文：

- 运行控制部署单元

英文：

- `Control Deployment Unit`

缩写：

- `CDU`

承担职责：

- 生命周期推进
- 流程编排
- 状态切换
- 路由与调度
- 权限与运行控制判断

### 3. DDU

中文：

- 数据部署单元

英文：

- `Data Deployment Unit`

缩写：

- `DDU`

承担职责：

- 状态
- 配置
- 记录
- 消息
- 事件载荷
- 持久化对象

## Logical And Physical Labels

当前建议把 `logical / physical` 作为标签，而不是新的主缩写体系。

推荐写法：

- `logical BDU`
- `physical BDU`
- `logical CDU`
- `physical CDU`
- `logical DDU`
- `physical DDU`

不推荐默认写法：

- `BLDU`
- `BPDU`
- `CLDU`
- `CPDU`
- `DLDU`
- `DPDU`

理由：

- 组合缩写过多，阅读成本高
- 某些缩写容易和其他领域术语冲突
- `BDU/CDU/DDU + logical/physical label` 更直观

## Logical Vs Physical

两种标签的语义如下：

### logical

- 表示逻辑上的部署边界
- 强调职责隔离、替换边界、独立演化可能性
- 不要求当前真的单独进程化或单独发版

### physical

- 表示实际发布、运行或隔离边界
- 强调进程、容器、包、服务、应用或硬件节点等真实承载形式

## Relation To Components And Objects

部署单元不是对象类型。

它和组件、服务对象、数据对象的关系建议这样理解：

- `组件`
  - 是架构边界单元
  - 用来表达职责边界与依赖关系

- `服务对象`
  - 是组件内部承担行为与协调的对象
  - 往往是某个部署单元里的主要执行者

- `数据对象`
  - 是在部署单元之间流动、持有、存储、投影的事实对象
  - 一个数据对象可以被多个部署单元读取、缓存、复制或投影
  - 但最好始终有清晰的权威来源

换句话说：

- `组件` 是架构层概念
- `服务对象` / `数据对象` 是对象层概念
- `DU` 是部署层概念

三者不要混成同一层 taxonomy。

## Recommended Default Rule

对 `loushang-coding` 当前阶段，默认采用：

1. `BDU`
2. `CDU`
3. `DDU`
4. `logical / physical` 作为附加标签

## Example

一个简化示意可以写成：

- `logical BDU`
  - `cli`
  - `sdk`
  - `mode`

- `logical CDU`
  - `runtime`
  - `session`
  - `control`
  - `policy`

- `logical DDU`
  - `store`
  - `message`
  - `event`

而在当前实现阶段，它们完全可能共同落在同一个：

- `physical BDU/CDU/DDU hosting unit`
  - 也就是同一个 Python package / process / app 中

这里的重点是：

- 逻辑部署边界可以先成立
- 物理部署边界可以后置

## Related Docs

- [Loushang Coding Component Structure And Responsibilities](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-structure-and-responsibilities.md)
- [Loushang Coding Core Service Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-service-objects.md)
- [Loushang Coding Core Data Objects](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-core-data-objects.md)
- [Loushang Coding Component Interfaces](/home/dev/workspace/loushang/docs/architecture/coding/loushang-coding-component-interfaces.md)
