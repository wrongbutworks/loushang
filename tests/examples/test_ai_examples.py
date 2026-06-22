from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from loushang.ai.model import load_model_registry_from_file


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_model_lookup_example_targets_public_kimi_model() -> None:
    module = _load_module(
        Path("examples/ai/model_lookup.py"), "examples_ai_model_lookup"
    )

    assert module.PROVIDER_ID == "moonshot"
    assert module.ENDPOINT_ID == "openai-completions"
    assert module.MODEL_ID == "kimi-k2.5"


def test_provider_matrix_example_targets_new_provider_models() -> None:
    module = _load_module(
        Path("examples/ai/provider_matrix.py"), "examples_ai_provider_matrix"
    )

    examples = {
        (item.provider_id, item.endpoint_id, item.model_id): item.env_vars
        for item in module.PROVIDER_EXAMPLES
    }

    assert examples[("openrouter", "openai-completions", "openai/gpt-oss-120b_free")]
    assert "amazon-bedrock" not in {item.provider_id for item in module.PROVIDER_EXAMPLES}


def test_provider_matrix_example_formats_upstream_model_id() -> None:
    module = _load_module(
        Path("examples/ai/provider_matrix.py"), "examples_ai_provider_matrix_format"
    )

    line = module._format_model_line(module.PROVIDER_EXAMPLES[0])

    assert "openai/gpt-oss-120b_free" in line
    assert "upstream=openai/gpt-oss-120b:free" in line


def test_provider_matrix_example_formats_all_provider_entries() -> None:
    module = _load_module(
        Path("examples/ai/provider_matrix.py"), "examples_ai_provider_matrix_all"
    )

    lines = [module._format_model_line(example) for example in module.PROVIDER_EXAMPLES]

    assert len(lines) == len(module.PROVIDER_EXAMPLES)


def test_usage_online_example_marks_unknown_cost() -> None:
    module = _load_module(
        Path("examples/ai/usage_online.py"), "examples_ai_usage_online"
    )

    assert module._cost_payload(None) == {"known": False}
    assert module._cost_payload({"input": 0.1, "total": 0.1}) == {
        "known": True,
        "input": 0.1,
        "total": 0.1,
    }


def test_usage_online_example_prints_unknown_cost(capsys, monkeypatch) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage

    module = _load_module(
        Path("examples/ai/usage_online.py"), "examples_ai_usage_online_main"
    )

    class FakeModel:
        pricing = None

        async def complete(self, context, options):
            return AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="ok")],
                api="openai-completions",
                provider="moonshot",
                model="kimi-k2.5",
                response_id="resp_1",
                usage=Usage(
                    input=1,
                    output=1,
                    cache_read=0,
                    cache_write=0,
                    total_tokens=2,
                    cost=None,
                ),
                stop_reason="stop",
                error_message=None,
                timestamp=0.0,
            )

    monkeypatch.setattr(sys, "argv", ["usage_online.py", "--api-key", "test-key"])
    monkeypatch.setattr(module, "get_model", lambda *_args: FakeModel())

    assert asyncio.run(module.main()) == 0

    cost_line = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("cost: ")
    )
    assert json.loads(cost_line.removeprefix("cost: ")) == {"known": False}


def test_usage_example_reports_response_observation(capsys) -> None:
    module = _load_module(Path("examples/ai/10_usage.py"), "examples_ai_10_usage")

    summary = module.inspect_usage_observation()

    assert summary == {
        "present": True,
        "input": 120,
        "output": 30,
        "cacheRead": 10,
        "cacheWrite": 0,
        "totalTokens": 160,
        "cost": None,
    }

    module.main()
    assert json.loads(capsys.readouterr().out) == summary


