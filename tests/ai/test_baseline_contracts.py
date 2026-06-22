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
    "builtin_catalog_matches_curated_budget": {
        "providers": 11,
        "endpoints": 11,
        "models": 17,
    },
    "typed_contract_compat_bridge_is_present": {
        "endpoints": 11,
        "models": 17,
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
    assert len(providers) == 11
    assert len(endpoints) == 11
    assert len(models) == 17
    assert sum(1 for endpoint in endpoints if endpoint.compat) == 11
    assert sum(1 for model in models if model.compat) == 17


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

    assert len(ai_test_files) == 40
    assert len(provider_test_files) == 5
    assert len(example_files) == 27


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
    assert KNOWN_BASELINE_DEBT["builtin_catalog_matches_curated_budget"] == {
        "providers": len(providers),
        "endpoints": len(endpoints),
        "models": len(models),
    }
    assert KNOWN_BASELINE_DEBT["typed_contract_compat_bridge_is_present"] == {
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
