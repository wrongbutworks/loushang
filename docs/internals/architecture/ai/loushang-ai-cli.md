# Loushang-AI CLI 设计（loushang-ai）

## 目标
- 以命令行形式查询当前注册的 API/模型/端点信息
- 快速发起一次对话或补全调用（stream/complete）
- 支持显式加载外部 models.json 文件或目录

## 用户体验概览
- 入口：
  - python -m loushang.ai.cli ...
  - 或在项目虚拟环境中：uv run python -m loushang.ai.cli ...
- 示例：
  - 列表与详情
    - loushang-ai apis list
    - loushang-ai apis show openai-completions
    - loushang-ai models list --provider kimi
    - loushang-ai models show kimi-k2.5
    - loushang-ai endpoints show kimi:openai
  - 调用
    - loushang-ai chat --model kimi-k2.5 --message "你好" --stream
    - loushang-ai complete --model kimi-k2.5 --message "总结以下文本..." --json
    - 临时覆盖 baseUrl：uv run python -m loushang.ai.cli --base-url https://api.moonshot.cn/v1 chat --model kimi:openai:kimi-k2.5 --message "hi"

## 子命令
1) apis
   - list：列出 ApiProviderRegistry 中的 API 名称
   - show <api>：显示 provider api 的基础信息（名称，仅保留基础字段与可扩展位）
2) models
   - list [--provider P --api A]
   - show <model-id>：展示 capability（context 窗口、是否支持 thinking/image 等）
3) endpoints
   - list [--provider P]
   - show <provider>:<endpoint>：显示 baseUrl、regions、defaults、compat
4) chat/complete
   - chat：流式输出事件或 JSON 行；参数：--model/--message/--system/--timeout/--region/--transport/--retries/--json/--stream
   - complete：等待最终消息并打印；支持 --json 输出原始 AssistantMessage（dict）
## 技术实现
- 解析：argparse（避免额外依赖）
- 数据访问：
  - 使用 loushang.ai 的默认 ModelRegistry / ApiProviderRegistry
  - 从 registry 读取 provider / endpoint / model 信息，打印简表
  - 调用层复用 loushang.ai.api.stream/complete
- 外部模型目录/文件加载由 loader 显式调用完成，不再通过 CLI 配置或环境变量隐式注入默认 registry

## 错误与输出
- --json：以 JSON 行输出事件或对象
- 非 JSON 模式：TTY 友好的简洁输出
- 退出码：未知命令/找不到模型/网络或 provider 错误区分

## 未来扩展（留接口）
- auth：login/set/list
- tools：validate 工具参数
- diag：上下文溢出等诊断快捷命令（复用 utils.is_context_overflow）
