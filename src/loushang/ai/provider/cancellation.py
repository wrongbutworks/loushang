from __future__ import annotations


def is_signal_cancelled(signal: object | None) -> bool:
    return bool(
        signal is not None
        and (
            getattr(signal, "aborted", False)
            or getattr(signal, "cancelled", False)
        )
    )


__all__ = ["is_signal_cancelled"]
