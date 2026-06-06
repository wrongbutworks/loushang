# Loushang Subsystem Diagram

## Scope

本文档给出 `loushang` 当前包级子系统关系图。
箭头表示依赖方向：`A --> B` 表示 `A` 依赖 `B`。

```mermaid
graph TD
    AI[loushang-ai]
    AGENT[loushang-agent]
    METHOD[loushang-method]
    WORK[loushang-work]
    TUI[loushang-tui<br/>generic terminal UI]
    CHANNEL[loushang-channel<br/>target only]

    subgraph CODING[loushang-coding]
        CODING_CORE[coding core<br/>runtime / session / tools]
        CODING_UI[coding.ui<br/>terminal product adapter]
    end

    AGENT --> AI
    CODING_CORE --> AGENT
    CODING_CORE --> METHOD
    CODING_CORE --> WORK

    CODING_UI --> CODING_CORE
    CODING_UI --> TUI

    CHANNEL -. future protocol boundary .-> WORK
```

`loushang-tui` is a generic terminal UI subsystem. Coding-specific terminal behavior lives in
`loushang.coding.ui`, which depends on both `loushang-tui` and the headless
`loushang-coding` core.

`loushang-channel` is target architecture only. The current RPC implementation is the
`loushang.coding.mode.RpcMode` surface, not a package-level `src/loushang/channel/`
implementation.