def test_reasoning_example_reports_simple_reasoning_mapping(capsys) -> None:
    module = _load_module(
        Path("examples/ai/06_reasoning.py"), "examples_ai_06_reasoning"
    )

    summary = asyncio.run(module.inspect_reasoning())

    assert summary == {
        "reasoning": "medium",
        "budgetTokens": 2048,
        "events": [
            {"type": "thinking_delta", "thinking": "reasoning trace"},
            {"type": "text_delta", "text": "mock hello from faux provider"},
        ],
        "stopReason": "stop",
    }

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_parallel_tools_example_groups_interleaved_calls(capsys) -> None:
    module = _load_module(
        Path("examples/ai/05_parallel_tools.py"), "examples_ai_05_parallel_tools"
    )

    summary = asyncio.run(module.inspect_parallel_tools())

    assert summary == {
        "stopReason": "toolUse",
        "toolCalls": [
            {"id": "call_add", "name": "add", "arguments": {"a": 2}},
            {"id": "call_mul", "name": "multiply", "arguments": {"x": 3}},
        ],
    }

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_structured_output_example_parses_result(capsys) -> None:
    module = _load_module(
        Path("examples/ai/07_structured_output.py"),
        "examples_ai_07_structured_output",
    )

    summary = asyncio.run(module.inspect_structured_output())

    assert summary == {
        "responseId": "structured-demo",
        "stopReason": "stop",
        "parsed": {"answer": "Paris", "score": 10},
    }

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_image_input_example_reports_image_counts(capsys) -> None:
    module = _load_module(
        Path("examples/ai/08_image_input.py"),
        "examples_ai_08_image_input",
    )

    summary = asyncio.run(module.inspect_image_input())

    assert summary == {
        "userImages": 1,
        "toolResultImages": 1,
        "toolResultText": "chart shows growth",
    }

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_oauth_credential_store_example_reports_scopes(capsys) -> None:
    module = _load_module(
        Path("examples/ai/advanced/oauth_credential_store.py"),
        "examples_ai_advanced_oauth_credential_store",
    )

    summary = module.inspect_oauth_credential_store()

    assert summary["credentialScopes"] == {
        "providers": 0,
        "endpoints": 1,
        "models": 0,
    }
    assert summary["selectedCredential"] == "endpoint"

    module.main()
    assert json.loads(capsys.readouterr().out) == summary


def test_platform_quota_example_reports_endpoint_quota(capsys) -> None:
    module = _load_module(
        Path("examples/ai/advanced/platform_quota.py"),
        "examples_ai_advanced_platform_quota",
    )

    summary = asyncio.run(module.inspect_platform_quota())

    assert summary == {
        "present": True,
        "limit": 1000,
        "used": 320,
        "remaining": 680,
        "resetTime": "2026-06-29T00:00:00Z",
        "source": "moonshot:coding",
    }

    module.main()
    assert json.loads(capsys.readouterr().out) == summary


def test_openai_codex_contrib_example_registers_codex_model() -> None:
    from loushang.ai.advanced.registry import clear_api_providers
    from loushang.ai.auth import clear_oauth_providers
    from loushang.ai.model import clear_default_model_registry

    module = _load_module(
        Path("examples/ai/advanced/openai_codex_contrib.py"),
        "examples_ai_advanced_openai_codex_contrib",
    )

    try:
        model = module.load_codex_model()
    finally:
        clear_api_providers()
        clear_oauth_providers()
        clear_default_model_registry()

    assert model.provider_id == "openai-codex"
    assert model.endpoint_id == "openai-codex-responses"
    assert model.id == "gpt-5.3-codex"


def test_errors_retry_example_reports_redacted_error_payload(capsys) -> None:
    module = _load_module(
        Path("examples/ai/09_errors_retry.py"), "examples_ai_09_errors_retry"
    )

    payload = module.inspect_errors_retry()

    assert payload["error"]["code"] == "authentication"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {
        "hint": "Set MOONSHOT_API_KEY.",
        "Authorization": "[redacted]",
        "nested": {"refresh_token": "[redacted]"},
    }
    assert payload["typedError"] == {
        "errorType": "AIRateLimitError",
        "code": "rate_limit",
        "statusCode": 429,
        "requestId": "req_error_demo",
    }
    assert payload["retry"]["attempts"] == 2
    assert payload["retry"]["text"] == "retry recovered"
    assert payload["retry"]["trace"] == [
        {
            "schema": "loushang.ai.trace.v1",
            "type": "runtime:request",
            "source": "runtime",
            "name": "request",
            "data": {
                "api": "anthropic-messages",
                "provider": "retry-demo",
                "model": "retry-demo",
                "attempt": 1,
                "maxAttempts": 2,
                "endpoint": "anthropic-messages",
                "upstreamModel": "retry-demo",
            },
        },
        {
            "schema": "loushang.ai.trace.v1",
            "type": "runtime:retry",
            "source": "runtime",
            "name": "retry",
            "data": {
                "attempt": 2,
                "maxAttempts": 2,
                "delayMs": 0,
                "reason": "service_unavailable",
                "statusCode": 503,
            },
        },
        {
            "schema": "loushang.ai.trace.v1",
            "type": "runtime:request",
            "source": "runtime",
            "name": "request",
            "data": {
                "api": "anthropic-messages",
                "provider": "retry-demo",
                "model": "retry-demo",
                "attempt": 2,
                "maxAttempts": 2,
                "endpoint": "anthropic-messages",
                "upstreamModel": "retry-demo",
            },
        },
    ]

    module.main()
    assert json.loads(capsys.readouterr().out) == payload


