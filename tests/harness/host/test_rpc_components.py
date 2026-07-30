from __future__ import annotations

import asyncio
import json
from io import StringIO

import pytest

from loushang.harness.host.jsonl_command_host import JsonlCommand
from loushang.harness.host.rpc import RpcHost, run_rpc_host
from loushang.harness.host.rpc.arguments import (
    optional_env_pairs,
    optional_number,
    require_string,
)
from loushang.harness.host.rpc.output import RpcOutput
from loushang.harness.host.rpc.routing import legacy_rpc_routes


def test_rpc_package_keeps_the_stable_host_exports() -> None:
    assert RpcHost.__module__ == "loushang.harness.host.rpc.runtime"
    assert run_rpc_host.__module__ == "loushang.harness.host.rpc.runtime"


def test_rpc_argument_readers_preserve_strict_alias_and_env_rules() -> None:
    assert require_string({"model_id": "model-a"}, "modelId", "model_id") == "model-a"
    assert optional_env_pairs([["A", "1"], ("B", "2")]) == [
        ["A", "1"],
        ["B", "2"],
    ]

    with pytest.raises(ValueError, match="finite number"):
        optional_number({"timeout": float("inf")}, "timeout")
    with pytest.raises(ValueError, match="2-item string pairs"):
        optional_env_pairs([["A"]])


def test_rpc_output_preserves_success_and_safe_fallback_wire_shapes() -> None:
    stdout = StringIO()
    output = RpcOutput(stdout)

    output.success(command="probe", request_id="one", data=None)
    output.write(
        {
            "type": "response",
            "command": "unsafe",
            "id": "two",
            "value": object(),
        }
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert lines[0] == {
        "type": "response",
        "command": "probe",
        "success": True,
        "id": "one",
        "data": None,
    }
    assert lines[1] == {
        "type": "response",
        "command": "unsafe",
        "success": False,
        "error": "Failed to serialize RPC output.",
        "id": "two",
    }


def test_legacy_rpc_routes_adapt_sync_and_async_handlers_without_name_lookup() -> None:
    calls: list[tuple[str, str | None, dict[str, object]]] = []

    def sync_handler(command_id: str | None, payload: dict[str, object]) -> None:
        calls.append(("sync", command_id, payload))

    async def async_handler(
        command_id: str | None, payload: dict[str, object]
    ) -> None:
        calls.append(("async", command_id, payload))

    routes = legacy_rpc_routes(
        (("sync", sync_handler), ("async", async_handler))
    )
    asyncio.run(
        routes[0].handler(JsonlCommand("one", "sync", {"value": "a"}))
    )
    asyncio.run(
        routes[1].handler(JsonlCommand("two", "async", {"value": "b"}))
    )

    assert calls == [
        ("sync", "one", {"value": "a"}),
        ("async", "two", {"value": "b"}),
    ]
