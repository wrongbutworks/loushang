"""Inspect typed endpoint contract facts from the built-in catalog.

This advanced example is offline. It reads the model catalog and prints the
typed endpoint-default protocol, wire dialect, transport, and routing contracts
alongside the remaining legacy compat keys. Model-level effective protocol and
dialect facts still flow through legacy compat during the migration.
"""

from __future__ import annotations

import json
from typing import Any

from loushang.ai.model import load_builtin_model_registry

DEFAULT_PROVIDER = "moonshot"
DEFAULT_ENDPOINT = "openai-completions"
DEFAULT_MODEL = "kimi-k2.5"


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
        contract["model"] = model_id
        contract["modelEffectiveLegacyCompat"] = dict(sorted(model.compat.items()))
        contract["modelEffectiveLegacyCompatKeys"] = sorted(model.compat)
    return contract


def main() -> None:
    print(json.dumps(inspect_endpoint_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
