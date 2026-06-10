from __future__ import annotations


def is_activation_event(event: object) -> bool:
    return (
        getattr(event, "kind", "") == "key"
        and getattr(event, "key", "") in {"enter", "space"}
        or getattr(event, "kind", "") == "text"
        and getattr(event, "text", "") == " "
    )


def callback_result(result: object) -> object:
    return True if result is None else result
