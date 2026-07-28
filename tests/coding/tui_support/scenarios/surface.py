from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loushang.ai.model import ModelSelection
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_surfaces import ScreenSurfaceManager
from loushang.harnesstui.status.provider import StatusProvider
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.harnesstui.testing.scenarios.surface import surface_scenarios
from loushang.tui import DialogSurface
from loushang.tui.playback_suite import (
    PlaybackScenarioSpec as ScreenPlaybackScenarioSpec,
)
from tests.coding.tui_support.fakes import (
    ModelPlaybackSession,
    SessionCommandPlaybackSession,
)
from tests.coding.tui_support.playback import ScreenTuiLoopPlayback
from tests.coding.tui_support.scenario_binding import (
    CODING_SCENARIO_FACTORY,
    CODING_SCENARIO_FRAME_CONTRACTS,
)


def _run_commands_info_surface() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    manager = _surface_manager(playback.app)

    result = playback.run(
        (0.00, "/commands terminal\r"),
        (0.01, "\r"),
        (0.03, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    result.assert_text_contains("Commands")
    result.assert_text_contains("/terminal - Show terminal diagnostics (local)")
    result.assert_text_not_contains("/settings - Open settings (local)")
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _run_commands_info_session_command() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    session = SessionCommandPlaybackSession()
    manager = _surface_manager(playback.app, session=session)

    result = playback.run(
        (0.00, "/commands name\r"),
        (0.01, "\r"),
        (0.03, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    result.assert_text_contains("Commands")
    result.assert_text_contains("/rename <name> - Rename the current session (builtin)")
    result.assert_text_not_contains("/terminal - Show terminal diagnostics (local)")
    result.assert_no_clear_screen()
    assert session.commands == []
    assert session.prompts == []
    assert result.app.active_surface is None
    return result


def _run_command_palette_select() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    manager = _surface_manager(playback.app)

    result = playback.run(
        (0.00, "/command\r"),
        (0.01, "term"),
        (0.03, "\r"),
        (0.05, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    result.assert_composer_text("/terminal ")
    result.assert_text_contains("Command selected: /terminal")
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _run_command_palette_session_command() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    session = SessionCommandPlaybackSession()
    manager = _surface_manager(playback.app, session=session)

    result = playback.run(
        (0.00, "/command\r"),
        (0.01, "nam"),
        (0.03, "\r"),
        (0.05, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    result.assert_composer_text("/rename ")
    result.assert_text_contains("Command selected: /rename")
    result.assert_no_clear_screen()
    assert session.commands == []
    assert session.prompts == []
    assert result.app.active_surface is None
    return result


def _run_settings_search() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    manager = _surface_manager(playback.app)

    result = playback.run(
        (0.00, "/settings\r"),
        (0.01, "zz"),
        (0.03, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    result.assert_text_contains("Settings")
    result.assert_text_contains("Search settings...")
    result.assert_text_contains("│ zz")
    result.assert_text_contains("No matching settings")
    result.assert_text_not_contains("Status line: off")
    result.assert_no_clear_screen()
    return result


def _run_model_select() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    session = ModelPlaybackSession()
    manager = _surface_manager(playback.app, session=session)

    result = playback.run(
        (0.00, "/model\r"),
        (0.01, "2"),
        (0.03, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    assert session.current_model == ModelSelection(
        provider="openai", model_id="gpt-5.4"
    )
    assert playback.app.state.model_label == "openai/gpt-5.4"
    result.assert_text_contains("Select Model")
    result.assert_text_contains("Model set: openai/gpt-5.4")
    result.assert_text_contains("openai/gpt-5.4 | repo | main | abcd | idle")
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _run_model_select_search() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    session = ModelPlaybackSession()
    manager = _surface_manager(playback.app, session=session)

    result = playback.run(
        (0.00, "/model\r"),
        (0.01, "gpt"),
        (0.03, "\r"),
        (0.05, ""),
        handle_local=manager.handle_text,
        handle_surface_intent=manager.handle_surface_intent,
        is_local_command=manager.is_local_command,
    )

    result.assert_exit_code(0)
    assert session.current_model == ModelSelection(
        provider="openai", model_id="gpt-5.4"
    )
    assert playback.app.state.model_label == "openai/gpt-5.4"
    result.assert_text_contains("Search: gpt")
    result.assert_text_contains("Model set: openai/gpt-5.4")
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _run_approval_surface() -> object:
    return _run_approval_surface_response(
        input_text="y",
        approved=True,
        scope="once",
        expected_status="Action confirmed: write file",
    )


def _run_approval_session_surface() -> object:
    return _run_approval_surface_response(
        input_text="a",
        approved=True,
        scope="session",
        allow_session=True,
        expected_status="Action confirmed: write file",
    )


def _run_approval_reject_surface() -> object:
    return _run_approval_surface_response(
        input_text="n",
        approved=False,
        scope="once",
        expected_status="Action rejected",
    )


def _run_approval_surface_response(
    *,
    input_text: str,
    approved: bool,
    scope: str,
    expected_status: str,
    allow_session: bool = False,
) -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    approvals: list[dict[str, object]] = []

    async def on_approval(payload: dict[str, object]) -> None:
        approvals.append(payload)

    manager = _surface_manager(playback.app, on_approval=on_approval)
    manager.open_approval(
        action="write file",
        risk="Will modify /repo/app.py",
        action_id="write:app.py",
        allow_session=allow_session,
    )

    result = playback.run(
        (0.00, input_text),
        (0.02, ""),
        handle_surface_intent=manager.handle_surface_intent,
    )

    result.assert_exit_code(0)
    assert approvals == [
        {
            "action_id": "write:app.py",
            "action": "write file",
            "approved": approved,
            "scope": scope,
            "raw_note": "write:app.py",
        }
    ]
    result.assert_text_contains("Approval")
    result.assert_text_contains("write file")
    result.assert_text_contains(expected_status)
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _run_dialog_surface() -> object:
    playback = ScreenTuiLoopPlayback(
        width=100, height=18, model_label="moonshot/kimi-for-coding"
    )
    manager = _surface_manager(playback.app)
    playback.app.active_surface = ScreenSurfaceView(
        title="Confirm",
        purpose="dialog",
        content=DialogSurface(title="Confirm", message="Proceed?"),
        footer="",
        presentation="bottom-exclusive",
    )

    result = playback.run(
        (0.00, "\r"),
        (0.02, ""),
        handle_surface_intent=manager.handle_surface_intent,
    )

    result.assert_exit_code(0)
    result.assert_text_contains("Confirm")
    result.assert_text_contains("Proceed?")
    result.assert_no_clear_screen()
    assert result.app.active_surface is None
    return result


def _surface_manager(
    app: ScreenCodingTuiApp,
    *,
    session: object | None = None,
    on_approval: Callable[[dict[str, Any]], Awaitable[bool | None]] | None = None,
) -> ScreenSurfaceManager:
    return ScreenSurfaceManager(
        app=app,
        session=object() if session is None else session,
        status_provider=_status_provider(app),
        on_approval=on_approval,
    )


def _status_provider(app: object) -> StatusProvider:
    state = getattr(app, "state")
    return StatusProvider(
        model_label=state.model_label,
        cwd=state.cwd,
        branch=state.branch,
        session_label=lambda: state.session_label,
        thinking_level=lambda: None,
        running=lambda: state.running,
    )


_NEUTRAL_SURFACE_SCENARIOS = surface_scenarios(
    CODING_SCENARIO_FACTORY,
    CODING_SCENARIO_FRAME_CONTRACTS,
)

SURFACE_SCENARIOS = (
    *_NEUTRAL_SURFACE_SCENARIOS[:1],
    ScreenPlaybackScenarioSpec(
        name="command-palette-select",
        description="Search the screen command palette and insert the selected command.",
        run=_run_command_palette_select,
        tags=("command", "surface"),
    ),
    ScreenPlaybackScenarioSpec(
        name="command-palette-session-command",
        description="Select a session command from the screen command palette without executing it.",
        run=_run_command_palette_session_command,
        tags=("command", "surface", "session"),
    ),
    ScreenPlaybackScenarioSpec(
        name="commands-info-surface",
        description="Open and close the screen commands info surface through the local command path.",
        run=_run_commands_info_surface,
        tags=("command", "surface"),
    ),
    ScreenPlaybackScenarioSpec(
        name="commands-info-session-command",
        description="Show session commands in the screen commands info surface without executing them.",
        run=_run_commands_info_session_command,
        tags=("command", "surface", "session"),
    ),
    ScreenPlaybackScenarioSpec(
        name="settings-search",
        description="Search the settings page opened through the screen command path.",
        run=_run_settings_search,
    ),
    ScreenPlaybackScenarioSpec(
        name="model-select",
        description="Open the screen model selector and switch models without clearing the screen.",
        run=_run_model_select,
    ),
    ScreenPlaybackScenarioSpec(
        name="model-select-search",
        description="Search the screen model selector and select the filtered model.",
        run=_run_model_select_search,
    ),
    ScreenPlaybackScenarioSpec(
        name="approval-surface",
        description="Approve an active screen approval surface and verify its callback payload.",
        run=_run_approval_surface,
    ),
    ScreenPlaybackScenarioSpec(
        name="approval-session-surface",
        description="Retain a Policy-admitted approval for the active session.",
        run=_run_approval_session_surface,
    ),
    ScreenPlaybackScenarioSpec(
        name="approval-reject-surface",
        description="Reject an active screen approval surface and verify its callback payload.",
        run=_run_approval_reject_surface,
    ),
    ScreenPlaybackScenarioSpec(
        name="dialog-surface",
        description="Confirm an active screen dialog surface without repainting the screen.",
        run=_run_dialog_surface,
    ),
    *_NEUTRAL_SURFACE_SCENARIOS[1:],
)


__all__ = ["SURFACE_SCENARIOS"]
