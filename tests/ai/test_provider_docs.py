from __future__ import annotations

from pathlib import Path

from loushang.ai.model import load_builtin_model_registry


def test_provider_docs_cover_new_provider_configuration() -> None:
    docs = Path("examples/ai/README.md").read_text(encoding="utf-8")
    registry = load_builtin_model_registry()

    for provider_id in [
        "openrouter",
        "cloudflare-ai-gateway",
        "cloudflare-workers-ai",
        "mistral",
        "google",
        "google-vertex",
        "amazon-bedrock",
    ]:
        assert registry.get_provider(provider_id) is not None
        assert f"`{provider_id}`" in docs or f"- `{provider_id}`" in docs

    for env_name in [
        "OPENROUTER_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "MISTRAL_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_VERTEX_ACCESS_TOKEN",
        "AWS_ACCESS_KEY_ID",
    ]:
        assert env_name in docs


def test_ai_readme_documents_upstream_model_id_rule() -> None:
    docs = Path("src/loushang/ai/README.md").read_text(encoding="utf-8")

    assert "model.upstream_id" in docs
    assert "ResolvedRequest.upstream_model_id" in docs
    assert "openai/gpt-oss-120b_free" in docs
    assert "bedrock-converse-stream" in docs
