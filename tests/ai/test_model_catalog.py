from __future__ import annotations

from loushang.ai.model import load_builtin_model_registry


def test_builtin_catalog_includes_kimi_coding_anthropic_endpoint() -> None:
    registry = load_builtin_model_registry()

    endpoint = registry.get_endpoint("moonshot", "kimi-code-anthropic")

    assert endpoint is not None
    assert endpoint.api == "anthropic-messages"
    assert endpoint.base_url == "https://api.kimi.com/coding"
    assert endpoint.get_model("kimi-for-coding") is not None


def test_builtin_catalog_resolves_kimi_coding_anthropic_model() -> None:
    registry = load_builtin_model_registry()

    model = registry.get_model("moonshot", "kimi-code-anthropic", "kimi-for-coding")

    assert model.provider_id == "moonshot"
    assert model.endpoint_id == "kimi-code-anthropic"
    assert model.id == "kimi-for-coding"
    assert model.supports_stream is True
    assert model.supports_tool_use is True
