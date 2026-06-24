"""Inspect typed provider request facts from the built-in catalog.

This advanced example is offline. It reads the model catalog and prints the
typed endpoint-default protocol, wire dialect, transport, and routing contracts,
then shows the model-effective request contract and adapter-effective request
facts produced by provider resolution.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loushang.ai.model import Endpoint, load_builtin_model_registry
from loushang.ai.provider import resolve_request_for_model

DEFAULT_PROVIDER = "moonshot"
DEFAULT_ENDPOINT = "openai-completions"
DEFAULT_MODEL = "kimi-k2.6"


def inspect_endpoint_contract(
    provider_id: str = DEFAULT_PROVIDER,
    endpoint_id: str = DEFAULT_ENDPOINT,
    model_id: str | None = DEFAULT_MODEL,
) -> dict[str, Any]:
    registry = load_builtin_model_registry()
    endpoint = registry.get_endpoint(provider_id, endpoint_id)
    if endpoint is None:
        raise KeyError((provider_id, endpoint_id))
    contract: dict[str, Any] = {
        "provider": provider_id,
        "endpoint": endpoint_id,
        "api": endpoint.api,
        "protocolScope": "endpoint-default",
        "protocol": endpoint.protocol.to_raw(),
        "dialectScope": "endpoint-default",
        "dialect": endpoint.dialect.to_raw(),
        "transportScope": "endpoint-default",
        "transport": endpoint.transport.to_raw(),
        "routingScope": "endpoint-default",
        "routing": endpoint.routing.to_raw(),
        "legacyCompatKeys": sorted(endpoint.compat),
    }
    if model_id is not None:
        model = registry.find_model(provider_id, endpoint_id, model_id)
        if model is None:
            raise KeyError((provider_id, endpoint_id, model_id))
        resolved = resolve_request_for_model(
            model,
            registry=registry,
            env=_offline_template_env(endpoint),
        )
        contract["model"] = model_id
        contract["requestProtocolScope"] = "model-effective"
        contract["requestProtocol"] = resolved.protocol.to_raw()
        contract["requestDialectScope"] = "model-effective"
        contract["requestDialect"] = resolved.dialect.to_raw()
        contract["adapterProtocolScope"] = "adapter-effective"
        contract["adapterProtocol"] = resolved.adapter_protocol.to_raw()
        contract["adapterDialectScope"] = "adapter-effective"
        contract["adapterDialect"] = resolved.adapter_dialect.to_raw()
        contract["requestTransportScope"] = "model-effective"
        contract["requestTransport"] = resolved.transport.to_raw()
        contract["requestRoutingScope"] = "model-effective"
        contract["requestRouting"] = resolved.routing.to_raw()
    return contract


def _offline_template_env(endpoint: Endpoint) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in _endpoint_template_values(endpoint):
        for name in re.findall(r"\{([A-Z_][A-Z0-9_]*)\}", value):
            env.setdefault(name, f"example-{name.lower()}")
    return env


def _endpoint_template_values(endpoint: Endpoint) -> tuple[str, ...]:
    values: list[str] = []
    if endpoint.base_url:
        values.append(endpoint.base_url)
    return tuple(values)


def main() -> None:
    print(json.dumps(inspect_endpoint_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
