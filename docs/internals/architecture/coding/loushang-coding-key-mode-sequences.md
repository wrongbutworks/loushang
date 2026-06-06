# Loushang Coding Key Mode Sequences

## Scope

本文档描述 `loushang-coding` 关键 mode 的运行时序。

本文档当前覆盖：

- `print mode`
- `json mode`
- `rpc mode`
- native `tui` / `interactive` mode

本文档目标是回答：

- 不同 mode 如何进入统一 runtime 主干
- mode 与 `AgentSessionRuntime` / `AgentSession` 如何协作
- 哪些时序应尽量对齐 `reference coding agent`
- 哪些地方是当前刻意保留的简化

本文档不展开：

- 字段级协议
- 详细 UI 行为
- channel 协议细节
- method-driven TUI 的 step status layer；该部分见 ARD-006

## Design Basis

本文档建立在以下文档之上：

- [Loushang Coding System Context](./loushang-coding-system-context.md)
- [Loushang Coding Component Interfaces](./loushang-coding-component-interfaces.md)
- [Loushang Coding Component Dependencies](./loushang-coding-component-dependencies.md)
- [reference coding agent Internal Dependency Overview](./reference/reference-coding-agent/architecture-dependencies.md)

## Shared Runtime Spine

当前所有 mode 都应尽量共享同一条主干：

```text
caller
  -> Bootstrap / SDK
  -> AgentSessionRuntime
  -> AgentSession
  -> loushang-agent
  -> loushang-ai
```

也就是说，mode 只是 I/O adapter，而不是另一套运行核心。

## Shared Core Component Sequence

如果把 `loushang-coding` 压成一轮最核心的组件时序，当前建议表达为：

```mermaid
sequenceDiagram
  autonumber
  participant Caller as CLI / SDK Caller
  participant Boot as Bootstrap / SDK
  participant Runtime as AgentSessionRuntime
  participant Session as AgentSession
  participant Store as SessionManager / store
  participant Loader as ResourceLoader / loader
  participant Prompt as PromptAssembler / prompt
  participant Agent as loushang-agent
  participant AI as loushang-ai
  participant Event as event
  participant Mode as mode adapter

  Caller->>Boot: create_services(...) / create_runtime(...)
  Boot->>Runtime: create_session(...) or restore_session(...)
  Runtime->>Store: load(...) / build_session_context()
  Store-->>Runtime: SessionRecord + SessionContext
  Runtime-->>Caller: Session

  Caller->>Mode: start(runtime, session, options)
  Mode->>Session: subscribe(handle_event)
  Caller->>Mode: submit input
  Mode->>Session: prompt(user_input, options)

  Session->>Loader: load resources / runtime inputs
  Loader-->>Session: ResourceBundle
  Session->>Prompt: assemble_system_prompt(...) / assemble_prompt(...)
  Prompt-->>Session: PromptAssembly

  Session->>Agent: prompt(messages, system_prompt, tools, model)
  Agent->>AI: stream / complete
  AI-->>Agent: assistant stream / result

  opt tool call path
    Agent-->>Session: tool request
    Session->>Session: route tools / exec / policy
    Session->>Agent: tool result / continue
  end

  Agent-->>Session: agent lifecycle events
  Session->>Event: build AgentSessionEvent
  Event-->>Mode: serialized session event
  Mode->>Mode: project to text / json / rpc output

  Session->>Store: append messages / labels / summaries
  Store-->>Session: updated branch / rebuilt context

  opt post-turn hooks
    Session->>Session: retry / compaction / branch-summary checks
  end
```

### Reading Notes

- `session` 是核心业务编排中心
- `runtime` 只负责当前活动 session 生命周期，不负责 turn 内业务
- `mode` 只消费 `AgentSessionEvent` 并做输出投影
- `store` 负责持久化与 context rebuild，不负责 run-loop 决策
- `prompt`、`tools`、`exec`、`policy`、`compaction` 都应作为 `session` 的协作者出现，而不是替代 `session`

## 1. `print mode`

### Intent

- 面向终端文本输出
- 最小交互
- 单次执行或串行执行输入

### Sequence

