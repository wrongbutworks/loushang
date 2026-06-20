from __future__ import annotations

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
    module = _load_module(Path("examples/ai/model_lookup.py"), "examples_ai_model_lookup")

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
    assert examples[("azure-openai-responses", "azure-openai-responses", "gpt-4o-mini")]
    assert examples[
        (
            "amazon-bedrock",
            "bedrock-converse-stream",
            "anthropic.claude-sonnet-4-5-20250929-v1_0",
        )
    ]


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
                                "compat": {"thinkingFormat": "example"},
                                "protocol": {
                                    "roles": {"developer": "unsupported"},
                                    "reasoning": {"effort": "unsupported"},
                                },
                                "dialect": {
                                    "maxOutputTokensField": "max_completion_tokens",
                                    "reasoning": {"wireFormat": "moonshot"},
                                },
                                "models": {
                                    "kimi-k2.5": {
                                        "compat": {
                                            "supportsReasoningEffort": True,
                                            "supportsStreamReasoningDelta": True
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
        "roles": {"developer": "unsupported"},
        "reasoning": {"effort": "unsupported"},
    }
    assert contract["dialectScope"] == "endpoint-default"
    assert contract["dialect"] == {
        "maxOutputTokensField": "max_completion_tokens",
        "reasoning": {"wireFormat": "moonshot"},
    }
    assert contract["modelEffectiveLegacyCompat"]["supportsReasoningEffort"] is True
    assert "thinkingFormat" in contract["legacyCompatKeys"]
    assert "supportsStreamReasoningDelta" in contract[
        "modelEffectiveLegacyCompatKeys"
    ]

    module.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["protocolScope"] == "endpoint-default"
    assert payload["dialectScope"] == "endpoint-default"


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
        "roles": {"developer": "unsupported"},
        "reasoning": {"effort": "unsupported"},
    }
    assert contract["dialect"] == {
        "maxOutputTokensField": "max_completion_tokens",
        "reasoning": {"wireFormat": "moonshot"},
    }
    assert contract["modelEffectiveLegacyCompat"]["supportsReasoningEffort"] is True
    assert "supportsStreamReasoningDelta" in contract[
        "modelEffectiveLegacyCompatKeys"
    ]


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


def test_typed_context_example_uses_public_types() -> None:
    module = _load_module(Path("examples/ai/typed_context.py"), "examples_ai_typed_context")

    context = module._build_context()

    assert context.system_prompt is not None
    assert context.messages[0].role == "user"
    assert context.tools is not None
    assert context.tools[0].name == "add"


def test_usage_online_example_defaults_to_moonshot_public_route(monkeypatch) -> None:
    module = _load_module(Path("examples/ai/usage_online.py"), "examples_ai_usage_online")

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
