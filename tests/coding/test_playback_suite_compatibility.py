from loushang.coding.ui import playback_suite as coding_playback_suite
from loushang.tui import playback_suite as tui_playback_suite


def test_coding_playback_suite_reexports_tui_objects_by_identity() -> None:
    assert (
        coding_playback_suite.ScreenPlaybackScenarioResult
        is tui_playback_suite.PlaybackScenarioResult
    )
    assert (
        coding_playback_suite.ScreenPlaybackScenarioSpec
        is tui_playback_suite.PlaybackScenarioSpec
    )
    assert coding_playback_suite.ScreenPlaybackSuite is tui_playback_suite.PlaybackSuite
    assert coding_playback_suite.normalized_tags is tui_playback_suite.normalized_tags
    assert (
        coding_playback_suite.run_playback_scenarios
        is tui_playback_suite.run_playback_scenarios
    )
