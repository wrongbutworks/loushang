from __future__ import annotations


def test_status_snapshot_compatibility_export_is_identical() -> None:
    from loushang.coding.ui.status_provider import (
        StatusSnapshot as CodingStatusSnapshot,
    )
    from loushang.harnesstui.status.snapshot import StatusSnapshot

    assert CodingStatusSnapshot is StatusSnapshot


def test_status_provider_returns_shared_snapshot() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider
    from loushang.harnesstui.status.line import StatusLineSettings
    from loushang.harnesstui.status.snapshot import StatusSnapshot

    provider = CodingTuiStatusProvider(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label=lambda: "abcd",
        thinking_level=lambda: "high",
        running=lambda: True,
        statusline_settings=StatusLineSettings(enabled=False),
    )

    snapshot = provider.snapshot()

    assert type(snapshot) is StatusSnapshot
    assert snapshot == StatusSnapshot(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        thinking_level="high",
        running=True,
        statusline_visible=False,
        statusline_settings=StatusLineSettings(enabled=False),
    )


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


def test_status_provider_formats_plain_settings_summary_without_legacy_tui_models() -> None:
    from loushang.coding.ui.status_provider import CodingTuiStatusProvider

    provider = CodingTuiStatusProvider(
        model_label="moonshot/kimi",
        cwd="/repo",
        branch="main",
        session_label=lambda: "abc",
        thinking_level=lambda: "high",
        running=lambda: False,
    )

    assert provider.settings_summary_text() == "Settings\nStatus line: true"
    assert not hasattr(provider, "legacy_settings_list")
    assert not hasattr(provider, "legacy_settings_text")
    provider.set_visible(False)
    assert provider.settings_summary_text() == "Settings\nStatus line: false"
