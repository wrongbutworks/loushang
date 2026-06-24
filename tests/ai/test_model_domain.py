from __future__ import annotations

import inspect

import pytest

from loushang.ai.model import (
    Endpoint,
    EndpointDialectCache,
    EndpointDialectReasoning,
    EndpointDialectTools,
    EndpointProtocolCache,
    EndpointProtocolFeatures,
    EndpointProtocolReasoning,
    EndpointProtocolRoles,
    EndpointProtocolSession,
    EndpointProtocolStreaming,
    EndpointProtocolTools,
    EndpointRouting,
    EndpointTransport,
    EndpointWireDialect,
    Model,
    Pricing,
    SupportStatus,
)


def test_endpoint_protocol_features_round_trip() -> None:
    protocol = EndpointProtocolFeatures.from_raw(
        {
            "store": "unsupported",
            "streaming": {
                "usage": "supported",
                "reasoningDelta": "unsupported",
            },
            "tools": {
                "strictSchema": "supported",
                "eagerInputStream": "unknown",
            },
            "reasoning": {
                "effort": "supported",
                "effortMap": {"off": None, "minimal": "low"},
            },
            "cache": {"promptKey": "supported"},
        }
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=protocol,
    )

    raw = endpoint.to_raw()["protocol"]

    assert raw == {
        "store": "unsupported",
        "streaming": {
            "usage": "supported",
            "reasoningDelta": "unsupported",
        },
        "tools": {
            "strictSchema": "supported",
            "eagerInputStream": "unknown",
        },
        "reasoning": {
            "effort": "supported",
            "effortMap": {"off": None, "minimal": "low"},
        },
        "cache": {"promptKey": "supported"},
    }
    assert EndpointProtocolFeatures.from_raw(raw) == EndpointProtocolFeatures(
        store=SupportStatus.UNSUPPORTED,
        streaming=EndpointProtocolStreaming(
            usage=SupportStatus.SUPPORTED,
            reasoning_delta=SupportStatus.UNSUPPORTED,
        ),
        tools=EndpointProtocolTools(strict_schema=SupportStatus.SUPPORTED),
        reasoning=EndpointProtocolReasoning(
            effort=SupportStatus.SUPPORTED,
            effort_map={"off": None, "minimal": "low"},
        ),
        cache=EndpointProtocolCache(prompt_key=SupportStatus.SUPPORTED),
    )


def test_endpoint_protocol_constructors_normalize_raw_status_strings() -> None:
    protocol = EndpointProtocolFeatures(
        store="supported",
        roles=EndpointProtocolRoles(developer="unsupported"),
        streaming=EndpointProtocolStreaming(
            usage="supported",
            reasoning_delta="unknown",
        ),
        reasoning=EndpointProtocolReasoning(
            effort="supported",
            interleaved="unsupported",
        ),
        tools=EndpointProtocolTools(
            strict_schema="supported",
            eager_input_stream="unsupported",
            fine_grained="unknown",
        ),
        cache=EndpointProtocolCache(
            on_tools="supported",
            long_retention="unsupported",
            prompt_key="supported",
        ),
        session=EndpointProtocolSession(
            id_header="supported",
            affinity_headers="unsupported",
        ),
    )

    assert protocol.store is SupportStatus.SUPPORTED
    assert protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert protocol.streaming.reasoning_delta is SupportStatus.UNKNOWN
    assert protocol.tools.fine_grained is SupportStatus.UNKNOWN
    assert protocol.to_raw() == {
        "store": "supported",
        "roles": {"developer": "unsupported"},
        "streaming": {"usage": "supported"},
        "reasoning": {
            "effort": "supported",
            "interleaved": "unsupported",
        },
        "tools": {
            "strictSchema": "supported",
            "eagerInputStream": "unsupported",
        },
        "cache": {
            "onTools": "supported",
            "longRetention": "unsupported",
            "promptKey": "supported",
        },
        "session": {
            "idHeader": "supported",
            "affinityHeaders": "unsupported",
        },
    }


def test_endpoint_protocol_constructors_reject_invalid_status_strings() -> None:
    with pytest.raises(ValueError, match="unsupported support status"):
        EndpointProtocolTools(strict_schema="yes")


