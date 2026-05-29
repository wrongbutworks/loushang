# Loushang-AI Model Design Note

本文档已从旧模型中间层方案收敛为当前实现说明。

## 当前结论

`loushang.ai` 的模型子包当前只保留三层：

- `model/domain.py`
- `model/registry.py`
- `model/loader.py`

`models.json` 是底层事实源，直接表达：

- provider
- endpoint
- model

以及配套值对象：

- auth
- capabilities
- support
- compat
- defaults
- pricing

## 已废弃的旧方案

以下概念不再是当前结构的一部分：

- 旧模型中间层
- 旧 loader 命名
- capability resolver

如果旧文档或旧代码里还出现这些名字，应视为待清理残留，而不是当前架构。

## 当前职责分工

- `domain.py`
  - 定义 `Provider`、`Endpoint`、`Model` 及配套值对象
- `registry.py`
  - 提供运行时查询容器 `ModelRegistry`
- `loader.py`
  - 从内置 `models.json` 或显式文件/目录路径装载 registry

## 当前原则

- 不再引入额外的中间模型层
- 不再把模型结构拆成全局规格表与绑定表
- 不再把 capability 解释逻辑做成独立 resolver 主轴
- 以当前 `models.json` 和 `src/loushang/ai/model/` 代码为准
