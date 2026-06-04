# 贡献指南

[English](../en/contributing.md) | 中文

Loushang 目前处于早期活跃开发阶段。贡献应保持当前公开产品面诚实：文档写清楚今天能用什么，将路线图方向与已交付行为分开，并避免让内部设计材料占据用户主路径。

## 本地开发

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

等价的便捷命令是 `make bootstrap`。

在本仓库做 Python 工作时，请使用本地虚拟环境 `.venv/`。

## 文档变更

- 公开用户文档放在 `docs/en/` 和 `docs/zh-CN/`。
- 历史架构、设计决策、spec、plan 和术语草案放在 `docs/internals/`。
- 英文和中文公开页面保持结构对齐。
- 不要把路线图中的产品面写成已经完整交付的行为。

## 验证

文档-only 变更需要验证已修改文档中的相对链接可以解析，并确认文档树仍然清楚地区分公开材料与内部材料。代码变更需要先运行相关测试和 lint，再说明完成状态。
