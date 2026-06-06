# Loushang Development Workflow And Tooling

## Scope

本文档定义 `loushang` 在开发工作流、Python 工具链与 `Makefile` 命令入口上的约定。

本文档主要回答：

- 根工作区应如何 bootstrap
- 根 project 应如何接入统一开发环境
- 根 `Makefile` 应提供哪些入口
- 推荐的测试、lint、fmt、typecheck 命令入口是什么
- Cursor / VS Code 应如何选择解释器与执行环境

本文档不讨论：

- 某个具体子系统的内部实现
- CI 平台供应商选择
- 发布流水线具体细节
- 部署流程

---

## Relationship To Other Docs

本文档建立在：

- [Loushang Monorepo Conventions](/home/dev/workspace/loushang/docs/architecture/loushang-monorepo-conventions.md)

之上。

两者关系是：

- monorepo conventions
  - 回答目录、命名、源码根与 namespace 组织
- 本文
  - 回答如何开发、如何运行、如何统一命令入口

---

## Design Goals

当前开发工作流优先满足：

1. 新开发者能在 monorepo 根目录完成 bootstrap
2. 各子系统都能通过根命令被独立测试和检查
3. 全仓命令与子系统命令都保持统一风格
4. 编辑器、pytest、lint、类型检查共用同一环境
5. `agent -> ai` 这类依赖能直接 import 并运行

---

## Core Recommendation

当前建议冻结如下工作流：

- 一个根工作区虚拟环境：`.venv`
- 一个根 `pyproject.toml`
- 根 `src/` 作为统一源码根
- 根 `Makefile` 作为主要命令入口
- 子系统级命令通过根 `Makefile` 的目标暴露
- 统一通过根解释器运行：
  - tests
  - lint
  - fmt
  - typecheck

---

## Recommended Tooling

当前建议的 Python 开发工具链为：

- `uv`
  - 环境与依赖管理
- `pytest`
  - 测试执行
- `ruff`
  - lint + format
- `mypy`
  - 静态类型检查

说明：

- 这里冻结的是推荐方向，不是立即要求全仓已有配置全部到位
- 但新的 Python 子系统实现，建议默认按这一套工具链接入

---

## Long-Lived Worktree Lane Rule

当前建议为高频子系统开发保留长期 worktree lane：

```text
/home/dev/workspace/loushang
  control / integration lane
  checkout: main

/home/dev/workspace/loushang/.worktrees/tui
  Native TUI lane
  checkout: feature/tui-* or lane/tui/*

/home/dev/workspace/loushang/.worktrees/code
  V1 code hardening lane
  checkout: feature/code-* or lane/code/*

/home/dev/workspace/loushang/.worktrees/method
  method/work-runtime lane
  checkout: feature/method-* or lane/method/*

/home/dev/workspace/loushang/.worktrees/ai
  AI/provider lane
  checkout: feature/ai-* or lane/ai/*

/home/dev/workspace/loushang/.worktrees/agent
  agent-runtime lane
  checkout: feature/agent-* or lane/agent/*
```

语义：

- control lane 是唯一默认 checkout `main` 的 worktree。
- control lane 负责进度管理、方向协调、最终验证、集成、merge 与 push。
- TUI/code/method/AI/agent lane 长期保留，不作为一次性临时目录随意删除或改作他用。
- 以某个子系统为主的模块内开发，优先在对应 lane 内创建或切换任务分支。
- 其他 lane 的任务分支都以 `main` / `origin/main` 为 base，并定期 rebase 或 merge 最新 `main`。
- 跨 lane 接口变化应先在 control lane 明确方向，再由相关 lane 消费稳定契约。
- 切换任何 lane 的分支前，必须检查 dirty state，避免覆盖用户或其他 agent 的未提交修改。

这样做的目的不是制造长期分叉，而是把高频并行开发隔离在稳定 lane 中：

- `main` 始终作为可集成事实；
- TUI 回归、playback 与终端行为调试不污染 code hardening 工作区；
- code/session/runtime/tool/policy 改动不污染 TUI worktree；
- method 执行语义、MethodPlan/WorkEvent 投影与 work/method 集成不被 CLI/TUI/RPC 表面改动裹挟；
- AI 与 agent 层在需要时也能拥有相同的隔离与同步节奏。

---

## Workspace Bootstrap Rule

根工作区应提供一个统一 bootstrap 入口。

目标：

1. 创建根 `.venv`
2. 安装根 project
3. 安装基础开发工具

建议的仓库级目标命令为：

- `make bootstrap`

其语义应是：

- 准备整个仓库的开发环境，而不是只安装某一个子系统

---

## Root Makefile Rule

根 `Makefile` 是当前阶段的主要命令入口。

应负责：

- `bootstrap`
- `test`
- `lint`
- `fmt`
- `typecheck`
- `test-ai`
- `test-agent`
- `lint-ai`
- `fmt-ai`
- `typecheck-ai`

不应负责：

- 某个子系统内部复杂实现逻辑
- 脚本式的大量细节拼装

也就是说：

- 根 `Makefile` 是统一入口与轻量编排层
- 真正的执行仍然直接落到根 project 的工具链命令

