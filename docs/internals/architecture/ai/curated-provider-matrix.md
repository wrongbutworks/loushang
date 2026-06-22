# Curated Provider Matrix

This matrix tracks the provider set being assembled in
`models.curated.v2.json`. AIQ-056 makes this curated catalog the runtime
default; the legacy full catalog is kept only as the compressed archive under
`docs/internals/archive/ai/model-catalog/`.

| Provider | Endpoint | API | Models | Auth env | Evidence | Offline smoke |
|---|---|---|---|---|---|---|
| `anthropic` | `anthropic-messages` | `anthropic-messages` | `claude-opus-4-8`, `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | `catalog-evidence/anthropic.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `baidu-qianfan` | `openai-completions-cn` | `openai-completions` | `ernie-5.1` | `QIANFAN_API_KEY`, `BAIDU_QIANFAN_API_KEY` | `catalog-evidence/baidu-qianfan.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |
| `dashscope` | `openai-responses` | `openai-responses` | `qwen3.7-max`, `qwen3.7-plus` | `DASHSCOPE_API_KEY` | `catalog-evidence/dashscope.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `deepseek` | `openai-completions` | `openai-completions` | `deepseek-v4-flash`, `deepseek-v4-pro` | `DEEPSEEK_API_KEY` | `catalog-evidence/deepseek.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |
| `minimax` | `anthropic-messages` | `anthropic-messages` | `MiniMax-M3` | `MINIMAX_API_KEY` | `catalog-evidence/minimax.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_anthropic_messages_mapping.py -q` |
| `moonshot` | `openai-completions` | `openai-completions` | `kimi-k2.6`, `kimi-k2.7-code` | `MOONSHOT_API_KEY` | `catalog-evidence/moonshot.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `openai` | `openai-responses` | `openai-responses` | `gpt-5.5`, `gpt-5.4-mini` | `OPENAI_API_KEY` | `catalog-evidence/openai.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `stepfun` | `openai-completions` | `openai-completions` | `step-3.7-flash` | `STEP_API_KEY`, `STEPFUN_API_KEY` | `catalog-evidence/stepfun.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |
| `tencent-hunyuan` | `openai-completions` | `openai-completions` | `hunyuan-turbos-latest` | `HUNYUAN_API_KEY` | `catalog-evidence/tencent-hunyuan.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `volcano-ark` | `openai-completions-cn-beijing` | `openai-completions` | `doubao-seed-2-0-lite-260215` | `ARK_API_KEY` | `catalog-evidence/volcano-ark.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |
| `zai` | `openai-completions` | `openai-completions` | `glm-5.2`, `glm-5.1` | `ZAI_API_KEY` | `catalog-evidence/zai.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |

Generic provider smoke for curated entries is intentionally offline: load the
built-in catalog, look up provider, endpoint, and selected models, and verify
auth, endpoint protocol, capabilities, and evidence links. Live API calls
require credentials and must be recorded in the provider evidence file.
