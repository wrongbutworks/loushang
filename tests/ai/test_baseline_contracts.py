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
    "AssistantMessage",
    "AssistantMessageEvent",
    "AssistantMessageEventStream",
    "Context",
    "Message",
    "Model",
    "StopReason",
    "AIError",
    "AIErrorCode",
    "AIErrorInfo",
    "CallOptions",
    "SimpleCallOptions",
    "ReasoningOptions",
    "RetryOptions",
    "TimeoutOptions",
    "ThinkingLevel",
    "ThinkingBudgets",
    "StructuredOutputError",
    "StructuredOutputOptions",
    "StructuredOutputResult",
    "ImagePart",
    "TextPart",
    "ThinkingPart",
    "Tool",
    "ToolCall",
    "ToolResultMessage",
    "UserMessage",
    "Usage",
    "UsageCost",
    "UsageObservation",
    "EndpointQuotaQuery",
    "PlatformQuota",
    "PlatformQuotaError",
    "PlatformQuotaUnsupportedError",
    "complete",
    "complete_simple",
    "complete_structured",
    "endpoint_quota_query_for_model",
    "get_model",
    "list_models",
    "platform_quota_payload",
    "query_platform_quota",
    "stream",
    "stream_simple",
    "usage_observation_from_message",
    "usage_observation_payload",
]

CATALOG_PROVIDER_BASELINE = [
    "ant-ling",
    "anthropic",
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
    "openai-completions",
    "openai-responses",
]

ADVANCED_ROOT_EXPORTS_REMOVED = [
    "ApiProviderRegistry",
    "AnthropicOptions",
    "OpenAICodexResponsesOptions",
    "OpenAICompletionsOptions",
    "OpenAIResponsesOptions",
    "clear_api_providers",
    "get_api_provider",
    "get_env_api_key",
    "get_providers",
    "list_api_providers",
    "register_api_provider",
    "reset_api_providers",
]

KNOWN_BASELINE_DEBT = {
    "core_bootstrap_registers_non_target_adapters": [],
    "builtin_catalog_is_over_curated_budget": {
        "providers": 38,
        "endpoints": 52,
        "models": 854,
    },
    "legacy_compat_is_still_present": {
        "endpoints": 29,
        "models": 607,
    },
}


def test_root_exports_baseline_snapshot() -> None:
    assert ai.__all__ == ROOT_EXPORTS_BASELINE
    assert len(ai.__all__) == 46


def test_advanced_exports_are_not_root_stable_exports() -> None:
    for export in ADVANCED_ROOT_EXPORTS_REMOVED:
        assert export not in ai.__all__


def test_builtin_provider_and_catalog_count_baseline() -> None:
    registry = load_builtin_model_registry()
    providers = registry.list_providers()
    endpoints = registry.list_endpoints()
    models = registry.list_models()

    assert [provider.id for provider in providers] == CATALOG_PROVIDER_BASELINE
    assert len(providers) == 38
    assert len(endpoints) == 52
    assert len(models) == 854
    assert sum(1 for endpoint in endpoints if endpoint.compat) == 29
    assert sum(1 for model in models if model.compat) == 607


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

    assert len(ai_test_files) == 39
    assert len(provider_test_files) == 5
    assert len(example_files) == 26


def test_known_baseline_debt_snapshot() -> None:
    provider_registry = ApiProviderRegistry()
    register_builtin_ai_providers(provider_registry)
    model_registry = load_builtin_model_registry()
    providers = model_registry.list_providers()
    endpoints = model_registry.list_endpoints()
    models = model_registry.list_models()

    assert [
        provider.api
        for provider in provider_registry.list_api_providers()
        if provider.api
        not in {
            "anthropic-messages",
            "openai-completions",
            "openai-responses",
        }
    ] == KNOWN_BASELINE_DEBT["core_bootstrap_registers_non_target_adapters"]
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
