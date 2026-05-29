from __future__ import annotations

from loushang.ai.auth.browser import open_browser


def test_open_browser_returns_boolean() -> None:
    assert isinstance(open_browser("https://example.com"), bool)
