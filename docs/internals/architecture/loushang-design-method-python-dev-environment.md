# Loushang Design Method: Python Development Environment

## Scope

本文档沉淀 `loushang` 在建立 Python 开发环境任务上的方法说明与执行准则。

本文档主要回答：

- 什么时候应把“建立 Python 开发环境”当成一个独立任务
- 这类任务的目标、边界与输出物是什么
- 如何设计环境任务，避免把临时运行方式写成长期规范
- 如何在 `pyproject.toml`、`uv`、`Makefile`、`src` 布局、examples/tests 之间保持一致
- 建立环境时应遵守哪些准则

本文档不讨论：

- 某个具体子系统的内部实现
- CI/CD 平台与发布流水线
- 部署环境
- Docker / 容器镜像

---

## Relationship To Other Docs

本文档建立在以下文档之上：

- [Loushang Monorepo Conventions](/home/dev/workspace/loushang/docs/architecture/loushang-monorepo-conventions.md)
- [Loushang Development Workflow And Tooling](/home/dev/workspace/loushang/docs/architecture/loushang-dev-workflow-and-tooling.md)

三者关系是：

- monorepo conventions
  - 回答目录、命名、源码根与 namespace 组织
- development workflow and tooling
  - 回答推荐工具链、统一命令入口与工作流
- 本文
  - 回答“如何把 Python 开发环境这件事设计成一个正确的任务”

---

## Why This Needs A Method

“把 Python 项目跑起来”表面上像一个很小的动作，但在实践里经常演化成错误的临时修补，例如：

- 在 example 里手动改 `sys.path`
- 依赖 shell 当前目录巧合
- 依赖编辑器私有配置
- 在 `Makefile`、README、脚本、测试里使用不同运行方式
- 裸 `python3` 能跑、`uv run` 不能跑，或反过来

这些做法短期能解一个问题，但会制造新的长期问题：

- 项目不可移植
- 新开发者难以复现
- examples 不能作为 API 参考
- 测试、示例、文档、实际运行方式相互脱节

因此，建立 Python 开发环境不应被看作纯工具操作，而应被看作一个需要设计的方法任务。

---

## Task Goal

建立 Python 开发环境任务的目标应固定为：

1. 项目源码可被标准方式导入
2. 根项目依赖可被标准方式安装
3. tests、examples、工具命令共享同一运行环境
4. 开发者不需要依赖路径 hack 或 IDE 私有配置
5. 仓库级命令入口与实际运行方式保持一致

一句话：

- 让项目通过“环境设计正确”而可运行
- 不是通过“脚本内补丁”而侥幸可运行

---

## Core Principle

Python 开发环境问题，优先修环境，不优先修示例。

也就是说，当出现：

- `ModuleNotFoundError`
- `uv run` 不能 import
- example 只能在某种 shell 技巧下运行
- 裸 `python3` 和项目环境行为不一致

应优先追查：

- package 是否被正确声明
- `src` 布局是否被正确打包
- `pyproject.toml` 是否完整
- `uv sync` 是否会把项目安装进环境
- `Makefile` 是否用统一入口调用

而不是优先在 example 文件里加入：

- `sys.path.insert(...)`
- 临时 import fallback
- 本地路径特判

---

## Recommended Task Sequence

建立 Python 开发环境任务，建议按以下顺序执行。

### 1. Freeze Project Shape

先冻结这几个基本决定：

- 是否采用根 `src/` layout
- import namespace 是什么
- 根 `pyproject.toml` 还是多 package
- 根 `.venv` 还是多环境
- `uv` / `pytest` / `ruff` / `mypy` 是否为默认工具链

在 `loushang` 当前阶段，推荐基线是：

- 根 `src/`
- `loushang.<subsystem>`
- 根 `pyproject.toml`
- 根 `.venv`
- `uv` 作为环境和运行入口

### 2. Make Packaging Real

如果项目打算通过标准方式运行，就必须让 packaging 成立。

最低要求：

- `pyproject.toml` 有 `[build-system]`
- 能发现 `src/` 下的包
- `uv sync` 后项目能安装进环境

如果这一步没有成立，后面的：

- `uv run python ...`
- example
- tests

都只能靠偶然成立。

### 3. Unify Runtime Entry

运行入口应尽量统一为：

- `uv run ...`
- 或根 `Makefile`

推荐形态：

```bash
uv sync --extra dev
uv run python examples/ai/01_complete.py
make example-ai-complete
```