def test_advanced_inspect_endpoint_contract_formats_protocol_facts(
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    module = _load_module(
        Path("examples/ai/advanced/inspect_endpoint_contract.py"),
        "examples_ai_advanced_inspect_endpoint_contract",
    )
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "moonshot": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://example.invalid/v1",
                                "compat": {
                                    "supportsStore": False,
                                    "supportsStrictMode": False,
                                    "thinkingFormat": "example",
                                },
                                "protocol": {
                                    "roles": {"developer": "unsupported"},
                                    "reasoning": {"effort": "unsupported"},
                                },
                                "dialect": {
                                    "maxOutputTokensField": "max_completion_tokens",
                                    "reasoning": {"wireFormat": "moonshot"},
                                },
                                "transport": {"kind": "httpx"},
                                "routing": {
                                    "requestOverrides": {
                                        "openrouter": {"only": ["anthropic"]}
                                    }
                                },
                                "models": {
                                    "kimi-k2.5": {
                                        "compat": {
                                            "supportsReasoningEffort": True,
                                            "supportsStreamReasoningDelta": True,
                                        },
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    monkeypatch.setattr(module, "load_builtin_model_registry", lambda: registry)

    contract = module.inspect_endpoint_contract()

    assert contract["provider"] == "moonshot"
    assert contract["endpoint"] == "openai-completions"
    assert contract["api"] == "openai-completions"
    assert contract["protocolScope"] == "endpoint-default"
    assert contract["model"] == "kimi-k2.5"
    assert contract["protocol"] == {
        "store": "unsupported",
        "roles": {"developer": "unsupported"},
        "reasoning": {"effort": "unsupported"},
        "tools": {"strictSchema": "unsupported"},
    }
    assert contract["dialectScope"] == "endpoint-default"
    assert contract["dialect"] == {
        "maxOutputTokensField": "max_completion_tokens",
        "reasoning": {"wireFormat": "moonshot"},
    }
    assert contract["transportScope"] == "endpoint-default"
    assert contract["transport"] == {"kind": "httpx"}
    assert contract["routingScope"] == "endpoint-default"
    assert contract["routing"] == {
        "requestOverrides": {"openrouter": {"only": ["anthropic"]}}
    }
    assert contract["requestProtocolScope"] == "model-effective"
    assert contract["requestProtocol"]["roles"]["developer"] == "unsupported"
    assert contract["requestProtocol"]["streaming"]["reasoningDelta"] == "supported"
    assert contract["requestProtocol"]["reasoning"]["effort"] == "supported"
    assert contract["requestDialectScope"] == "model-effective"
    assert contract["requestDialect"]["maxOutputTokensField"] == "max_completion_tokens"
    assert contract["requestDialect"]["reasoning"]["wireFormat"] == "moonshot"
    assert contract["adapterProtocolScope"] == "adapter-effective"
    assert contract["adapterProtocol"]["roles"]["developer"] == "unsupported"
    assert contract["adapterProtocol"]["reasoning"]["effort"] == "supported"
    assert contract["adapterDialectScope"] == "adapter-effective"
    assert contract["adapterDialect"]["maxOutputTokensField"] == "max_completion_tokens"
    assert contract["adapterDialect"]["reasoning"]["wireFormat"] == "moonshot"
    assert contract["requestTransportScope"] == "model-effective"
    assert contract["requestTransport"] == {"kind": "httpx"}
    assert contract["requestRoutingScope"] == "model-effective"
    assert contract["requestRouting"] == {
        "requestOverrides": {"openrouter": {"only": ["anthropic"]}}
    }
    assert "thinkingFormat" in contract["legacyCompatKeys"]

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["protocolScope"] == "endpoint-default"
    assert payload["dialectScope"] == "endpoint-default"
    assert payload["transportScope"] == "endpoint-default"
    assert payload["routingScope"] == "endpoint-default"
    assert payload["requestProtocolScope"] == "model-effective"
    assert payload["requestDialectScope"] == "model-effective"
    assert payload["adapterProtocolScope"] == "adapter-effective"
    assert payload["adapterDialectScope"] == "adapter-effective"


def test_advanced_inspect_endpoint_contract_runs_against_builtin_catalog() -> None:
    module = _load_module(
        Path("examples/ai/advanced/inspect_endpoint_contract.py"),
        "examples_ai_advanced_inspect_endpoint_contract_builtin",
    )

    contract = module.inspect_endpoint_contract()

    assert contract["provider"] == "moonshot"
    assert contract["endpoint"] == "openai-completions"
    assert contract["model"] == "kimi-k2.5"
    assert contract["protocol"] == {
        "store": "unsupported",
        "roles": {"developer": "unsupported"},
        "reasoning": {"effort": "unsupported"},
        "tools": {"strictSchema": "unsupported"},
    }
    assert contract["dialect"] == {
        "maxOutputTokensField": "max_tokens",
        "reasoning": {"wireFormat": "moonshot"},
    }
    assert contract["transport"] == {}
    assert contract["routing"] == {}
    assert contract["requestProtocol"]["reasoning"]["effort"] == "supported"
    assert contract["adapterProtocol"]["reasoning"]["effort"] == "supported"


def test_advanced_inspect_endpoint_contract_handles_templated_base_url() -> None:
    module = _load_module(
        Path("examples/ai/advanced/inspect_endpoint_contract.py"),
        "examples_ai_advanced_inspect_endpoint_contract_template",
    )

    contract = module.inspect_endpoint_contract(
        "cloudflare-workers-ai",
        "openai-completions",
        "@cf/google/gemma-4-26b-a4b-it",
    )

    assert contract["provider"] == "cloudflare-workers-ai"
    assert contract["endpoint"] == "openai-completions"
    assert contract["model"] == "@cf/google/gemma-4-26b-a4b-it"
    assert contract["requestProtocolScope"] == "model-effective"
    assert contract["requestDialectScope"] == "model-effective"
    assert contract["adapterProtocolScope"] == "adapter-effective"
    assert contract["adapterDialectScope"] == "adapter-effective"


def test_advanced_custom_catalog_uses_typed_upstream_binding() -> None:
    module = _load_module(
        Path("examples/ai/advanced/custom_catalog.py"),
        "examples_ai_advanced_custom_catalog",
    )

    summary = module.inspect_custom_catalog()

    assert summary == {
        "model": "custom-provider:openai-completions:public-model",
        "upstreamId": "vendor/public-model:latest",
        "resolvedUpstreamModelId": "vendor/public-model:latest",
        "baseUrl": "https://api.example.invalid/v1",
    }


def test_advanced_normalization_diagnostics_reports_stable_payload(capsys) -> None:
    module = _load_module(
        Path("examples/ai/advanced/normalization_diagnostics.py"),
        "examples_ai_advanced_normalization_diagnostics",
    )

    summary = module.inspect_normalization_diagnostics()

    assert summary["messageRoles"] == ["assistant", "toolResult"]
    assert summary["normalizedMessages"] == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "private reasoning"},
                {"type": "text", "text": "answer"},
                {
                    "type": "toolCall",
                    "id": "call_1",
                    "name": "calc",
                    "arguments": {"x": 1},
                    "thoughtSignature": None,
                },
            ],
        },
        {
            "role": "toolResult",
            "toolCallId": "call_1",
            "toolName": "calc",
            "isError": True,
            "details": {"synthetic": True, "reason": "missing_tool_result"},
            "content": [{"type": "text", "text": "No result provided"}],
        },
    ]
    assert summary["diagnostics"] == [
        {
            "code": "thinking_signature_removed",
            "path": "messages[0].content[0]",
            "level": "warning",
        },
        {
            "code": "thinking_downgraded_to_text",
            "path": "messages[0].content[0]",
            "level": "warning",
        },
        {
            "code": "text_signature_removed",
            "path": "messages[0].content[1]",
            "level": "warning",
        },
        {
            "code": "tool_call_id_normalized",
            "path": "messages[0].content[2]",
            "level": "warning",
        },
        {
            "code": "tool_call_thought_signature_removed",
            "path": "messages[0].content[2]",
            "level": "warning",
        },
        {
            "code": "missing_tool_result_repaired",
            "path": "messages[0].content[2]",
            "level": "warning",
        },
    ]

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_advanced_capability_failure_reports_public_error(capsys) -> None:
    module = _load_module(
        Path("examples/ai/advanced/capability_failure.py"),
        "examples_ai_advanced_capability_failure",
    )

    summary = asyncio.run(module.inspect_capability_failure())

    assert summary == {
        "errorType": "ValueError",
        "message": "Model 'capability-demo' does not support tool use",
    }

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_advanced_cancel_stream_reports_abort_and_source_close() -> None:
    module = _load_module(
        Path("examples/ai/advanced/cancel_stream.py"),
        "examples_ai_advanced_cancel_stream",
    )

    summary = asyncio.run(module.inspect_stream_cancellation())

    assert summary == {
        "events": ["start", "error"],
        "reason": "aborted",
        "stopReason": "aborted",
        "sourceClosed": True,
    }