---

## Command Shape Rule

当前建议保持命令命名统一：

### Repository Level

- `make bootstrap`
- `make test`
- `make lint`
- `make fmt`
- `make typecheck`
- `make test-ai`
- `make test-agent`
- `make lint-ai`
- `make fmt-ai`
- `make typecheck-ai`

这样有两个好处：

1. 根目录下的命令足够统一
2. 即使当前不做多 package，也保留了按子系统执行的开发体验

---

## Example Root Makefile Shape

根 `Makefile` 更适合写成统一入口，例如：

```make
.PHONY: bootstrap test lint fmt typecheck test-ai lint-ai fmt-ai typecheck-ai

bootstrap:
	uv venv .venv
	. .venv/bin/activate && uv pip install -e .[dev]

test:
	. .venv/bin/activate && python -m pytest tests -q

lint:
	. .venv/bin/activate && ruff check src tests

fmt:
	. .venv/bin/activate && ruff format src tests

typecheck:
	. .venv/bin/activate && mypy src

test-ai:
	. .venv/bin/activate && python -m pytest tests/ai -q

lint-ai:
	. .venv/bin/activate && ruff check src/loushang/ai tests/ai

fmt-ai:
	. .venv/bin/activate && ruff format src/loushang/ai tests/ai

typecheck-ai:
	. .venv/bin/activate && mypy src/loushang/ai
```

这里的重点不是命令逐字不变，而是：

- 根目录负责统一入口
- 子系统粒度通过目标名体现
- 不要求当前阶段引入子包 `Makefile`

---

## Workspace Install Workflow

当前推荐工作流是：

1. 在仓库根目录创建 `.venv`
2. 将整个根 project 安装到该环境
3. 编辑器始终使用这个统一环境

例如：

```bash
cd /home/dev/workspace/loushang
uv venv .venv
. .venv/bin/activate
uv pip install -e .[dev]
```

这样做的结果是：

- `loushang.ai` 可直接 import
- `loushang.agent` 可直接 import
- `agent` 对 `ai` 的本地依赖变更可立即生效

---

## Editor Rule

在 Cursor / VS Code 中，推荐做法是：

1. 打开仓库根目录
2. 选择根 `.venv` 作为 Python interpreter
3. 不依赖手写 `PYTHONPATH`
4. 不把 `extraPaths` 作为主方案

原因：

- 统一解释器能让 import、测试、lint、typecheck 使用同一环境
- 根 `src/` layout 已足够支撑跳转与运行

---

## Cross-Subsystem Dependency Workflow

当 `agent` 依赖 `ai` 时，推荐流程是：

1. `ai` 代码存在于 `src/loushang/ai`
2. `agent` 代码存在于 `src/loushang/agent`
3. `agent` 直接通过 `from loushang.ai import ...` 使用 `ai`
4. 根 `.venv` 与根 project 安装态负责统一解析
5. 根 `Makefile` 暴露：
   - `make test-ai`
   - `make test-agent`

这样：

- 架构边界仍然是清楚的
- 本地开发体验也是顺畅的

---

## What Not To Do

当前不建议采用以下做法作为正式规范：

### 1. 每个子系统一个 git repo

原因：

- 当前边界仍在演进
- 会增加跨子系统协调成本

### 2. 只靠 `PYTHONPATH`

原因：

- 运行时、编辑器、测试环境容易漂移

### 3. 只靠编辑器 `extraPaths`

原因：

- 这只能解决部分跳转问题，不能稳定解决运行与测试环境

### 4. 在当前阶段先上多 package + 多 editable install

原因：

- 当前实现重点是先把子系统落成代码
- 不是先引入 package 管理复杂度

---

## Recommended Initial Rollout

当前更稳的落地顺序是：

1. 先建立：
   - 根 `pyproject.toml`
   - 根 `Makefile`
   - `src/loushang/ai`
2. 验证：
   - workspace bootstrap
   - Cursor / VS Code import 解析
   - `make test-ai`
3. 再把同一规范扩展到：
   - `agent`
   - `channel`

也就是说：

- 不需要一开始就把所有子系统都脚手架好
- 但第一批落地时就应按统一规范来

---

## Impact On Current AI Plan

这份规范对当前 `loushang-ai` 实现计划的约束是：

1. 代码应采用：
   - `src/loushang/ai/`
2. 测试应采用：
   - `tests/ai/`
3. 命令入口应通过根 `Makefile` 暴露
4. 根 project 应负责：
   - `.venv`
   - 安装
   - 测试工具

因此，`loushang-ai` 实现计划应与这份 workflow/tooling 规范对齐，而不能继续假设 `packages/ai` 与局部 `Makefile`。

---

## Takeaway

`loushang` 当前更稳的开发工作流是：

- 一个 monorepo
- 一个统一 workspace virtualenv
- 一个根 project
- `src/loushang/*` 命名空间源码布局
- 根 `Makefile` 做统一命令入口
- 编辑器统一指向根 `.venv`

这样能同时满足：

- 架构边界清楚
- 当前启动成本较低
- 跨子系统依赖稳定
- Cursor / VS Code 体验稳定
