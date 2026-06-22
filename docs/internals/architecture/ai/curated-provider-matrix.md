# Curated Provider Matrix

This matrix tracks the provider set being assembled in
`models.curated.v2.json`. The runtime default remains the legacy catalog until
AIQ-056 switches the package data.

| Provider | Endpoint | API | Models | Auth env | Evidence | Offline smoke |
|---|---|---|---|---|---|---|
| `anthropic` | `anthropic-messages` | `anthropic-messages` | `claude-opus-4-8`, `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | `catalog-evidence/anthropic.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `moonshot` | `openai-completions` | `openai-completions` | `kimi-k2.6`, `kimi-k2.7-code` | `MOONSHOT_API_KEY` | `catalog-evidence/moonshot.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |
| `openai` | `openai-responses` | `openai-responses` | `gpt-5.5`, `gpt-5.4-mini` | `OPENAI_API_KEY` | `catalog-evidence/openai.md` | `uv run pytest tests/ai/test_curated_catalog.py -q` |

Generic provider smoke for curated entries is intentionally offline in this
phase: load the curated catalog file with `load_model_registry_from_file`, look
up provider, endpoint, and selected models, and verify auth, endpoint protocol,
capabilities, and evidence links. Live API calls require credentials and must be
recorded in the provider evidence file.
