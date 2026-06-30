"""Inspect typed provider request facts from the built-in catalog.

This advanced example is offline. It reads the model catalog and prints the
endpoint-default adapter, transport, and routing contracts, then shows the
model-effective request facts produced by provider resolution.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loushang.ai.auth import ApiKeyAuth
from loushang.ai.model import Endpoint, load_builtin_model_registry
from loushang.ai.options import CallOptions
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
        "adapterScope": "endpoint-default",
        "adapter": endpoint.adapter.to_raw() if endpoint.adapter is not None else None,
        "transportScope": "endpoint-default",
        "transport": endpoint.transport.to_raw(),
        "routingScope": "endpoint-default",
        "routing": endpoint.routing.to_raw(),
    }
    if model_id is not None:
        model = registry.find_model(provider_id, endpoint_id, model_id)
        if model is None:
            raise KeyError((provider_id, endpoint_id, model_id))
        resolved = resolve_request_for_model(
            model,
            options=CallOptions(auth=ApiKeyAuth("example-offline-api-key")),
            registry=registry,
            env=_offline_template_env(endpoint),
        )
        contract["model"] = model_id
        contract["requestAdapterScope"] = "model-effective"
        adapter_config = resolved.adapter_config
        contract["requestAdapter"] = (
            adapter_config.to_raw() if hasattr(adapter_config, "to_raw") else None
        )
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
