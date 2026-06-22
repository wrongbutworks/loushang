# Loushang-AI ARD List

本文档索引 `loushang-ai` 的技术架构决策（Architecture Record Decision, `ARD`）。

`ARD` 的用途是记录：

- 已经拍板的关键技术取舍
- 当时的备选方案与权衡
- 对现有设计与实现的直接影响

`ARD` 不替代主设计文档。  
主设计文档负责描述系统结构；`ARD` 负责记录关键决策。

---

## Accepted

1. [ARD-001: Async Public Streaming Surface](./ARD-001-async-public-streaming-surface.md)
2. [ARD-002: AI Coverage Gate Scope](./ARD-002-ai-coverage-gate-scope.md)

---

## Notes

- `ARD` 主要用于记录少量高影响、长期有效的决策。
- 不应把一般实现细节、阶段性笔记或 review 结论都塞进 `ARD`。
- 当 `ARD` 与旧设计文档表述冲突时，应以已接受的 `ARD` 为准，并回补主设计文档。
