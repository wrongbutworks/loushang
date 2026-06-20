from __future__ import annotations

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
    EndpointWireDialect,
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
    with pytest.raises(ValueError, match="wire dialect field must be a non-empty string"):
        EndpointWireDialect(max_output_tokens_field="")


@pytest.mark.parametrize("section", ["tools", "reasoning", "cache"])
def test_endpoint_wire_dialect_rejects_non_object_sections(section: str) -> None:
    with pytest.raises(
        ValueError,
        match=f"wire dialect section must be an object: {section}",
    ):
        EndpointWireDialect.from_raw({section: True})
