from __future__ import annotations

import webbrowser

import pytest

from loushang.ai.auth.browser import open_browser


def test_open_browser_returns_boolean_without_launching_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, bool]] = []

    def fake_open(url: str, *, new: int, autoraise: bool) -> bool:
        calls.append((url, new, autoraise))
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)

    assert open_browser("https://example.com") is True
    assert calls == [("https://example.com", 1, True)]


def test_open_browser_returns_false_when_browser_open_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(url: str, *, new: int, autoraise: bool) -> bool:
        raise RuntimeError(f"cannot open {url} with {new=} {autoraise=}")

    monkeypatch.setattr(webbrowser, "open", fake_open)

    assert open_browser("https://example.com") is False
