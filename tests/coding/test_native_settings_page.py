from __future__ import annotations

import asyncio

from loushang.coding.types import ModelSelection
from loushang.coding.ui.settings_page import SettingsPageView
from loushang.coding.ui.status_provider import CodingTuiStatusProvider
from loushang.tui import InputEvent, InputIntent, RenderConstraints
from loushang.tui.cell_width import strip_control_sequences


class _Session:
    def __init__(self) -> None:
        self.current_model = ModelSelection(provider="moonshot", model_id="kimi-for-coding")
        self.models = (
            ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
            ModelSelection(provider="openai", model_id="gpt-5.4"),
        )
        self.set_model_calls: list[object] = []

    def get_model_selection(self) -> object:
        return self.current_model

    def get_available_models(self) -> list[object]:
        return list(self.models)

    async def set_model(self, selection: object) -> None:
        self.set_model_calls.append(selection)
        self.current_model = selection


class _SettingsManager:
    def __init__(self) -> None:
        self.terminal_progress = False

    def get_show_terminal_progress(self) -> bool:
        return self.terminal_progress

    def set_show_terminal_progress(self, enabled: bool) -> None:
        self.terminal_progress = enabled


def test_status_provider_exposes_read_only_snapshot() -> None:
    provider = CodingTuiStatusProvider(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label=lambda: "abcd",
        thinking_level=lambda: "medium",
        running=lambda: False,
    )

    snapshot = provider.snapshot()

    assert snapshot.model_label == "moonshot/kimi-for-coding"
    assert snapshot.cwd == "/repo"
    assert snapshot.branch == "main"
    assert snapshot.session_label == "abcd"
    assert snapshot.thinking_level == "medium"
    assert snapshot.running is False
    assert snapshot.statusline_visible is True


def _status_provider() -> CodingTuiStatusProvider:
    return CodingTuiStatusProvider(
        model_label="moonshot/kimi-for-coding",
        cwd="/repo",
        branch="main",
        session_label=lambda: "abcd",
        thinking_level=lambda: None,
        running=lambda: False,
    )


def _page(settings_manager: object | None = None) -> SettingsPageView:
    return asyncio.run(
        SettingsPageView.create(
            session=_Session(),
            status_provider=_status_provider(),
            settings_manager=settings_manager,
        )
    )


def _plain(page: SettingsPageView, *, width: int = 100, height: int = 18) -> tuple[str, ...]:
    rendered = page.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text) for line in rendered.lines)


def test_settings_page_opens_config_tab_with_search_focus() -> None:
    page = _page()
    lines = _plain(page)

    assert any("Status" in line and "Config" in line and "Model" in line for line in lines)
    assert any("Search settings" in line for line in lines)
    assert any("Status line" in line for line in lines)
    assert page.editor_input_target() is not None


def test_settings_page_search_filters_config_rows() -> None:
    page = _page()

    assert page.handle_input(InputEvent(kind="text", text="status")) is True
    lines = _plain(page)

    assert any("Status line" in line for line in lines)
    assert not any("Terminal progress" in line for line in lines)


def test_settings_page_statusline_toggle_returns_setting_intent_and_apply_updates_rows() -> None:
    page = _page()
    page.handle_input(InputEvent(kind="key", key="down"))
    intent = page.handle_input(InputEvent(kind="key", key="enter"))

    assert intent == InputIntent(kind="setting", text="statusline", note="false")

    result = asyncio.run(page.apply_setting("statusline", "false"))

    assert result.statusline_visible is False
    assert result.message == "Status line: off"
    assert any("Status line" in line and "false" in line for line in _plain(page))


def test_settings_page_terminal_progress_apply_updates_settings_manager_and_rows() -> None:
    settings_manager = _SettingsManager()
    page = _page(settings_manager=settings_manager)

    result = asyncio.run(page.apply_setting("terminal.progress", "true"))

    assert settings_manager.terminal_progress is True
    assert result.message == "Terminal progress: on"
    assert any("Terminal progress" in line and "true" in line for line in _plain(page))


def test_settings_page_q_is_search_text_but_closes_from_list_focus() -> None:
    search_page = _page()

    assert search_page.handle_input(InputEvent(kind="text", text="q")) is True
    assert any("q" in line for line in _plain(search_page))

    list_page = _page()
    list_page.handle_input(InputEvent(kind="key", key="down"))

    assert list_page.handle_input(InputEvent(kind="text", text="q")) == InputIntent(kind="surface_close")


def test_settings_page_search_editing_keys_do_not_switch_tabs() -> None:
    page = _page()

    before = page.tabs.value
    assert page.handle_input(InputEvent(kind="key", key="right")) is True

    assert page.tabs.value == before


def test_settings_page_model_tab_filters_and_selects_model() -> None:
    page = _page()
    page.tabs.focus_header()
    page.handle_input(InputEvent(kind="key", key="right"))
    page.handle_input(InputEvent(kind="key", key="down"))

    assert page.tabs.value == "model"
    assert page.handle_input(InputEvent(kind="text", text="gpt")) is True
    intent = page.handle_input(InputEvent(kind="key", key="enter"))

    assert intent == InputIntent(kind="setting", text="model.current", note="openai/gpt-5.4")