def test_advanced_trace_events_reports_schema_and_redaction(capsys) -> None:
    module = _load_module(
        Path("examples/ai/advanced/trace_events.py"),
        "examples_ai_advanced_trace_events",
    )

    summary = asyncio.run(module.inspect_trace_events())

    assert summary == {
        "schemas": ["loushang.ai.trace.v1"],
        "eventTypes": [
            "runtime:request",
            "sdk:client",
            "runtime:retry",
            "runtime:request",
            "sdk:client",
        ],
        "text": "trace recovered",
        "redaction": {
            "authorization": "<redacted>",
            "apiKey": "<redacted>",
            "refreshToken": "<redacted>",
        },
        "retry": {
            "attempt": 2,
            "maxAttempts": 2,
            "delayMs": 0,
            "reason": "service_unavailable",
            "statusCode": 503,
        },
    }
    assert "secret" not in json.dumps(summary, sort_keys=True)

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == summary


def test_advanced_inspect_endpoint_contract_rejects_missing_model(
    monkeypatch,
    tmp_path,
) -> None:
    module = _load_module(
        Path("examples/ai/advanced/inspect_endpoint_contract.py"),
        "examples_ai_advanced_inspect_endpoint_contract_missing_model",
    )
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "moonshot": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "models": {},
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    monkeypatch.setattr(module, "load_builtin_model_registry", lambda: registry)

    try:
        module.inspect_endpoint_contract(model_id="missing")
    except KeyError as error:
        assert error.args == (("moonshot", "openai-completions", "missing"),)
    else:
        raise AssertionError("missing model should raise KeyError")


