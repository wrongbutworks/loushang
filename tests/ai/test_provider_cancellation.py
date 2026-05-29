from __future__ import annotations

from types import SimpleNamespace


def test_is_signal_cancelled_accepts_aborted() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(SimpleNamespace(aborted=True)) is True


def test_is_signal_cancelled_accepts_cancelled() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(SimpleNamespace(cancelled=True)) is True


def test_is_signal_cancelled_ignores_missing_or_false_flags() -> None:
    from loushang.ai.provider.cancellation import is_signal_cancelled

    assert is_signal_cancelled(None) is False
    assert is_signal_cancelled(SimpleNamespace()) is False
    assert is_signal_cancelled(SimpleNamespace(aborted=False, cancelled=False)) is False
