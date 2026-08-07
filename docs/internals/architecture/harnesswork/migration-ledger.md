# HarnessWork Migration Ledger

[HarnessWork Architecture](README.md)

## Status

Status: **active migration ledger**.

基线：`origin/main` commit `b0410e13`，2026-08-07。本文按文件记录 canonical owner、兼容
入口和迁移门禁；代码变化必须同步更新本表。目标不是维持两套运行时，而是在迁移期间让
`loushang.work` 作为单向兼容 facade 指向唯一的 `loushang.harnesswork` kernel。

## Dependency Contract

```text
loushang.harness      -/-> loushang.harnesswork
loushang.harnesswork   -> loushang.harness public contracts + loushang.protocol
loushang.harnesswork  -/-> loushang.work / Product / Method / Ontology / Channel / UI
loushang.work facade   -> loushang.harnesswork
Product adapters       -> loushang.harnesswork + Product dependencies
```

`harnesswork` 的 operation、step payload 与 domain facts 保持 opaque；公共协议不接受
Coding、Method 或 Ontology 类型。

## File Ownership

| 原 `loushang.work` 文件 | 当前 canonical owner | 兼容入口 | 状态与下一门禁 |
| --- | --- | --- | --- |
| `types.py` | `loushang.harnesswork.types` | `loushang.work.types` forwarding | 已 `git mv`；old/new symbols identity 已测试 |
| `ports.py` | `loushang.harnesswork.ports` | `loushang.work.ports` forwarding | 已 `git mv`；executor/context 继续保持 opaque |
| `runtime.py` | `loushang.harnesswork.runtime` | `loushang.work.runtime` forwarding | 已 `git mv`；只有这一套可写 runtime |
| `event_log.py` | `loushang.harnesswork.event_log` | `loushang.work.event_log` forwarding | 已 `git mv`；JSONL schema 与 replay contract 不变 |
| `run_projection.py` | `loushang.harnesswork.run_projection` | `loushang.work.run_projection` forwarding | 已 `git mv`；orphan replay 语义不变 |
| `plan_projection.py` | `loushang.harnesswork.plan_projection` | `loushang.work.plan_projection` forwarding | 已迁移；以通用 operation/plan-start 识别 attempt，旧 Coding JSONL golden replay 已通过 |
| `cli.py` | `loushang.harnesswork.cli` | `loushang.work.cli` forwarding | 已迁移中立 log inspection；产品命令装配仍留 Product |
| `agent_projection.py` | Agent/Product integration | 原入口 | 不进入 HarnessWork core；后续迁往明确 adapter owner |
| `projection.py` | Agent/Product compatibility | 原入口 | 委托 agent projection，不进入 HarnessWork core |
| `session.py` | Agent-session/HarnessWork integration | 原入口 | 后续进入 integration adapter，不进入 durable kernel |

Coding executor、Channel codec/session binding 等消费者本阶段不搬入 core。它们将在 adapter
阶段改用新 canonical imports；在此之前旧 facade 是受支持的迁移入口。

## Public Surface

`loushang.harnesswork` 根包只导出产品中立 kernel 与 inspection 公共符号：

- types：operation/run/step/event/artifact/deviation 值对象；
- ports：accept/wait/cancel/query/subscribe、domain executor/cancellation/resolver 与 fact publisher；
- runtime：`WorkRuntime` 及生命周期错误；
- event log：Memory/JSONL backend、entry 与 position；
- run projection：`project_work_runs` 与 replay error；
- plan projection：`project_work_plan_runs`；
- CLI：JSONL event log 创建、路径解析和中立 inspect/format 操作。

`loushang.work` 根包暂时保留原完整 `__all__`，包括 CLI 和 Agent/session projection symbols。
kernel 子模块的旧入口与新入口必须返回同一 Python 对象。迁移不承诺稳定的
`type.__module__`、pickle qualified name 或未列入 `__all__` 的私有成员；JSONL wire/replay
兼容由既有 contract tests 保证。

## Required Gates

- 新根包不加载 `loushang.work`、Product、Method、Ontology、Channel、Agent、AI 或 UI；
- old/new kernel symbols identity、子模块 `__all__` 与两种 import order 均通过；
- `harness -/-> harnesswork`、`harnesswork -/-> work/channel` 保持单向；
- `tests/work/` 继续验证旧 facade，`tests/harnesswork/` 验证 canonical owner；
- 至少一个非 Coding opaque handler 从 accept 运行到 terminal 并可 replay；
- 旧 Coding plan JSONL golden fixture 在无 Coding sentinel 的 projection 上保持等价；
- 当前 Work 与 Channel contract suite 无回归。

## Deferred Surfaces

本阶段不增加 `WorkHandle`，不改变 `wait()` 的既有取消语义，不增加 typed result，也不承诺
崩溃后自动 resume。这些能力分别受 HarnessWork Architecture Phase 3a、3b 和独立 recovery
ARD 约束。
