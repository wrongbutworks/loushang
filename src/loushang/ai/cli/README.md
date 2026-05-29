# Loushang AI CLI

> Notice
> `loushang.ai.cli` is currently a development-stage helper for validation and debugging. It is not the core value surface of `loushang.ai`, not a stable product layer, and not the reference architecture for the package itself. Temporary hardcoded behavior or workflow shortcuts may exist here while the CLI is being used to exercise provider selection, auth flows, and multi-turn conversation paths.

`loushang.ai.cli` 当前的定位是一个轻量验证入口，用来直接验证：

- provider / endpoint / model 选择
- endpoint 级认证与登录
- 基础对话调用链
- 不同接入方式下的兼容性表现

推荐入口：

```bash
uv run python -m loushang.ai.cli console
```

## Console 能力

`console` 当前支持：

- 交互式选择 `provider -> endpoint -> auth -> model`
- 在 `endpoint` 选择后立即做认证准备
- 从环境变量读取认证信息
- 缺少环境变量时，提示输入临时凭证
- 当前进程内保留对话上下文
- 运行中支持：
  - `/help`
  - `/model`
  - `/switch`
  - `/switch-model`
  - `/reset`
  - `/exit`
- 选择页面支持返回上一层：
  - 输入 `b`
  - 或输入 `back`

## Console 约束

`console` 不是长期会话系统，当前要明确几个边界：

- 在 `console` 中手工输入的密钥或登录信息只保存在内存中，不会写入本地存储
- 环境变量只会被读取，不会被修改或回写
- 当前轮次内会保留对话上下文
- 退出 `console` 后，对话不会形成持久 session，也不会被恢复

也就是说：

- `context` 是“当前进程内有效”
- `session` 是“不会持久化”

## Auth 子命令

`auth` 子命令仍然保留，但它不是首选入口。

它更适合：

- 单独检查 OAuth provider 是否注册
- 查看本地已存储的 OAuth credentials
- 显式触发一次登录流程

示例：

```bash
uv run python -m loushang.ai.cli auth providers
uv run python -m loushang.ai.cli auth show openai-codex
uv run python -m loushang.ai.cli auth login openai-codex
```

对于大多数验证场景，优先使用 `console`。

## OpenAI Codex

`openai-codex` 当前按包内 OAuth provider 接入：

- `loushang-ai` 会直接发起 OpenAI Codex OAuth
- 浏览器完成登录后，会通过本地 callback 回到 CLI
- 如果自动 callback 没有到达，也支持手工粘贴最终 redirect URL 或授权码

也就是说，`loushang-ai` 不再把 `openai-codex` 主路径建模为“依赖外部 `codex login` 的桥接器”，而是把 OAuth 本身实现为 `ai` 层能力。
