from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields, is_dataclass
from types import ModuleType

import pytest

from loushang.coding.testing.tui import fakes as testing_fakes
from loushang.coding.testing.tui import playback as testing_playback
from loushang.coding.testing.tui import runner as testing_runner
from loushang.coding.testing.tui.scenarios import budgets as testing_budgets
from loushang.coding.testing.tui.scenarios import command as testing_command
from loushang.coding.testing.tui.scenarios import composer as testing_composer
from loushang.coding.testing.tui.scenarios import lifecycle as testing_lifecycle
from loushang.coding.testing.tui.scenarios import product as testing_product
from loushang.coding.testing.tui.scenarios import surface as testing_surface
from loushang.coding.testing.tui.scenarios import terminal as testing_terminal
from loushang.coding.testing.tui.scenarios import transcript as testing_transcript
from loushang.coding.ui import playback as legacy_playback
from loushang.coding.ui import playback_fakes as legacy_fakes
from loushang.coding.ui import playback_runner as legacy_runner
from loushang.coding.ui.playback_scenarios import budgets as legacy_budgets
from loushang.coding.ui.playback_scenarios import command as legacy_command
from loushang.coding.ui.playback_scenarios import composer as legacy_composer
from loushang.coding.ui.playback_scenarios import lifecycle as legacy_lifecycle
from loushang.coding.ui.playback_scenarios import product as legacy_product
from loushang.coding.ui.playback_scenarios import surface as legacy_surface
from loushang.coding.ui.playback_scenarios import terminal as legacy_terminal
from loushang.coding.ui.playback_scenarios import transcript as legacy_transcript


def test_legacy_playback_facades_reexport_testing_objects_by_identity() -> None:
    _assert_same_symbols(
        legacy_playback,
        testing_playback,
        (
            "ScreenTuiAbortHandler",
            "ScreenTuiHandler",
            "ScreenTuiInputPlayback",
            "ScreenTuiInputPlaybackResult",
            "ScreenTuiInputScenario",
            "ScreenTuiLoopArtifacts",
            "ScreenTuiLoopPlayback",
            "ScreenTuiLoopPlaybackResult",
            "ScreenTuiLoopScenario",
            "ScreenTuiScenario",
        ),
    )
    _assert_same_symbols(
        legacy_fakes,
        testing_fakes,
        (
            "AppleShiftEnterTerminalContext",
            "ModelPlaybackSession",
            "RecordingTerminalContext",
            "RecordingTerminalMode",
            "SessionCommandPlaybackSession",
            "recording_drain",
        ),
    )
    _assert_same_symbols(
        legacy_runner,
        testing_runner,
        (
            "DEFAULT_SUITE",
            "ScreenPlaybackScenarioResult",
            "ScreenPlaybackScenarioSpec",
            "ScreenPlaybackSuite",
            "run_playback_cli",
            "run_playback_scenarios",
        ),
    )


def test_legacy_scenario_facades_reexport_testing_objects_by_identity() -> None:
    module_symbols = (
        (
            legacy_budgets,
            testing_budgets,
            ("INTERACTION_FRAME_BUDGET", "LONG_TRANSCRIPT_FRAME_BUDGET"),
        ),
        (legacy_command, testing_command, ("COMMAND_ROUTING_SCENARIOS",)),
        (legacy_composer, testing_composer, ("COMPOSER_SCENARIOS",)),
        (legacy_lifecycle, testing_lifecycle, ("LIFECYCLE_SCENARIOS",)),
        (
            legacy_product,
            testing_product,
            (
                "PRODUCT_COMPOSED_FRAME_BUDGET",
                "PRODUCT_SCENARIOS",
                "PRODUCT_STREAMING_CONTROL_FRAME_BUDGET",
            ),
        ),
        (legacy_surface, testing_surface, ("SURFACE_SCENARIOS",)),
        (legacy_terminal, testing_terminal, ("TERMINAL_SCENARIOS",)),
        (legacy_transcript, testing_transcript, ("TRANSCRIPT_SCENARIOS",)),
    )
    for legacy_module, testing_module, names in module_symbols:
        _assert_same_symbols(legacy_module, testing_module, names)


def test_legacy_playback_runner_module_cli_remains_executable() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "loushang.coding.ui.playback_runner",
            "completion-tab",
            "--json",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert [result["name"] for result in payload["results"]] == ["completion-tab"]


def test_screen_tui_result_constructors_and_default_artifact_names_remain_compatible(
    tmp_path,
) -> None:
    scenario = testing_playback.ScreenTuiScenario()
    input_result = testing_playback.ScreenTuiInputPlaybackResult(
        (), scenario.port, (), (), (), scenario.app
    )
    loop_result = testing_playback.ScreenTuiLoopPlaybackResult(
        0, "terminal output", scenario.app
    )

    assert input_result.step_coding_states == ()
    assert loop_result.exit_code == 0

    with pytest.raises(AssertionError):
        with loop_result.write_artifacts_on_failure(tmp_path):
            raise AssertionError("write default Coding artifact names")

    assert (tmp_path / "screen-loop-raw.txt").is_file()
    assert (tmp_path / "screen-loop-text.txt").is_file()
    assert (tmp_path / "screen-loop-state.json").is_file()


def test_screen_tui_loop_playback_and_artifacts_remain_coding_dataclasses() -> None:
    assert is_dataclass(testing_playback.ScreenTuiLoopPlayback)
    assert [field.name for field in fields(testing_playback.ScreenTuiLoopPlayback)] == [
        "width",
        "height",
        "model_label",
        "cwd",
        "branch",
        "session_label",
        "now",
        "app",
    ]
    assert testing_playback.ScreenTuiLoopArtifacts.__name__ == "ScreenTuiLoopArtifacts"


def _assert_same_symbols(
    legacy_module: ModuleType,
    testing_module: ModuleType,
    names: tuple[str, ...],
) -> None:
    for name in names:
        assert getattr(legacy_module, name) is getattr(testing_module, name)
