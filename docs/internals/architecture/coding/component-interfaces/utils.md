# `utils`

## Role

- coding 各组件共享的小型通用辅助层

## Owns

- 文件与路径小工具
- 文本与序列化辅助
- 非业务型错误包装
- token / message 的轻量辅助函数

## Depends On

- 无稳定业务依赖

## Commands

- 当前不定义稳定 command 接口

## Queries

- 当前不定义稳定 query 接口

## Events

- 无

## Key Data

- 当前不拥有稳定业务数据对象

## Out Of Scope

- 任何 session / store / prompt / tool 业务语义
- 组件间 orchestration
- 面向用户的产品接口

## Reference Implementation Alignment

- 与 `reference CLI` 一样保留 utils 作为薄辅助层
- 明确禁止把业务中心逻辑下沉到 `utils`
