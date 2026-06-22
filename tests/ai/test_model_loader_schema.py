from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from loushang.ai.model import (
    LEGACY_COMPAT_TRANSLATION_TARGETS,
    EndpointWireDialect,
    SupportStatus,
    load_builtin_model_registry_with_diagnostics,
    load_layered_model_registry_with_diagnostics,
    load_model_registry_from_directory_with_diagnostics,
    load_model_registry_from_file_with_diagnostics,
)
from loushang.ai.model.loader import (
    load_layered_model_registry,
    load_model_registry,
    load_model_registry_from_directory,
    load_model_registry_from_file,
    validate_model_registry_raw,
)

EXPECTED_LEGACY_COMPAT_TRANSLATION_TARGETS = {
    "supportsStore": "protocol.store",
    "supportsDeveloperRole": "protocol.roles.developer",
    "supportsReasoningEffort": "protocol.reasoning.effort",
    "reasoningEffortMap": "protocol.reasoning.effortMap",
    "supportsUsageInStreaming": "protocol.streaming.usage",
    "supportsStreamReasoningDelta": "protocol.streaming.reasoningDelta",
    "maxTokensField": "dialect.maxOutputTokensField",
    "requiresToolResultName": "dialect.tools.resultNameRequired",
    "requiresAssistantAfterToolResult": "dialect.tools.assistantBridgeRequired",
    "requiresThinkingAsText": "dialect.reasoning.thinkingAsText",
    "thinkingFormat": "dialect.reasoning.wireFormat",
    "supportsStrictMode": "protocol.tools.strictSchema",
    "requiresReasoningContentOnAssistantMessages": (
        "dialect.reasoning.assistantContentRequired"
    ),
    "openRouterRouting": "routing.requestOverrides.openrouter",
    "vercelGatewayRouting": "routing.requestOverrides.vercelGateway",
    "zaiToolStream": "dialect.tools.streamFlag",
    "cacheControlFormat": "dialect.cache.controlFormat",
    "sendSessionAffinityHeaders": "protocol.session.affinityHeaders",
    "sendSessionIdHeader": "protocol.session.idHeader",
    "supportsLongCacheRetention": "protocol.cache.longRetention",
    "supportsEagerToolInputStreaming": "protocol.tools.eagerInputStream",
    "supportsCacheControlOnTools": "protocol.cache.onTools",
    "fineGrainedTools": "protocol.tools.fineGrained",
    "interleavedThinking": "protocol.reasoning.interleaved",
    "supportsPromptCacheKey": "protocol.cache.promptKey",
    "providerTransport": "transport.kind",
    "supportsJsonSchemaStructuredOutput": "capabilities.structuredOutput",
    "upstreamModelId": "model.upstreamId",
}


def _minimal_registry_raw(*, schema_version: int | None = 1) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    if schema_version is not None:
        raw["schemaVersion"] = schema_version
    return raw


def _diagnostics_by_key(result) -> dict[str, object]:
    return {diagnostic.legacy_key: diagnostic for diagnostic in result.diagnostics}


def test_legacy_compat_translation_target_table_covers_plan_keys() -> None:
    assert LEGACY_COMPAT_TRANSLATION_TARGETS == (
        EXPECTED_LEGACY_COMPAT_TRANSLATION_TARGETS
    )


def test_builtin_model_registry_matches_schema() -> None:
    registry = load_model_registry()

    assert registry.get_model("moonshot", "openai-completions", "kimi-k2.6")


def test_model_registry_schema_accepts_implicit_v1_catalog() -> None:
    raw = _minimal_registry_raw(schema_version=None)

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_explicit_v1_catalog() -> None:
    raw = _minimal_registry_raw(schema_version=1)

    validate_model_registry_raw(raw)


def test_model_registry_schema_loads_v2_catalog_file(tmp_path) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"],
                        "stream": true
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_model_registry_from_file(path)

    model = registry.get_model("custom", "openai-completions", "model-a")
    assert model.supports_stream is True


