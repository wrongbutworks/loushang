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
    from loushang.coding.ui.status_line import StatusLineSettings
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    saved: list[StatusLineSettings] = []
    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
        statusline_settings=StatusLineSettings(enabled=False, style="muted"),
        on_statusline_settings_changed=saved.append,
    )

    assert provider.is_visible() is False
    assert provider.statusline_settings() == StatusLineSettings(enabled=False, style="muted")
    assert provider.set_visible(True) == "Status line: on"
    assert provider.is_visible() is True
    assert provider.statusline_settings().enabled is True
    assert provider.set_visible(None) == "Status line: on"
    assert saved == [StatusLineSettings(enabled=True, style="muted")]


def test_status_provider_applies_full_statusline_settings() -> None:
    from loushang.coding.ui.status_line import StatusLineSettings
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    saved: list[StatusLineSettings] = []
    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
        on_statusline_settings_changed=saved.append,
    )
    settings = StatusLineSettings(enabled=False, queue="true", message="false", separator="dot", style="muted")

    assert provider.apply_statusline_settings(settings) == "Status line: off"

    assert provider.statusline_settings() == settings
    assert provider.is_visible() is False
    assert saved == [settings]


def test_status_provider_applies_individual_statusline_settings() -> None:
    from loushang.coding.ui.status_line import StatusLineSettings
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    saved: list[StatusLineSettings] = []
    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
        on_statusline_settings_changed=saved.append,
    )

    assert provider.apply_statusline_setting("statusline.enabled", "false") == "Status line: off"
    assert provider.apply_statusline_setting("statusline.field.queue", "true") == "Status line queue: true"
    assert provider.apply_statusline_setting("statusline.separator", "dot") == "Status line separator: dot"
    assert provider.apply_statusline_setting("statusline.style", "plain") == "Status line style: plain"

    settings = provider.statusline_settings()
    assert settings.enabled is False
    assert settings.queue == "true"
    assert settings.separator == "dot"
    assert settings.style == "plain"
    assert saved == [
        StatusLineSettings(enabled=False),
        StatusLineSettings(enabled=False, queue="true"),
        StatusLineSettings(enabled=False, queue="true", separator="dot"),
        StatusLineSettings(enabled=False, queue="true", separator="dot", style="plain"),
    ]


def test_status_provider_rejects_invalid_statusline_setting_values() -> None:
    from loushang.coding.ui.status_line import StatusLineSettings
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    saved: list[StatusLineSettings] = []
    provider = CodingTuiStatusProvider(
        model_label=None,
        cwd="/repo",
        branch=None,
        session_label=lambda: None,
        thinking_level=lambda: None,
        running=lambda: False,
        on_statusline_settings_changed=saved.append,
    )

    assert provider.apply_statusline_setting("statusline.field.queue", "maybe") == "Invalid status line queue value."
    assert provider.apply_statusline_setting("statusline.separator", "slash") == "Invalid status line separator value."
    assert provider.apply_statusline_setting("statusline.unknown", "true") == "Unknown status line setting: statusline.unknown"
    assert provider.statusline_settings().queue == "auto"
    assert provider.statusline_settings().separator == "pipe"
    assert saved == []


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
