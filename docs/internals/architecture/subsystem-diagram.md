# Loushang Subsystem Diagram

## Scope

本文档给出 `loushang` 当前建议的子系统关系图。
箭头表示依赖方向：`A --> B` 表示 `A` 依赖 `B`。

```mermaid
graph TD
    AI[loushang-ai]
    AGENT[loushang-agent]
    CHANNEL[loushang-channel]
    TUI[loushang-tui<br/>generic terminal UI]
    METHODS[loushang-methods]

    subgraph CODING[loushang-coding]
        CODING_CORE[coding core<br/>runtime / session / tools]
        CODING_UI[coding.ui<br/>terminal product adapter]
    end

    AGENT --> AI
    CODING_CORE --> AGENT
    CODING_CORE --> CHANNEL
    CODING_CORE --> METHODS

    CODING_UI --> CODING_CORE
    CODING_UI --> TUI
```

`loushang-tui` is a generic terminal UI subsystem. Coding-specific terminal behavior lives in `loushang.coding.ui`, which depends on both `loushang-tui` and the headless `loushang-coding` core.