```mermaid
sequenceDiagram
  autonumber
  participant User as CLI User
  participant CLI as CLI
  participant Boot as Bootstrap
  participant Runtime as AgentSessionRuntime
  participant Session as AgentSession
  participant Print as PrintMode
  participant Agent as loushang-agent
  participant AI as loushang-ai

  User->>CLI: run print mode
  CLI->>Boot: create_services(...)
  CLI->>Boot: create_agent_session_runtime(...)
  Boot-->>CLI: Runtime
  CLI->>Runtime: create_session(...) / restore_session(...)
  Runtime-->>CLI: Session
  CLI->>Print: start(runtime, session, options)

  alt direct CLI input
    User->>Print: command text
  else stdin / batch input
    Print->>Print: read input stream
  end

  Print->>Session: subscribe(handle_event)
  Print->>Session: prompt(user_input, options)
  Session->>Agent: prompt(...)
  Agent->>AI: stream / complete
  AI-->>Agent: assistant stream / result
  Agent-->>Session: agent events
  Session-->>Print: AgentSessionEvent
  Print->>Print: project to stdout/stderr text

  opt tool execution
    Session->>Session: route tools / exec / policy
    Session-->>Print: tool execution events
    Print->>Print: print tool progress / result
  end

  Session-->>Print: agent_end / completion
  Print-->>CLI: exit code
```

### Reading Notes

- `print mode` 不应直接调用 `loushang-agent`
- `print mode` 只通过 `AgentSession` 驱动运行
- `print mode` 主要消费 `AgentSessionEvent` 并投影为文本

### Alignment With reference coding agent

- 对齐 `PrintMode` 作为 mode adapter 的定位
- 对齐“统一 session facade 驱动 runtime，再由 mode 投影输出”的主思路

## 2. `print mode` 的 JSON projection

### Intent

- 面向结构化输出
- 适合脚本、管道、自动化场景
- 与 `print mode` 共用相同 session 主干
- 当前应视为 `PrintMode` 的第二输出投影，而不是独立 adapter object

### Sequence

```mermaid
sequenceDiagram
  autonumber
  participant Caller as CLI / SDK caller
  participant Boot as Bootstrap
  participant Runtime as AgentSessionRuntime
  participant Session as AgentSession
  participant Print as PrintMode
  participant Agent as loushang-agent
  participant AI as loushang-ai

  Caller->>Boot: create_agent_session_runtime(...)
  Boot-->>Caller: Runtime
  Caller->>Runtime: create_session(...)
  Runtime-->>Caller: Session
  Caller->>Print: start(runtime, session, output_mode="json")

  Print->>Session: subscribe(handle_event)
  Caller->>Print: submit command
  Print->>Session: prompt(user_input, options)
  Session->>Agent: prompt(...)
  Agent->>AI: stream / complete
  AI-->>Agent: assistant stream / result
  Agent-->>Session: agent events
  Session-->>Print: AgentSessionEvent
  Print->>Print: project event to JSON records or final structured result

  opt final-only mode
    Print->>Print: emit final assistant payload only
  else streaming-json mode
    Print->>Print: emit event stream incrementally
  end

  Session-->>Print: completion
  Print-->>Caller: structured output + exit status
```

### Reading Notes

- `json` 与 `print` 的核心差别不在运行主干，而在输出投影
- 当前应把它建模为 `PrintMode(output_mode="json")`
- 用户层仍可保留 `json mode` 这一运行形态命名

### Alignment With reference coding agent

- 对齐 `reference CLI` 中 `--mode json` 作为 `runPrintMode(...)` 的结构化输出分支
- 对齐的是“相同 session 主干，不同输出投影”这一点
- 当前不建议再引入独立 `JsonMode` service object

## 3. `rpc mode`

### Intent

- 作为远程调用或宿主接入的 mode
- 前期不要求先依赖 `loushang-channel`
- 先以 mode adapter 形态成立
- 在架构对象层可表示为 `RpcMode`，也可落成 `runRpcMode(...)` 一类入口

### Sequence

```mermaid
sequenceDiagram
  autonumber
  participant Client as RPC Client
  participant RPC as RpcMode
  participant Boot as Bootstrap
  participant Runtime as AgentSessionRuntime
  participant Session as AgentSession
  participant Agent as loushang-agent
  participant AI as loushang-ai

  Client->>RPC: create/start session request
  RPC->>Boot: create_agent_session_runtime(...)
  Boot-->>RPC: Runtime
  RPC->>Runtime: create_session(...) / restore_session(...)
  Runtime-->>RPC: Session
  RPC->>Session: subscribe(handle_event)
  RPC-->>Client: session created / ready

  Client->>RPC: prompt / steer / follow_up / abort
  alt prompt
    RPC->>Session: prompt(...)
  else steer
    RPC->>Session: steer(...)
  else follow up
    RPC->>Session: follow_up(...)
  else abort
    RPC->>Session: abort()
  end

  Session->>Agent: prompt / continue / steer
  Agent->>AI: stream / complete
  AI-->>Agent: assistant stream / result
  Agent-->>Session: agent events
  Session-->>RPC: AgentSessionEvent
  RPC-->>Client: event / response projection

  opt session management
    Client->>RPC: switch / fork / list sessions
    RPC->>Runtime: switch_session(...) / fork_session(...) / list_sessions(...)
    Runtime-->>RPC: session result
    RPC-->>Client: projected result
  end
```