def test_endpoint_wire_dialect_round_trip() -> None:
    dialect = EndpointWireDialect.from_raw(
        {
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
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        dialect=dialect,
    )

    raw = endpoint.to_raw()["dialect"]

    assert raw == {
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
    assert EndpointWireDialect.from_raw(raw) == EndpointWireDialect(
        max_output_tokens_field="max_completion_tokens",
        tools=EndpointDialectTools(
            result_name_required=True,
            assistant_bridge_required=False,
            stream_flag=True,
        ),
        reasoning=EndpointDialectReasoning(
            wire_format="moonshot",
            thinking_as_text=True,
            assistant_content_required=False,
        ),
        cache=EndpointDialectCache(control_format="anthropic"),
    )


def test_endpoint_wire_dialect_constructors_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="wire dialect field must be a boolean"):
        EndpointDialectTools(result_name_required="yes")
    with pytest.raises(
        ValueError, match="wire dialect field must be a non-empty string"
    ):
        EndpointWireDialect(max_output_tokens_field="")


@pytest.mark.parametrize("section", ["tools", "reasoning", "cache"])
def test_endpoint_wire_dialect_rejects_non_object_sections(section: str) -> None:
    with pytest.raises(
        ValueError,
        match=f"wire dialect section must be an object: {section}",
    ):
        EndpointWireDialect.from_raw({section: True})


def test_endpoint_transport_round_trip() -> None:
    transport = EndpointTransport.from_raw(
        {
            "kind": "httpx",
            "stream": "sse",
            "fallback": True,
            "timeout": 30,
        }
    )
    endpoint = Endpoint(
        id="anthropic-messages",
        provider="custom",
        api="anthropic-messages",
        transport=transport,
    )

    raw = endpoint.to_raw()["transport"]

    assert raw == {
        "kind": "httpx",
        "stream": "sse",
        "fallback": True,
        "timeout": 30,
    }
    assert EndpointTransport.from_raw(raw) == transport


def test_endpoint_transport_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="transport field must be a non-empty string"):
        EndpointTransport(kind="")
    with pytest.raises(ValueError, match="transport field must be a boolean"):
        EndpointTransport(fallback="yes")


@pytest.mark.parametrize("timeout", [0, float("nan"), float("inf"), float("-inf")])
def test_endpoint_transport_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="transport field must be a positive number"):
        EndpointTransport(timeout=timeout)
    with pytest.raises(ValueError, match="transport field must be a positive number"):
        EndpointTransport.from_raw({"timeout": timeout})


def test_endpoint_routing_round_trip_defensively_copies_raw() -> None:
    routing = EndpointRouting.from_raw(
        {
            "requestOverrides": {
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai", "anthropic"]},
            }
        }
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        routing=routing,
    )

    raw = endpoint.to_raw()["routing"]
    raw["requestOverrides"]["openrouter"]["only"].append("openai")

    assert routing.to_raw() == {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }
    assert EndpointRouting.from_raw(endpoint.to_raw()["routing"]) == routing


def test_endpoint_routing_rejects_invalid_request_overrides() -> None:
    with pytest.raises(ValueError, match="routing field must be an object"):
        EndpointRouting.from_raw({"requestOverrides": True})
    with pytest.raises(ValueError, match="requestOverrides entries must be objects"):
        EndpointRouting.from_raw({"requestOverrides": {"openrouter": True}})


def test_model_omits_unknown_pricing_from_raw() -> None:
    model = Model(id="public-model", provider="custom", endpoint="openai-completions")

    raw = model.to_raw()

    assert model.pricing is None
    assert "pricing" not in raw


def test_pricing_round_trip_preserves_unknown_and_zero_components() -> None:
    pricing = Pricing.from_raw({"input": 0, "output": 2.0})

    assert pricing == Pricing(input=0, output=2.0)
    assert pricing.cache_read is None
    assert pricing.cache_write is None
    assert pricing.to_raw() == {"input": 0, "output": 2.0}


def test_model_upstream_id_round_trip() -> None:
    model = Model(
        id="public-model",
        provider="custom",
        endpoint="openai-completions",
        upstream_id="vendor/public-model:latest",
    )

    raw = model.to_raw()

    assert raw["upstreamId"] == "vendor/public-model:latest"
    assert "upstreamModelId" not in raw["compat"]


def test_model_constructor_keeps_existing_fields_before_upstream_id() -> None:
    parameters = list(inspect.signature(Model).parameters)

    assert parameters.index("knowledge") < parameters.index("upstream_id")
    assert parameters.index("_routing_legacy_raw") < parameters.index("upstream_id")


def test_model_rejects_invalid_upstream_id() -> None:
    with pytest.raises(ValueError, match="upstream_id must be a non-empty string"):
        Model(
            id="public-model",
            provider="custom",
            endpoint="openai-completions",
            upstream_id="",
        )
    with pytest.raises(ValueError, match="upstream_id must be a non-empty string"):
        Model(
            id="public-model",
            provider="custom",
            endpoint="openai-completions",
            upstream_id=" ",
        )
