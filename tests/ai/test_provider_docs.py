from __future__ import annotations

from pathlib import Path

from loushang.ai.model import load_builtin_model_registry


def test_provider_docs_cover_new_provider_configuration() -> None:
    docs = Path("examples/ai/README.md").read_text(encoding="utf-8")
    registry = load_builtin_model_registry()

    for provider_id in [
        "anthropic",
        "baidu-qianfan",
        "dashscope",
        "deepseek",
        "minimax",
        "moonshot",
        "openai",
        "stepfun",
        "tencent-hunyuan",
        "volcano-ark",
        "zai",
    ]:
        assert registry.get_provider(provider_id) is not None
        assert f"`{provider_id}`" in docs or f"- `{provider_id}`" in docs

    for env_name in [
        "ANTHROPIC_API_KEY",
        "QIANFAN_API_KEY",
        "DASHSCOPE_API_KEY",
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "STEPFUN_API_KEY",
    ]:
        assert env_name in docs


def test_ai_readme_documents_curated_builtin_catalog_and_archive() -> None:
    docs = Path("src/loushang/ai/README.md").read_text(encoding="utf-8")

    assert "models.curated.v2.json" in docs
    assert "models-v1-full.json.gz" in docs
    assert "model.upstream_id" in docs
    assert "ResolvedRequest.upstream_model_id" in docs
    assert "kimi-k2.6" in docs