def test_model_registry_schema_loads_v2_catalog_directory(tmp_path) -> None:
    path = tmp_path / "catalog"
    path.mkdir()
    (path / "models.v2.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_model_registry_from_directory(path)

    assert registry.get_model("custom", "openai-completions", "model-a")


def test_model_registry_schema_rejects_unknown_version() -> None:
    raw = _minimal_registry_raw(schema_version=3)

    with pytest.raises(ValueError, match="unsupported models registry schemaVersion"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_endpoint_protocol_features() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {
        "roles": {"developer": "supported"},
        "streaming": {
            "usage": "supported",
            "reasoningDelta": "unsupported",
        },
        "reasoning": {
            "effort": "unknown",
            "effortMap": {"off": None, "minimal": "low"},
        },
        "tools": {"strictSchema": "supported"},
        "cache": {"longRetention": "supported"},
        "session": {"idHeader": "supported"},
        "store": "unsupported",
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_protocol_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"roles": {"developer": "supported"}}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_model_protocol_features() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["protocol"] = {"reasoning": {"effort": "supported"}}

    with pytest.raises(ValueError, match="only supported on endpoints"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_endpoint_wire_dialect() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {
        "maxOutputTokensField": "max_completion_tokens",
        "tools": {
            "resultNameRequired": True,
            "assistantBridgeRequired": False,
            "streamFlag": True,
        },
        "reasoning": {
            "wireFormat": "moonshot",
            "thinkingAsText": True,
            "assistantContentRequired": False,
        },
        "cache": {"controlFormat": "anthropic"},
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_dialect_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {"reasoning": {"wireFormat": "moonshot"}}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_model_wire_dialect() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["dialect"] = {"reasoning": {"wireFormat": "moonshot"}}

    with pytest.raises(ValueError, match="only supported on endpoints"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_endpoint_transport_and_routing() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {
        "kind": "httpx",
        "stream": "sse",
        "fallback": True,
        "timeout": 30,
    }
    endpoint["routing"] = {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_transport_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {"kind": "httpx"}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_routing_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["routing"] = {"requestOverrides": {"openrouter": {"only": ["anthropic"]}}}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("field", ["transport", "routing"])
def test_model_registry_schema_rejects_model_transport_routing_before_v2(
    field: str,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model[field] = {}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_model_transport_routing() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["transport"] = {"timeout": 30}
    model["routing"] = {"requestOverrides": {"openrouter": {"only": ["anthropic"]}}}

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_model_upstream_id() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["upstreamId"] = "vendor/model-a:latest"

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_model_upstream_id_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["upstreamId"] = "vendor/model-a:latest"

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_legacy_upstream_id() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {"upstreamModelId": "vendor/model-a:latest"}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_model_upstream_id() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["upstreamId"] = ""

    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_model_registry_raw(raw)

    model["upstreamId"] = " "

    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_model_registry_raw(raw)


def test_model_registry_loads_legacy_reasoning_effort_map_into_protocol(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "supportsReasoningEffort": True,
        "reasoningEffortMap": {"off": None, "minimal": "low"},
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.to_raw()["reasoning"] == {
        "effort": "supported",
        "effortMap": {"off": None, "minimal": "low"},
    }
    endpoint_raw = endpoint_contract.to_raw()
    assert "protocol" not in endpoint_raw

    validate_model_registry_raw(
        {
            "schemaVersion": 1,
            "providers": {
                "custom": {
                    "endpoints": {
                        "openai-completions": endpoint_raw,
                    }
                }
            },
        }
    )


def test_model_registry_reports_legacy_compat_translation_diagnostics(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "supportsStore": True,
        "supportsReasoningEffort": True,
        "reasoningEffortMap": {"minimal": "low"},
        "maxTokensField": "max_completion_tokens",
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
    }
    model = endpoint["models"]["model-a"]
    model["compat"] = {
        "supportsJsonSchemaStructuredOutput": True,
        "upstreamModelId": "vendor/model-a:latest",
        "codexUserAgent": "loushang-test",
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_file_with_diagnostics(path)
    diagnostics = _diagnostics_by_key(result)
    registry = result.registry
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.store is SupportStatus.SUPPORTED
    assert endpoint_contract.protocol.reasoning.effort is SupportStatus.SUPPORTED
    assert endpoint_contract.protocol.reasoning.effort_map == {"minimal": "low"}
    assert endpoint_contract.dialect.max_output_tokens_field == (
        "max_completion_tokens"
    )
    assert endpoint_contract.transport.to_raw() == {"kind": "httpx"}
    assert endpoint_contract.routing.to_raw() == {
        "requestOverrides": {"openrouter": {"only": ["anthropic"]}}
    }
    assert model_contract.supports_structured_output is True
    assert model_contract.upstream_id == "vendor/model-a:latest"
    assert model_contract.compat["supportsJsonSchemaStructuredOutput"] is True
    assert model_contract.compat["codexUserAgent"] == "loushang-test"

    expected_keys = {
        "supportsStore",
        "supportsReasoningEffort",
        "reasoningEffortMap",
        "maxTokensField",
        "providerTransport",
        "openRouterRouting",
        "supportsJsonSchemaStructuredOutput",
        "upstreamModelId",
    }
    assert set(diagnostics) == expected_keys
    assert "codexUserAgent" not in diagnostics
    for legacy_key in expected_keys:
        diagnostic = diagnostics[legacy_key]
        assert diagnostic.code == "legacy_compat_deprecated"
        assert diagnostic.level == "warning"
        assert diagnostic.target == LEGACY_COMPAT_TRANSLATION_TARGETS[legacy_key]
        assert diagnostic.path.endswith(f".compat.{legacy_key}")
        assert legacy_key in diagnostic.message


def test_endpoint_legacy_structured_output_compat_applies_to_models(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {"supportsJsonSchemaStructuredOutput": True}
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_file_with_diagnostics(path)
    model_contract = result.registry.get_model(
        "custom",
        "openai-completions",
        "model-a",
    )

    assert model_contract.supports_structured_output is True
    assert model_contract.compat["supportsJsonSchemaStructuredOutput"] is True
    assert [diagnostic.legacy_key for diagnostic in result.diagnostics] == [
        "supportsJsonSchemaStructuredOutput"
    ]


def test_legacy_structured_output_compat_does_not_override_typed_capability(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["capabilities"]["structuredOutput"] = False
    model["compat"] = {"supportsJsonSchemaStructuredOutput": True}
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_file_with_diagnostics(path)
    model_contract = result.registry.get_model(
        "custom",
        "openai-completions",
        "model-a",
    )

    assert model_contract.supports_structured_output is False
    assert model_contract.compat["supportsJsonSchemaStructuredOutput"] is False
    assert [diagnostic.legacy_key for diagnostic in result.diagnostics] == [
        "supportsJsonSchemaStructuredOutput"
    ]


def test_builtin_model_registry_with_diagnostics_suppresses_builtin_warnings() -> None:
    result = load_builtin_model_registry_with_diagnostics()

    assert result.registry.get_model("moonshot", "openai-completions", "kimi-k2.6")
    assert result.diagnostics == ()


def test_legacy_compat_diagnostics_preserve_per_path_entries(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {"supportsJsonSchemaStructuredOutput": True}
    endpoint["models"]["model-a"]["compat"] = {
        "supportsJsonSchemaStructuredOutput": False
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_file_with_diagnostics(path)

    assert [diagnostic.path for diagnostic in result.diagnostics] == [
        "providers.custom.endpoints.openai-completions.compat.supportsJsonSchemaStructuredOutput",
        "providers.custom.endpoints.openai-completions.models.model-a.compat.supportsJsonSchemaStructuredOutput",
    ]


def test_model_level_endpoint_only_compat_does_not_emit_invalid_target(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["compat"] = {"supportsStore": False}
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_file_with_diagnostics(path)
    model_contract = result.registry.get_model(
        "custom",
        "openai-completions",
        "model-a",
    )

    assert model_contract.compat["supportsStore"] is False
    assert result.diagnostics == ()


def test_directory_diagnostics_follow_last_provider_wins(
    tmp_path,
) -> None:
    first = _minimal_registry_raw(schema_version=1)
    first["providers"]["custom"]["endpoints"]["openai-completions"]["compat"] = {
        "supportsStore": True
    }
    second = _minimal_registry_raw(schema_version=1)
    (tmp_path / "a.json").write_text(json.dumps(first), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(second), encoding="utf-8")

    result = load_model_registry_from_directory_with_diagnostics(tmp_path)
    endpoint_contract = result.registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.store is SupportStatus.UNKNOWN
    assert result.diagnostics == ()


def test_directory_diagnostics_do_not_match_dotted_provider_prefix(
    tmp_path,
) -> None:
    raw = {
        "schemaVersion": 1,
        "providers": {
            "foo": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            },
            "foo.bar": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "compat": {"supportsStore": True},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            },
        },
    }
    (tmp_path / "models.json").write_text(json.dumps(raw), encoding="utf-8")

    result = load_model_registry_from_directory_with_diagnostics(tmp_path)

    assert [diagnostic.path for diagnostic in result.diagnostics] == [
        "providers.foo.bar.endpoints.openai-completions.compat.supportsStore"
    ]


def test_layered_model_registry_with_diagnostics_reports_external_overlay(
    tmp_path,
) -> None:
    project_dir = tmp_path / "models"
    project_dir.mkdir()
    raw = _minimal_registry_raw(schema_version=1)
    raw["providers"]["custom"]["endpoints"]["openai-completions"]["compat"] = {
        "supportsStore": True
    }
    (project_dir / "models.json").write_text(json.dumps(raw), encoding="utf-8")

    result = load_layered_model_registry_with_diagnostics(project_dir=project_dir)

    assert result.registry.get_model("custom", "openai-completions", "model-a")
    assert result.registry.get_model("moonshot", "openai-completions", "kimi-k2.6")
    assert [diagnostic.path for diagnostic in result.diagnostics] == [
        "providers.custom.endpoints.openai-completions.compat.supportsStore"
    ]


def test_layered_model_registry_with_diagnostics_preserves_merged_overlay_warning(
    tmp_path,
) -> None:
    user_dir = tmp_path / "user-models"
    project_dir = tmp_path / "project-models"
    user_dir.mkdir()
    project_dir.mkdir()
    user_raw = _minimal_registry_raw(schema_version=1)
    user_raw["providers"]["custom"]["endpoints"]["openai-completions"]["compat"] = {
        "supportsStore": True
    }
    project_raw = _minimal_registry_raw(schema_version=1)
    project_raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]["displayName"] = "Project override"
    (user_dir / "models.json").write_text(json.dumps(user_raw), encoding="utf-8")
    (project_dir / "models.json").write_text(json.dumps(project_raw), encoding="utf-8")

    result = load_layered_model_registry_with_diagnostics(
        user_dir=user_dir,
        project_dir=project_dir,
    )
    endpoint_contract = result.registry.get_endpoint("custom", "openai-completions")
    model_contract = result.registry.get_model(
        "custom",
        "openai-completions",
        "model-a",
    )

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.store is SupportStatus.SUPPORTED
    assert model_contract.name == "Project override"
    assert [diagnostic.path for diagnostic in result.diagnostics] == [
        "providers.custom.endpoints.openai-completions.compat.supportsStore"
    ]


def test_model_registry_loads_legacy_wire_dialect_from_compat(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "maxTokensField": "max_completion_tokens",
        "requiresToolResultName": True,
        "requiresAssistantAfterToolResult": True,
        "requiresThinkingAsText": True,
        "requiresReasoningContentOnAssistantMessages": True,
        "thinkingFormat": "moonshot",
        "zaiToolStream": True,
        "cacheControlFormat": "anthropic",
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.dialect.to_raw() == {
        "maxOutputTokensField": "max_completion_tokens",
        "tools": {
            "resultNameRequired": True,
            "assistantBridgeRequired": True,
            "streamFlag": True,
        },
        "reasoning": {
            "wireFormat": "moonshot",
            "thinkingAsText": True,
            "assistantContentRequired": True,
        },
        "cache": {"controlFormat": "anthropic"},
    }
    endpoint_raw = endpoint_contract.to_raw()
    assert "dialect" not in endpoint_raw


def test_model_registry_loads_legacy_transport_routing_from_compat(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
        "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.transport.to_raw() == {"kind": "httpx"}
    assert endpoint_contract.routing.to_raw() == {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }
    assert "providerTransport" not in endpoint_contract.compat
    assert "openRouterRouting" not in endpoint_contract.compat
    assert "vercelGatewayRouting" not in endpoint_contract.compat
    endpoint_raw = endpoint_contract.to_raw()
    assert "transport" not in endpoint_raw
    assert "routing" not in endpoint_raw
    assert endpoint_raw["compat"] == {
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
        "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
    }
    roundtrip_path = tmp_path / "roundtrip.v1.json"
    roundtrip_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": endpoint_raw,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    roundtrip_registry = load_model_registry_from_file(roundtrip_path)
    roundtrip_endpoint = roundtrip_registry.get_endpoint(
        "custom",
        "openai-completions",
    )
    assert roundtrip_endpoint is not None
    assert roundtrip_endpoint.transport.to_raw() == {"kind": "httpx"}
    assert roundtrip_endpoint.routing.to_raw() == {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }


def test_model_registry_round_trips_mixed_legacy_and_typed_transport_routing(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
    }
    endpoint["transport"] = {"timeout": 45}
    endpoint["routing"] = {"requestOverrides": {"openrouter": {"order": ["openai"]}}}
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    endpoint_raw = endpoint_contract.to_raw()
    assert endpoint_raw["transport"] == {"kind": "httpx", "timeout": 45}
    assert endpoint_raw["routing"] == {
        "requestOverrides": {"openrouter": {"only": ["anthropic"], "order": ["openai"]}}
    }


def test_model_registry_loads_model_legacy_transport_routing_from_compat(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["compat"] = {
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
        "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.transport.to_raw() == {"kind": "httpx"}
    assert model_contract.routing.to_raw() == {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }
    assert "providerTransport" not in model_contract.compat
    assert "openRouterRouting" not in model_contract.compat
    assert "vercelGatewayRouting" not in model_contract.compat
    model_raw = model_contract.to_raw()
    assert "transport" not in model_raw
    assert "routing" not in model_raw
    assert model_raw["compat"] == {
        "providerTransport": "httpx",
        "openRouterRouting": {"only": ["anthropic"]},
        "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
    }


def test_model_registry_loads_model_legacy_upstream_id_from_compat(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["compat"] = {"upstreamModelId": "vendor/model-a:latest"}
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.upstream_id == "vendor/model-a:latest"
    assert "upstreamModelId" not in model_contract.compat
    model_raw = model_contract.to_raw()
    assert "upstreamId" not in model_raw
    assert model_raw["compat"] == {
        "upstreamModelId": "vendor/model-a:latest",
    }


def test_model_registry_loads_unknown_pricing_as_absent(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.pricing is None
    assert "pricing" not in model_contract.to_raw()


def test_model_registry_loads_partial_pricing_without_default_zero(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["pricing"] = {"input": 0, "output": 2.0, "cacheRead": None}
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.pricing is not None
    assert model_contract.pricing.input == 0
    assert model_contract.pricing.output == 2.0
    assert model_contract.pricing.cache_read is None
    assert model_contract.pricing.cache_write is None
    assert model_contract.to_raw()["pricing"] == {"input": 0, "output": 2.0}


def test_model_registry_schema_rejects_invalid_pricing_value() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["pricing"] = {"input": "free"}

    with pytest.raises(ValueError, match="non-negative number or null"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), float("-inf")])
def test_model_registry_schema_rejects_non_numeric_pricing_values(
    value: object,
) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["pricing"] = {"input": value}

    with pytest.raises(ValueError, match="non-negative number or null"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_legacy_unknown_pricing_sentinel() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["pricing"] = {"input": -1000000}

    with pytest.raises(ValueError, match="non-negative number or null"):
        validate_model_registry_raw(raw)


def test_model_registry_loads_model_typed_transport_routing(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["transport"] = {"stream": "sse", "timeout": 30}
    model["routing"] = {"requestOverrides": {"openrouter": {"order": ["openai"]}}}
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.transport.to_raw() == {"stream": "sse", "timeout": 30}
    assert model_contract.routing.to_raw() == {
        "requestOverrides": {"openrouter": {"order": ["openai"]}}
    }
    model_raw = model_contract.to_raw()
    assert model_raw["transport"] == {"stream": "sse", "timeout": 30}
    assert model_raw["routing"] == {
        "requestOverrides": {"openrouter": {"order": ["openai"]}}
    }


def test_model_registry_loads_model_typed_upstream_id(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["compat"] = {"upstreamModelId": "legacy/model-a"}
    model["upstreamId"] = "vendor/model-a:latest"
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    model_contract = registry.get_model("custom", "openai-completions", "model-a")

    assert model_contract.upstream_id == "vendor/model-a:latest"
    assert "upstreamModelId" not in model_contract.compat
    model_raw = model_contract.to_raw()
    assert model_raw["upstreamId"] == "vendor/model-a:latest"
    assert "upstreamModelId" not in model_raw["compat"]


def test_model_registry_loads_explicit_protocol_into_compat_bridge(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {"supportsDeveloperRole": True}
    endpoint["protocol"] = {
        "roles": {"developer": "unsupported"},
        "streaming": {"reasoningDelta": "supported"},
        "tools": {"strictSchema": "unsupported"},
        "reasoning": {
            "effort": "supported",
            "effortMap": {"off": None, "minimal": "low"},
        },
        "cache": {"promptKey": "supported"},
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.to_raw() == {
        "roles": {"developer": "unsupported"},
        "streaming": {"reasoningDelta": "supported"},
        "reasoning": {
            "effort": "supported",
            "effortMap": {"off": None, "minimal": "low"},
        },
        "tools": {"strictSchema": "unsupported"},
        "cache": {"promptKey": "supported"},
    }
    assert endpoint_contract.compat["supportsDeveloperRole"] is False
    assert endpoint_contract.compat["supportsStreamReasoningDelta"] is True
    assert endpoint_contract.compat["supportsReasoningEffort"] is True
    assert endpoint_contract.compat["supportsStrictMode"] is False
    assert endpoint_contract.compat["supportsPromptCacheKey"] is True
    assert endpoint_contract.compat["reasoningEffortMap"] == {
        "off": None,
        "minimal": "low",
    }


def test_model_registry_loads_explicit_dialect_into_compat_bridge(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "maxTokensField": "max_tokens",
        "thinkingFormat": "openai",
    }
    endpoint["dialect"] = {
        "maxOutputTokensField": "max_completion_tokens",
        "tools": {
            "resultNameRequired": True,
            "assistantBridgeRequired": True,
            "streamFlag": False,
        },
        "reasoning": {
            "wireFormat": "moonshot",
            "thinkingAsText": True,
            "assistantContentRequired": True,
        },
        "cache": {"controlFormat": "anthropic"},
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.dialect.to_raw() == endpoint["dialect"]
    assert endpoint_contract.compat["maxTokensField"] == "max_completion_tokens"
    assert endpoint_contract.compat["requiresToolResultName"] is True
    assert endpoint_contract.compat["requiresAssistantAfterToolResult"] is True
    assert endpoint_contract.compat["requiresThinkingAsText"] is True
    assert (
        endpoint_contract.compat["requiresReasoningContentOnAssistantMessages"] is True
    )
    assert endpoint_contract.compat["thinkingFormat"] == "moonshot"
    assert endpoint_contract.compat["zaiToolStream"] is False
    assert endpoint_contract.compat["cacheControlFormat"] == "anthropic"


def test_model_registry_loads_explicit_transport_routing(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {"kind": "httpx", "stream": "sse", "timeout": 45}
    endpoint["routing"] = {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.transport.to_raw() == endpoint["transport"]
    assert endpoint_contract.routing.to_raw() == endpoint["routing"]
    endpoint_raw = endpoint_contract.to_raw()
    assert endpoint_raw["transport"] == endpoint["transport"]
    assert endpoint_raw["routing"] == endpoint["routing"]
    model_compat = endpoint_raw["models"]["model-a"]["compat"]
    assert "providerTransport" not in model_compat
    assert "openRouterRouting" not in model_compat
    assert "vercelGatewayRouting" not in model_compat


def test_model_registry_preserves_explicit_dialect_on_to_raw(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {
        "tools": {"resultNameRequired": True},
        "reasoning": {"wireFormat": "moonshot"},
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    effective_dialect = {
        "tools": {"resultNameRequired": True},
        "reasoning": {"wireFormat": "moonshot"},
    }
    assert endpoint_contract.dialect.to_raw() == effective_dialect
    endpoint_raw = endpoint_contract.to_raw()
    assert endpoint_raw["dialect"] == endpoint["dialect"]

    roundtrip_path = tmp_path / "roundtrip.v2.json"
    roundtrip_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": endpoint_raw,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    roundtrip_registry = load_model_registry_from_file(roundtrip_path)
    roundtrip_endpoint = roundtrip_registry.get_endpoint(
        "custom",
        "openai-completions",
    )

    assert roundtrip_endpoint is not None
    assert roundtrip_endpoint.dialect.to_raw() == effective_dialect
    assert roundtrip_endpoint.compat["requiresToolResultName"] is True
    assert roundtrip_endpoint.compat["thinkingFormat"] == "moonshot"


def test_model_registry_to_raw_uses_replaced_dialect(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {"reasoning": {"wireFormat": "moonshot"}}
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    updated_endpoint = replace(
        endpoint_contract,
        dialect=EndpointWireDialect.from_raw({"maxOutputTokensField": "max_tokens"}),
    )

    assert updated_endpoint.to_raw()["dialect"] == {
        "maxOutputTokensField": "max_tokens"
    }


def test_model_registry_preserves_explicit_unknown_protocol_on_to_raw(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {
        "store": "unknown",
        "roles": {"developer": "unknown"},
        "tools": {"strictSchema": "unknown"},
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    endpoint_raw = endpoint_contract.to_raw()
    assert endpoint_raw["protocol"] == {
        "store": "unknown",
        "roles": {"developer": "unknown"},
        "tools": {"strictSchema": "unknown"},
    }
    assert endpoint_raw["compat"]["supportsStore"] is False
    assert endpoint_raw["compat"]["supportsDeveloperRole"] is False
    assert endpoint_raw["compat"]["supportsStrictMode"] is False

    roundtrip_path = tmp_path / "roundtrip.v2.json"
    roundtrip_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": endpoint_raw,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    roundtrip_registry = load_model_registry_from_file(roundtrip_path)
    roundtrip_endpoint = roundtrip_registry.get_endpoint(
        "custom",
        "openai-completions",
    )

    assert roundtrip_endpoint is not None
    assert roundtrip_endpoint.protocol.store is SupportStatus.UNKNOWN
    assert roundtrip_endpoint.protocol.roles.developer is SupportStatus.UNKNOWN
    assert roundtrip_endpoint.protocol.tools.strict_schema is SupportStatus.UNKNOWN


def test_model_registry_schema_rejects_invalid_protocol_status() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"roles": {"developer": "yes"}}

    with pytest.raises(ValueError, match="invalid support status"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("scope", ["endpoint", "model"])
def test_model_registry_schema_rejects_non_bool_prompt_cache_compat(
    scope: str,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    compat_owner = endpoint if scope == "endpoint" else endpoint["models"]["model-a"]
    compat_owner["compat"] = {"supportsPromptCacheKey": "false"}

    with pytest.raises(ValueError, match="supportsPromptCacheKey"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_unknown_protocol_key() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"streaming": {"usageEvents": "supported"}}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_protocol_effort_map() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"reasoning": {"effortMap": {"minimal": 1}}}

    with pytest.raises(ValueError, match="string-or-null map"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_unknown_dialect_key() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {"reasoning": {"wireFormatAlias": "moonshot"}}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize(
    "dialect",
    [
        True,
        {"tools": True},
        {"reasoning": []},
        {"cache": "anthropic"},
    ],
)
def test_model_registry_schema_rejects_non_object_dialect_containers(
    dialect: object,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = dialect

    with pytest.raises(ValueError, match="must be an object"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_dialect_bool() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {"tools": {"resultNameRequired": "yes"}}

    with pytest.raises(ValueError, match="must be a boolean"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_null_dialect_bool() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = {"tools": {"resultNameRequired": None}}

    with pytest.raises(ValueError, match="must be a boolean"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize(
    "dialect",
    [
        {"maxOutputTokensField": ""},
        {"maxOutputTokensField": 1024},
        {"reasoning": {"wireFormat": ""}},
        {"reasoning": {"wireFormat": None}},
        {"cache": {"controlFormat": ""}},
        {"cache": {"controlFormat": False}},
    ],
)
def test_model_registry_schema_rejects_invalid_dialect_strings(
    dialect: dict[str, object],
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["dialect"] = dialect

    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_unknown_transport_key() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {"sdk": "openai"}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize(
    "transport",
    [
        {"kind": ""},
        {"stream": 12},
    ],
)
def test_model_registry_schema_rejects_invalid_transport_strings(
    transport: dict[str, object],
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = transport

    with pytest.raises(ValueError, match="must be a non-empty string"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("timeout", [0, float("nan"), float("inf"), float("-inf")])
def test_model_registry_schema_rejects_invalid_transport_timeout(
    timeout: float,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {"timeout": timeout}

    with pytest.raises(ValueError, match="must be a positive number"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_transport_fallback() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["transport"] = {"fallback": "yes"}

    with pytest.raises(ValueError, match="must be a boolean"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_unknown_routing_key() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["routing"] = {"provider": {"only": ["anthropic"]}}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize(
    "routing",
    [
        {"requestOverrides": True},
        {"requestOverrides": {"openrouter": True}},
    ],
)
def test_model_registry_schema_rejects_invalid_routing_request_overrides(
    routing: dict[str, object],
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["routing"] = routing

    with pytest.raises(ValueError, match="must be an object"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_integer_version() -> None:
    raw = _minimal_registry_raw(schema_version=None)
    raw["schemaVersion"] = "2"

    with pytest.raises(ValueError, match="schemaVersion must be an integer"):
        validate_model_registry_raw(raw)


def test_layered_model_registry_loads_v2_overlay_without_version_stamping(
    tmp_path,
) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_layered_model_registry(user_dir=user_dir)

    assert registry.get_model("custom", "openai-completions", "model-a")
    assert registry.get_model("moonshot", "openai-completions", "kimi-k2.6")


def test_layered_model_registry_loads_v2_overlay_protocol(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "protocol": {
                    "roles": {"developer": "unsupported"}
                  },
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_layered_model_registry(user_dir=user_dir)
    endpoint = registry.get_endpoint("custom", "openai-completions")

    assert endpoint is not None
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_layered_model_registry_rejects_v1_overlay_protocol(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 1,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "protocol": {
                    "roles": {"developer": "unsupported"}
                  },
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        load_layered_model_registry(user_dir=user_dir)


def test_layered_model_registry_loads_v2_overlay_dialect(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "dialect": {
                    "reasoning": {"wireFormat": "moonshot"}
                  },
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_layered_model_registry(user_dir=user_dir)
    endpoint = registry.get_endpoint("custom", "openai-completions")

    assert endpoint is not None
    assert endpoint.dialect.reasoning.wire_format == "moonshot"


def test_layered_model_registry_rejects_v1_overlay_dialect(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 1,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "dialect": {
                    "reasoning": {"wireFormat": "moonshot"}
                  },
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        load_layered_model_registry(user_dir=user_dir)


def test_layered_model_registry_loads_v2_overlay_transport_routing(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "transport": {"kind": "httpx"},
                  "routing": {
                    "requestOverrides": {
                      "openrouter": {"only": ["anthropic"]}
                    }
                  },
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_layered_model_registry(user_dir=user_dir)
    endpoint = registry.get_endpoint("custom", "openai-completions")

    assert endpoint is not None
    assert endpoint.transport.kind == "httpx"
    assert endpoint.routing.request_overrides == {"openrouter": {"only": ["anthropic"]}}


@pytest.mark.parametrize("field", ["transport", "routing"])
def test_layered_model_registry_rejects_v1_overlay_transport_routing(
    field: str,
    tmp_path,
) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                field: {},
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                        }
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

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        load_layered_model_registry(user_dir=user_dir)


@pytest.mark.parametrize("field", ["transport", "routing"])
def test_layered_model_registry_rejects_v1_overlay_model_transport_routing(
    field: str,
    tmp_path,
) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "00-version.json").write_text(
        json.dumps({"schemaVersion": 2, "providers": {}}),
        encoding="utf-8",
    )
    (user_dir / "10-custom.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "models": {
                                    "model-a": {
                                        field: {},
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

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        load_layered_model_registry(user_dir=user_dir)


def test_layered_model_registry_rejects_unknown_overlay_version(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 99,
          "providers": {}
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported models registry schemaVersion"):
        load_layered_model_registry(user_dir=user_dir)


def test_model_registry_schema_rejects_unknown_compat_key() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "compat": {"supportsReasoningEffortTypo": True},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_modality() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text", "telepathy"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }

    with pytest.raises(ValueError, match="invalid modalities"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_object_root() -> None:
    with pytest.raises(ValueError, match="<root>"):
        validate_model_registry_raw([])  # type: ignore[arg-type]


def test_model_registry_schema_accepts_auth_on_provider_endpoint_and_model() -> None:
    raw = {
        "providers": {
            "custom": {
                "auth": {
                    "kind": "apiKey",
                    "apiKeyEnvs": ["CUSTOM_API_KEY", "CUSTOM_FALLBACK_KEY"],
                    "extraHeaders": {"x-provider": "yes"},
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {"extraHeaders": {"x-endpoint": "yes"}},
                        "models": {
                            "model-a": {
                                "auth": {"apiKeyEnv": "MODEL_API_KEY"},
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_endpoint_preferred_flag() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "preferred": True,
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_colons_in_endpoint_keys() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions:cn:coding": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_colons_in_provider_keys() -> None:
    raw = {
        "providers": {
            "custom:cn": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="must not contain ':'"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_colons_in_model_keys() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "models": {
                            "model:a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="must not contain ':'"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_boolean_endpoint_preferred_flag() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "preferred": "yes",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="preferred"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_legacy_auth_override() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "authOverride": {"apiKeyEnv": "CUSTOM_API_KEY"},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_auth_and_legacy_auth_override() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {"apiKeyEnv": "CUSTOM_API_KEY"},
                        "authOverride": {"apiKeyEnv": "LEGACY_API_KEY"},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="both auth and authOverride"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_auth_shape() -> None:
    raw = {
        "providers": {
            "custom": {
                "auth": {
                    "apiKeyEnvs": "CUSTOM_API_KEY",
                    "extraHeaders": {"x-provider": 1},
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="apiKeyEnvs"):
        validate_model_registry_raw(raw)
