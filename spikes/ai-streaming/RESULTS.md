# AI Streaming Spike Results

## Scope

本文档记录 `spikes/ai-streaming` 的实际验证结果。  
它只记录实验事实、观察和结论，不替代正式架构文档。

## Files

本次 spike 涉及的原型文件：

- `types.py`
- `abort_signal.py`
- `event_stream.py`
- `assembler.py`
- `demo.py`

## Run Commands

执行过的命令：

```bash
python3 demo.py
python3 -m py_compile abort_signal.py assembler.py demo.py event_stream.py types.py
```

## Scenario Results

### Scenario 1: Normal Completion

结果：通过

观察：

- 总事件数：`6`
- 最后事件类型：`done`
- 最终 `stop_reason`：`stop`

结论：

- `async for event in stream` 与 `await stream.result()` 可以自然协同
- 正常结束路径可稳定收敛到最终 `AssistantMessage`

### Scenario 2: Aborted Mid-Stream

结果：通过

观察：

- 总事件数：`4`
- 最后事件类型：`error`
- 最终 `stop_reason`：`aborted`

结论：

- `signal.cancelled: bool` 的最小语义足以表达取消
- `aborted` 可以稳定映射到最终 `AssistantMessage`

### Scenario 3: Mixed Consumption

结果：通过

观察：

- 先消费部分事件，再调用 `result()`
- 最终 `stop_reason`：`stop`

结论：

- 事件消费与最终结果收敛不会互相冲突

### Scenario 4: Reader/Writer Separation

结果：通过

观察：

- public 消费方只需要接触 stream
- assembler 只依赖 writer 最小接口：
  - `push`
  - `finish`
  - `fail`

结论：

- internal `(stream, writer)` 分离是可行的
- 不需要把 writer-side 方法暴露为 public API

### Scenario 5: Event Throughput Smoke Test

结果：通过

观察：

- `10_000` 个 `text_delta`
- 总事件数：`10004`
- 耗时约：`0.057s`
- 最终 `stop_reason`：`stop`

结论：

- 当前流对象、writer 与 assembler 结构没有暴露出明显的结构性性能问题
- 该结果仅说明 smoke-level 可行，不构成正式 benchmark 结论

## Issues Found

### Module Naming Collision

问题：

- spike 目录下的 `types.py` 会与 Python 标准库 `types` 产生导入冲突

处理：

- `demo.py` 中使用显式 bootstrap，以别名方式加载本地模块

影响：

- 这不是 streaming/cancellation 模型本身的问题
- 但说明正式实现应放入包命名空间，例如 `loushang/ai/types.py`
- 不建议最终以裸脚本目录形式组织正式实现

## Summary

本次 spike 支持以下判断：

1. `AssistantMessageEventStream` 作为只读 public contract 是可行的
2. internal reader/writer 分离是可行的
3. `signal.cancelled: bool` 的最小取消语义是可行的
4. `stream().result()` 作为 `complete()` 的基础模型是可行的
5. 默认 `asyncio` 实现不会阻碍 public contract 保持 runtime-neutral

## Limits

本次 spike 尚未验证：

- 真实 provider SDK 接入
- 多 provider 差异下的 raw part 统一
- 多任务取消传播策略
- tool call / thinking / image 的完整事件矩阵
- 长时间运行下的严格性能与内存行为
