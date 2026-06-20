from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import loushang.ai as ai
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.model import load_builtin_model_registry

REPO_ROOT = Path(__file__).resolve().parents[2]

ROOT_EXPORTS_BASELINE = [
    "ApiProviderRegistry",
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStream",
    "EventStream",
    "Context",
    "Message",
    "Model",
    "StopReason",
    "ModelCallOptions",
    "StreamOptions",
    "SimpleStreamOptions",
    "AnthropicOptions",
    "AzureOpenAIResponsesOptions",
    "OpenAICompletionsOptions",
    "OpenAICodexResponsesOptions",
    "OpenAIResponsesOptions",
    "PairingMode",
    "ThinkingLevel",
    "ThinkingBudgets",
    "CacheRetention",
    "Transport",
    "ImagePart",
    "TextPart",
    "ThinkingPart",
    "Tool",
    "ToolCall",
    "ToolResultMessage",
    "UserMessage",
    "Usage",
    "calculate_cost",
    "clear_api_providers",
    "complete",
    "complete_simple",
    "create_assistant_message_event_stream",
    "get_api_provider",
    "get_env_api_key",
    "get_model",
    "get_overflow_patterns",
    "get_providers",
    "is_context_overflow",
    "list_api_providers",
    "list_models",
    "models_are_equal",
    "normalize_context",
    "normalize_tool_call_id_for_model",
    "parse_streaming_json",
    "register_api_provider",
    "register_builtin_ai_providers",
    "reset_api_providers",
    "stream",
    "stream_simple",
    "transform_messages",
    "validate_tool_arguments",
    "validate_tool_call",
]

CATALOG_PROVIDER_BASELINE = [
    "amazon-bedrock",
    "ant-ling",
    "anthropic",
    "azure-openai-responses",
    "baidu-qianfan",
    "cerebras",
    "cloudflare-ai-gateway",
    "cloudflare-workers-ai",
    "dashscope",
    "deepseek",
    "fireworks",
    "github-copilot",
    "google",
    "google-vertex",
    "groq",
    "huggingface",
    "kimi-coding",
    "minimax",
    "minimax-cn",
    "mistral",
    "moonshot",
    "moonshotai",
    "moonshotai-cn",
    "nvidia",
    "openai",
    "openai-codex",
    "opencode",
    "opencode-go",
    "openrouter",
    "stepfun",
    "tencent-hunyuan",
    "together",
    "vercel-ai-gateway",
    "volcano-ark",
    "xai",
    "xiaomi",
    "xiaomi-token-plan-ams",
    "xiaomi-token-plan-cn",
    "xiaomi-token-plan-sgp",
    "zai",
    "zai-coding-cn",
]

REGISTERED_PROVIDER_APIS_BASELINE = [
    "anthropic-messages",
    "azure-openai-responses",
    "bedrock-converse-stream",
    "openai-codex-responses",
    "openai-completions",
    "openai-responses",
]

KNOWN_BASELINE_DEBT = {
    "root_exports_include_advanced_provider_management": [
        "ApiProviderRegistry",
        "register_api_provider",
        "clear_api_providers",
    ],
    "root_exports_include_provider_specific_options": [
        "AnthropicOptions",
        "AzureOpenAIResponsesOptions",
        "OpenAICodexResponsesOptions",
        "OpenAICompletionsOptions",
        "OpenAIResponsesOptions",
    ],
    "core_bootstrap_registers_non_target_adapters": [
        "azure-openai-responses",
        "bedrock-converse-stream",
        "openai-codex-responses",
    ],
    "builtin_catalog_is_over_curated_budget": {
        "providers": 41,
        "endpoints": 56,
        "models": 1000,
    },
    "legacy_compat_is_still_present": {
        "endpoints": 38,
        "models": 618,
    },
}


def test_root_exports_baseline_snapshot() -> None:
    assert ai.__all__ == ROOT_EXPORTS_BASELINE
    assert len(ai.__all__) == 55


def test_builtin_provider_and_catalog_count_baseline() -> None:
    registry = load_builtin_model_registry()
    providers = registry.list_providers()
    endpoints = registry.list_endpoints()
    models = registry.list_models()

    assert [provider.id for provider in providers] == CATALOG_PROVIDER_BASELINE
    assert len(providers) == 41
    assert len(endpoints) == 56
    assert len(models) == 1000
    assert sum(1 for endpoint in endpoints if endpoint.compat) == 38
    assert sum(1 for model in models if model.compat) == 618


def test_registered_provider_api_baseline_snapshot() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert sorted(provider.api for provider in registry.list_api_providers()) == (
        REGISTERED_PROVIDER_APIS_BASELINE
    )


def test_test_and_example_inventory_baseline() -> None:
    ai_test_files = sorted((REPO_ROOT / "tests/ai").rglob("test_*.py"))
    provider_test_files = sorted((REPO_ROOT / "tests/providers").rglob("test_*.py"))
    example_files = sorted((REPO_ROOT / "examples/ai").rglob("*.py"))

    assert len(ai_test_files) == 32
    assert len(provider_test_files) == 6
    assert len(example_files) == 13


def test_known_baseline_debt_snapshot() -> None:
    provider_registry = ApiProviderRegistry()
    register_builtin_ai_providers(provider_registry)
    model_registry = load_builtin_model_registry()
    providers = model_registry.list_providers()
    endpoints = model_registry.list_endpoints()
    models = model_registry.list_models()

    for export in KNOWN_BASELINE_DEBT["root_exports_include_advanced_provider_management"]:
        assert export in ai.__all__
    for export in KNOWN_BASELINE_DEBT["root_exports_include_provider_specific_options"]:
        assert export in ai.__all__

    assert sorted(provider.api for provider in provider_registry.list_api_providers() if provider.api in {
        "azure-openai-responses",
        "bedrock-converse-stream",
        "openai-codex-responses",
    }) == KNOWN_BASELINE_DEBT["core_bootstrap_registers_non_target_adapters"]
    assert KNOWN_BASELINE_DEBT["builtin_catalog_is_over_curated_budget"] == {
        "providers": len(providers),
        "endpoints": len(endpoints),
        "models": len(models),
    }
    assert KNOWN_BASELINE_DEBT["legacy_compat_is_still_present"] == {
        "endpoints": sum(1 for endpoint in endpoints if endpoint.compat),
        "models": sum(1 for model in models if model.compat),
    }


def test_plan_status_script_reports_committed_aiq_items() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ai/plan_status.py", "--json"],
        check=True,
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    payload = json.loads(result.stdout)

    assert payload["plan_file"] == (
        "docs/internals/plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md"
    )
    assert payload["total"] == 61
    assert payload["complete"] >= 2
    completed = {
        item["plan_id"]: item
        for item in payload["items"]
        if item["status"] == "complete"
    }
    assert completed["AIQ-001"]["commit_message"] == (
        "docs(ai): add quality hardening charter"
    )
    assert completed["AIQ-002"]["commit_message"] == (
        "chore(codex): add AI review agents"
    )
    assert completed["AIQ-003"]["commit_message"] == (
        "test(ai): capture baseline contracts"
    )
    assert completed["AIQ-001"]["subject_matches_plan"] is True
    assert completed["AIQ-002"]["subject_matches_plan"] is True
    assert completed["AIQ-003"]["subject_matches_plan"] is True
