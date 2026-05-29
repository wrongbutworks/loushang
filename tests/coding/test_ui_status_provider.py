from __future__ import annotations


def test_status_provider_renders_toolbar_snapshot_from_session_state() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    provider = CodingTuiStatusProvider(
        model_label="moonshot/kimi",
        cwd="/repo",
        branch="main",
        session_label=lambda: "session-name",
        thinking_level=lambda: "high",
        running=lambda: True,
    )

    status = provider.render()

    assert "model=moonshot/kimi" in status
    assert "cwd=/repo" in status
    assert "branch=main" in status
    assert "session=session-name" in status
    assert "thinking=high" in status
    assert "running" in status


def test_status_provider_omits_missing_optional_values() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
    )

    status = provider.render()

    assert status == "cwd=/repo"


def test_status_provider_tracks_statusline_visibility() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
    )

    assert provider.is_visible() is True
    assert provider.set_visible(False) == "Status line: off"
    assert provider.is_visible() is False
    assert provider.set_visible(True) == "Status line: on"
    assert provider.is_visible() is True
    assert provider.set_visible(None) == "Status line: on"


def test_status_provider_formats_settings_summary() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider
    from loushang.tui import SettingItem, SettingsList

    provider = CodingTuiStatusProvider(
        model_label="moonshot/kimi",
        cwd="/repo",
        branch="main",
        session_label=lambda: "abc",
        thinking_level=lambda: "high",
        running=lambda: False,
    )

    assert provider.settings_list() == SettingsList(
        (SettingItem(id="statusline", label="Status line", enabled=True),)
    )
    assert provider.settings_text() == "Settings\n> [x] Status line"
    provider.set_visible(False)
    assert provider.settings_text() == "Settings\n> [ ] Status line"
