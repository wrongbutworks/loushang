# Curated Provider Matrix

This matrix tracks the provider set being assembled in
`models.curated.v2.json`. The runtime default remains the legacy catalog until
AIQ-056 switches the package data.

| Provider | Endpoint | API | Models | Auth env | Evidence | Offline smoke |
|---|---|---|---|---|---|---|
| `anthropic` | `anthropic-messages` | `anthropic-messages` | `claude-opus-4-8`, `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | `catalog-evidence/anthropic.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `dashscope` | `openai-responses` | `openai-responses` | `qwen3.7-max`, `qwen3.7-plus` | `DASHSCOPE_API_KEY` | `catalog-evidence/dashscope.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `deepseek` | `openai-completions` | `openai-completions` | `deepseek-v4-flash`, `deepseek-v4-pro` | `DEEPSEEK_API_KEY` | `catalog-evidence/deepseek.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |
| `moonshot` | `openai-completions` | `openai-completions` | `kimi-k2.6`, `kimi-k2.7-code` | `MOONSHOT_API_KEY` | `catalog-evidence/moonshot.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `openai` | `openai-responses` | `openai-responses` | `gpt-5.5`, `gpt-5.4-mini` | `OPENAI_API_KEY` | `catalog-evidence/openai.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `tencent-hunyuan` | `openai-completions` | `openai-completions` | `hunyuan-turbos-latest` | `HUNYUAN_API_KEY` | `catalog-evidence/tencent-hunyuan.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `zai` | `openai-completions` | `openai-completions` | `glm-5.2`, `glm-5.1` | `ZAI_API_KEY` | `catalog-evidence/zai.md` | `uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q` |

Generic provider smoke for curated entries is intentionally offline in this
phase: load the curated catalog file with `load_model_registry_from_file`, look
up provider, endpoint, and selected models, and verify auth, endpoint protocol,
capabilities, and evidence links. Live API calls require credentials and must be
recorded in the provider evidence file.
