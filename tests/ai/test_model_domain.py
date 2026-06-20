from __future__ import annotations

import pytest

from loushang.ai.model import (
    Endpoint,
    EndpointProtocolCache,
    EndpointProtocolFeatures,
    EndpointProtocolReasoning,
    EndpointProtocolRoles,
    EndpointProtocolSession,
    EndpointProtocolStreaming,
    EndpointProtocolTools,
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
