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


def test_builtin_catalog_includes_issue_model_providers_from_pi_mono() -> None:
    registry = load_builtin_model_registry()

    deepseek = registry.get_model("deepseek", "openai-completions", "deepseek-v4-pro")
    zai = registry.get_model("zai", "openai-completions", "glm-5.1")
    zai_coding = registry.get_model(
        "zai-coding-cn", "openai-completions", "glm-5.1"
    )
    minimax = registry.get_model("minimax", "anthropic-messages", "MiniMax-M3")

    assert deepseek.api == "openai-completions"
    assert deepseek.auth is not None
    assert deepseek.auth.api_key_env == "DEEPSEEK_API_KEY"
    assert zai.api == "openai-completions"
    assert zai_coding.api == "openai-completions"
    assert minimax.api == "anthropic-messages"
    assert minimax.auth is not None
    assert minimax.auth.api_key_env == "MINIMAX_API_KEY"


def test_builtin_catalog_includes_issue_only_official_providers() -> None:
    registry = load_builtin_model_registry()

    hunyuan = registry.get_model(
        "tencent-hunyuan", "openai-completions", "hunyuan-turbos-latest"
    )
    doubao = registry.get_model(
        "volcano-ark",
        "openai-completions-cn-beijing",
        "doubao-seed-2-0-lite-260215",
    )
    ernie = registry.get_model(
        "baidu-qianfan", "openai-completions", "ernie-5.0"
    )
    stepfun = registry.get_model("stepfun", "openai-completions", "step-3.5-flash")

    assert hunyuan.base_url == "https://api.hunyuan.cloud.tencent.com/v1"
    assert hunyuan.auth is not None
    assert hunyuan.auth.api_key_env == "HUNYUAN_API_KEY"
    assert doubao.region == "cn-beijing"
    assert doubao.auth is not None
    assert "ARK_API_KEY" in doubao.auth.api_key_envs
    assert ernie.supports_image_input is True
    assert ernie.auth is not None
    assert "QIANFAN_API_KEY" in ernie.auth.api_key_envs
    assert stepfun.supports_thinking is True
    assert stepfun.auth is not None
    assert "STEPFUN_API_KEY" in stepfun.auth.api_key_envs


def test_builtin_catalog_skips_model_ids_with_colons() -> None:
    registry = load_builtin_model_registry()

    assert registry.find_model(
        "openrouter", "openai-completions", "openai/gpt-oss-120b:free"
    ) is None
    assert registry.get_model(
        "openrouter", "openai-completions", "openai/gpt-5.1"
    ) is not None