### Reading Notes

- `rpc mode` 是 mode adapter，不是另一套 runtime
- 当前阶段它不要求先依赖 `loushang-channel`
- 未来如果 `channel` 落地，`rpc mode` 可以改为承载 `channel` projection
- 这里的 `rpc mode` 首先表示运行形态，其次才是具体对象命名

### Alignment With reference coding agent

- 对齐 `rpc mode / rpc client` 作为 mode adapter 的定位
- 保留当前 `loushang` 的明确决定：
  - `channel` 有长期价值
  - 但不是 `rpc mode` 的前置实现条件

## 4. Native TUI / `interactive mode`

### Intent

- 面向 TUI 交互
- 通过 `loushang.coding.ui` 适配 coding session/runtime
- 依赖 `loushang.tui` 的 native terminal core primitives
- 当前不支持 `--method`；method integration 需等待 ARD-006 的前置条件

### Sequence

```mermaid
sequenceDiagram
  autonumber
  participant User as Terminal User
  participant CLI as CLI / tui runner
  participant App as NativeCodingApp
  participant Controller as CodingUiController
  participant Runtime as AgentSessionRuntime
  participant Session as AgentSession
  participant TUI as loushang-tui

  User->>CLI: loushang --tui / interactive resume
  CLI->>Runtime: create / restore / switch session
  Runtime-->>CLI: Session
  CLI->>App: create native coding app
  App->>TUI: render transcript / composer / surfaces
  User->>TUI: key input / paste / surface action
  TUI-->>App: InputEvent / intent
  App->>Controller: dispatch PromptIntent / AbortIntent / FollowUpIntent
  Controller->>Session: prompt / steer / follow_up / abort
  Session-->>App: AgentSessionEvent / native event projection
  App->>TUI: update display records / bottom frame / surfaces
```

### Reading Notes

- native TUI 是当前最重的 local product surface
- 在对象层由 `loushang.coding.ui` 承担 UI orchestration，而不是把 generic TUI 变成 coding runtime
- 它仍应：
  - 依赖 `AgentSessionRuntime`
  - 依赖 `AgentSession`
  - 订阅 `AgentSessionEvent`
  - 不绕过 session facade 直接驱动底层 runtime
- TUI + method 不应通过遍历 `prepared_turns` 快速打通；应等 method status layer 消费 `WorkEvent` / `WorkPlanRun` projection

### Alignment With reference coding agent

- 对齐 `InteractiveMode` 作为 UI orchestration layer 的边界
- 当前差异在于：
  - `reference CLI` 依赖 reference TUI
  - `loushang` 依赖 native terminal core，不采用 Textual/fullscreen 方案

## 5. Cross-Mode Invariants

当前建议把以下规则作为所有 mode 的共同约束：

1. mode 不直接驱动 `loushang-agent`
2. mode 不直接驱动 `loushang-ai`
3. mode 通过 `AgentSessionRuntime` 管理 session 生命周期
4. mode 通过 `AgentSession` 推进一次运行
5. mode 通过 `AgentSessionEvent` 获取运行时观察面

## 6. Strong Alignment With reference coding agent

当前时序设计中，最需要对齐 `reference coding agent` 的点是：

- `AgentSession` 是统一运行中心
- 不同 mode 共用同一 session 语义
- TUI / `PrintMode` / `RpcMode` 都只是适配层
- session event stream 是 mode 最重要的输入面

## 7. Current Simplifications

当前相对 `reference coding agent` 的简化主要包括：

- 还未展开 extension hook 时序
- 还未展开 compaction / retry / queue 的细粒度时序
- TUI + method 尚未打通，`--method` 在 TUI 中保持互斥
- `rpc mode` 仍未接入 `channel`

## Next Step

基于当前关键 mode 时序，后续建议继续：

1. TUI + method 前置条件跟踪，见 ARD-006
2. `rpc mode` 到 future `loushang.channel.rpc_jsonl` 的迁移草案，见 ARD-005
3. `print/json/rpc/tui` 的公共 mode/event boundary 继续收窄