def test_complete_example_builds_expected_context() -> None:
    module = _load_module(Path("examples/ai/complete.py"), "examples_ai_complete")

    context = module._build_context()

    assert context["system_prompt"]
    assert context["messages"][0]["role"] == "user"


def test_tools_example_declares_add_tool() -> None:
    module = _load_module(Path("examples/ai/tools.py"), "examples_ai_tools")

    tools = module._build_tools()

    assert tools[0]["name"] == "add"
    assert tools[0]["parameters"]["required"] == ["a", "b"]
    assert module._inspect_tool_validation() == {
        "strict": {"a": 2, "b": 3},
        "strictError": 'Validation failed for tool "add":',
        "coerce": {"a": 2.0, "b": 3.0},
        "diagnostics": [
            {
                "code": "tool_argument_coerced",
                "path": "$.a",
                "fromType": "string",
                "toType": "number",
            },
            {
                "code": "tool_argument_coerced",
                "path": "$.b",
                "fromType": "string",
                "toType": "number",
            },
        ],
    }


def test_typed_context_example_uses_public_types() -> None:
    module = _load_module(
        Path("examples/ai/03_typed_context.py"), "examples_ai_03_typed_context"
    )

    context = module._build_context()

    assert context.system_prompt is not None
    assert context.messages[0].role == "user"
    assert context.tools is not None
    assert context.tools[0].name == "add"


def test_usage_online_example_defaults_to_moonshot_public_route(monkeypatch) -> None:
    module = _load_module(
        Path("examples/ai/usage_online.py"), "examples_ai_usage_online"
    )

    monkeypatch.setattr(sys, "argv", ["usage_online.py"])

    assert module.parse_args().route == "moonshot-openai"


def test_usage_online_kimi_code_routes_require_kimi_credentials() -> None:
    module = _load_module(
        Path("examples/ai/usage_online.py"), "examples_ai_usage_online_routes"
    )

    assert module.ROUTES["kimi-code-anthropic"].api_key_envs == (
        "KIMI_API_KEY",
        "KIMI_AUTH_TOKEN",
    )
    assert module.ROUTES["kimi-code-openai"].api_key_envs == (
        "KIMI_API_KEY",
        "KIMI_AUTH_TOKEN",
    )


def test_usage_online_routes_exist_in_model_catalog() -> None:
    module = _load_module(
        Path("examples/ai/usage_online.py"), "examples_ai_usage_online_catalog"
    )

    for route in module.ROUTES.values():
        module.get_model(route.provider, route.endpoint, route.model)