不推荐把以下路径写成主推荐方式：

- 裸 `python3 some_file.py`
- 手写 `PYTHONPATH=src ...`
- example 自己改 `sys.path`

### 4. Separate Examples, Tests, And Scripts

这三类对象职责不同：

- `examples/`
  - 面向开发者
  - 用 public API 展示最小可用法
- `tests/`
  - 面向回归验证
  - 可覆盖内部语义与边界
- `scripts/`
  - 辅助维护脚本
  - 不承担主要示例职责

建立环境任务时，要保证三者都能在同一项目环境下运行，但不要让它们互相替代。

### 5. Verify In The Same Shape Developers Will Use

环境任务完成前，至少验证两类路径：

1. 项目环境路径

```bash
uv sync --extra dev
uv run python examples/ai/01_complete.py
```

2. 仓库级命令路径

```bash
make example-ai-complete
make test-ai
```

如果只验证编辑器里能跑，或只验证某个 shell 已激活环境能跑，这个任务不算完成。

---

## Design Rules

### 1. Prefer Standard Packaging Over Path Injection

优先修：

- `pyproject.toml`
- build backend
- package discovery

不优先修：

- `sys.path`
- 本地绝对路径
- 编辑器额外路径

例外只适用于：

- 非正式 spike
- 一次性调试脚本

而不适用于正式 example。

### 2. Prefer One Canonical Runtime Path

一个项目应有一条主推荐运行路径。

在当前 `loushang` 中，应优先推荐：

- `uv sync --extra dev`
- `uv run ...`

根 `Makefile` 应建立在这条主路径之上，而不是另行发明一套环境语义。

### 3. Examples Should Use Public API Only

example 的价值在于：

- 作为开发者参考
- 作为外部 API 使用示例

因此 example 应尽量只 import：

- 公共 API
- 少量明确允许的 public helper

不应依赖：

- 内部测试 helper
- 私有模块细节
- 局部路径修补

### 4. Makefile Should Be A Thin Entry Layer

`Makefile` 的职责是：

- 暴露统一入口
- 轻量编排

不应承担：

- 隐式修环境
- 补路径
- 私下替换运行语义

例如：

```make
example-ai-complete:
	uv run python examples/ai/01_complete.py
```

这类入口是合适的。

### 5. Development Environment Tasks Must Be Reproducible

建立环境任务的完成标准，不是“当前机器上能跑一次”，而是：

- 新开发者按文档步骤能跑
- 仓库命令能跑
- examples/tests 都能跑
- 不依赖未说明的 shell 状态

### 6. Avoid Dual Reality

不要同时维持两套世界：

- 一套给 tests
- 一套给 examples
- 一套给 README
- 一套给 Makefile

如果存在这种情况，说明环境任务还没有设计完成。

---

## Verification Checklist

完成一个 Python 开发环境任务前，应至少检查：

- `pyproject.toml` 是否声明了 build system
- `src` 布局是否被正确发现
- `uv sync --extra dev` 是否能安装项目自身
- `uv run python examples/...` 是否能运行
- `pytest` 是否在同一环境里运行
- `ruff` / `mypy` 是否在同一环境里运行
- 根 `Makefile` 是否只是统一入口，而非另一套隐含环境逻辑

---

## Anti-Patterns

以下做法应视为反模式：

- 在正式 example 中写 `sys.path.insert(...)`
- 为了让示例运行而修改库的 public surface
- 依赖 `python` / `python3` 名字碰巧存在
- 依赖当前 shell 已激活某个未说明环境
- README 写 `uv run`，Makefile 却走另一套命令
- tests 能 import，examples 不能 import

---

## Recommended Completion Standard

可以把“建立 Python 开发环境任务已完成”定义为：

1. `uv sync --extra dev` 成功
2. `uv run python examples/...` 成功
3. `make test` / `make test-ai` 成功
4. `make example-*` 成功
5. examples 不包含路径 hack
6. 项目源码通过标准 packaging 被环境识别

---

## Current Loushang Recommendation

对 `loushang` 当前阶段，推荐固定为：

- 根 `src` 布局
- 根 `pyproject.toml`
- `setuptools` build backend
- `uv sync --extra dev`
- `uv run python examples/...`
- 根 `Makefile` 用 `uv run` 暴露 example 入口

这意味着：

- examples 应保持干净
- 环境问题优先修 packaging 和 runtime entry
- 不再通过 example 内部路径修补来兜底
