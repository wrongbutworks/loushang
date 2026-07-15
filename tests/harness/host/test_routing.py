from __future__ import annotations

import asyncio

from loushang.harness.host.routing import PayloadEventRouter


def test_payload_event_router_preserves_stage_order_and_short_circuits() -> None:
    order: list[str] = []
    router: PayloadEventRouter[dict[str, str]] = PayloadEventRouter(
        kind_of=lambda event: event["kind"],
        before={"done": (lambda event: order.append(f"before:{event['value']}"),)},
        mirrors=(
            lambda event: _record(order, f"mirror-1:{event['value']}"),
            lambda event: _record(order, f"mirror-2:{event['value']}"),
        ),
        after={"done": (lambda event: _record(order, f"after:{event['value']}"),)},
    )

    stopped = asyncio.run(router.route({"kind": "done", "value": "opaque"}))

    assert stopped is False
    assert order == [
        "before:opaque",
        "mirror-1:opaque",
        "mirror-2:opaque",
        "after:opaque",
    ]

    stopping: PayloadEventRouter[dict[str, str]] = PayloadEventRouter(
        kind_of=lambda event: event["kind"],
        mirrors=(lambda event: True, lambda event: order.append("unreachable")),
    )
    assert asyncio.run(stopping.route({"kind": "done", "value": "opaque"})) is True
    assert "unreachable" not in order


async def _record(order: list[str], value: str) -> None:
    order.append(value)
