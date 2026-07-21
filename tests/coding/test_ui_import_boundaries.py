from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

RETIRED_CODING_UI_COMPATIBILITY_MODULES: dict[str, tuple[str, ...]] = {
    "loushang.coding.commands.tui": (
        "loushang.coding.commands.catalog",
        "loushang.harnesstui.commands.interaction",
        "loushang.harnesstui.commands.presentation",
        "loushang.harnesstui.commands.source",
    ),
    "loushang.coding.presentation.tui.runtime": (
        "loushang.coding.ui.mode",
        "loushang.harnesstui.conversation.runtime_view",
    ),
    "loushang.coding.presentation.settings": (
        "loushang.harnesstui.settings.schema",
        "loushang.coding.interaction.settings_profile",
    ),
    "loushang.coding.interaction.plain_abort": (
        "loushang.harnesstui.conversation.control",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.interaction.plain_dispatch": (
        "loushang.harnesstui.conversation.dispatch",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.interaction.plain_follow_up": (
        "loushang.harnesstui.conversation.control",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.interaction.plain_host": (
        "loushang.harnesstui.conversation.host",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.interaction.plain_result": (
        "loushang.harnesstui.conversation.dispatch",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.interaction.routing": (
        "loushang.harnesstui.conversation.host",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.ui.lifecycle": ("loushang.harnesstui.conversation.control",),
    "loushang.coding.ui.event_stream": ("loushang.harnesstui.conversation.dispatch",),
    "loushang.coding.ui.pending_queue": ("loushang.harnesstui.conversation.queue",),
    "loushang.coding.ui.perf_probe": (
        "loushang.harnesstui.testing.performance",
        "loushang.coding.presentation.tui.history",
    ),
    "loushang.coding.ui.plain_toolbar": ("loushang.harnesstui.status.plain",),
    "loushang.coding.ui.run_context": ("loushang.harnesstui.conversation.run_context",),
    "loushang.coding.ui.screen_loop": (
        "loushang.harnesstui.conversation.host",
        "loushang.harnesstui.conversation.screen_runner",
        "loushang.coding.ui.screen_input",
    ),
    "loushang.coding.ui.playback": ("tests.coding.tui_support.playback",),
    "loushang.coding.ui.playback_fakes": ("tests.coding.tui_support.fakes",),
    "loushang.coding.ui.playback_runner": ("tests.coding.tui_support.runner",),
    "loushang.coding.ui.playback_suite": ("loushang.tui.playback_suite",),
    "loushang.coding.ui.playback_scenarios": ("tests.coding.tui_support.scenarios",),
    "loushang.coding.ui.playback_scenarios.budgets": (
        "tests.coding.tui_support.scenarios.budgets",
    ),
    "loushang.coding.ui.playback_scenarios.command": (
        "tests.coding.tui_support.scenarios.command",
    ),
    "loushang.coding.ui.playback_scenarios.composer": (
        "tests.coding.tui_support.scenarios.composer",
    ),
    "loushang.coding.ui.playback_scenarios.lifecycle": (
        "tests.coding.tui_support.scenarios.lifecycle",
    ),
    "loushang.coding.ui.playback_scenarios.product": (
        "tests.coding.tui_support.scenarios.product",
    ),
    "loushang.coding.ui.playback_scenarios.surface": (
        "tests.coding.tui_support.scenarios.surface",
    ),
    "loushang.coding.ui.playback_scenarios.terminal": (
        "tests.coding.tui_support.scenarios.terminal",
    ),
    "loushang.coding.ui.playback_scenarios.transcript": (
        "tests.coding.tui_support.scenarios.transcript",
    ),
    "loushang.coding.ui.screen_state": (
        "loushang.harnesstui.conversation.screen_state",
    ),
    "loushang.coding.ui.settings_common": ("loushang.tui.settings",),
    "loushang.coding.ui.settings_status_line": ("loushang.harnesstui.status.settings",),
    "loushang.coding.ui.status_line": ("loushang.harnesstui.status.line",),
    "loushang.coding.ui.steer": ("loushang.harnesstui.conversation.control",),
    "loushang.coding.ui.transcript_reader": (
        "loushang.harnesstui.conversation.reader",
    ),
    "loushang.coding.ui.transcript_style": (
        "loushang.harnesstui.conversation.transcript_style",
    ),
}

MOVED_CODING_UI_PRODUCT_MODULES: dict[str, tuple[str, ...]] = {
    "loushang.coding.ui.abort": (
        "loushang.harnesstui.conversation.control",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.ui.command_list": (
        "loushang.coding.commands.catalog",
        "loushang.harnesstui.commands.interaction",
        "loushang.harnesstui.commands.presentation",
        "loushang.harnesstui.commands.source",
    ),
    "loushang.coding.ui.conversation_event_adapter": (
        "loushang.coding.presentation.tui.events",
    ),
    "loushang.coding.ui.controller": ("loushang.coding.interaction.controller",),
    "loushang.coding.ui.debug_status": ("loushang.coding.diagnostics.debug_status",),
    "loushang.coding.ui.debug_command": (
        "loushang.harnesstui.conversation.debug_action",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.ui.event_policy": ("loushang.coding.event.presentation_policy",),
    "loushang.coding.ui.intent": ("loushang.coding.interaction.intent",),
    "loushang.coding.ui.follow_up_queue": (
        "loushang.harnesstui.conversation.control",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.ui.handlers": (
        "loushang.harnesstui.conversation.host",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.ui.model": ("loushang.coding.model_selection",),
    "loushang.coding.ui.model_list": ("loushang.coding.model_selection_tui",),
    "loushang.coding.ui.plain_events": ("loushang.coding.presentation.tui.plain",),
    "loushang.coding.ui.plain_renderer": ("loushang.coding.presentation.tui.plain",),
    "loushang.coding.ui.prompt_dispatch": (
        "loushang.harnesstui.conversation.dispatch",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.ui.prompt_result": (
        "loushang.harnesstui.conversation.dispatch",
        "loushang.coding.ui.plain_app",
    ),
    "loushang.coding.ui.prompt_routing": (
        "loushang.harnesstui.conversation.host",
        "loushang.coding.interaction.tui_profile",
    ),
    "loushang.coding.ui.session_view": ("loushang.coding.presentation.session",),
    "loushang.coding.ui.screen_events": ("loushang.coding.presentation.tui.screen",),
    "loushang.coding.ui.session_history": ("loushang.coding.presentation.tui.history",),
    "loushang.coding.ui.settings_config": (
        "loushang.coding.interaction.settings_profile",
        "loushang.harnesstui.settings.workflow",
    ),
    "loushang.coding.ui.status_provider": (
        "loushang.harnesstui.status.persistence",
        "loushang.harnesstui.status.provider",
        "loushang.harnesstui.status.snapshot",
    ),
    "loushang.coding.ui.tool_blocks": (
        "loushang.coding.presentation.tui.tool_transcript",
    ),
    "loushang.coding.ui.transcript_projection": (
        "loushang.coding.presentation.tui.tool_transcript",
    ),
    "loushang.coding.ui.transcript_source": (
        "loushang.coding.presentation.tui.history",
    ),
}

RETIRED_CODING_UI_MODULES = {
    **RETIRED_CODING_UI_COMPATIBILITY_MODULES,
    **MOVED_CODING_UI_PRODUCT_MODULES,
}

RETAINED_CODING_UI_PRODUCT_ADAPTER_MODULES = {
    "cli",
    "completion",
    "hotkeys",
    "mode",
    "plain_app",
    "screen_app",
    "screen_input",
    "screen_surfaces",
    "settings_page",
    "startup",
}

NON_UI_CODING_OWNERS = (
    "loushang.coding.model_selection",
    "loushang.coding.diagnostics.debug_status",
    "loushang.coding.event.presentation_policy",
    "loushang.coding.interaction.intent",
    "loushang.coding.presentation.session",
)

CODING_TUI_FEATURE_OWNERS = (
    "loushang.coding.interaction.controller",
    "loushang.coding.interaction.screen_host",
    "loushang.coding.interaction.settings_profile",
    "loushang.coding.interaction.tui_profile",
    "loushang.coding.model_selection_tui",
    "loushang.coding.policy.tui",
    "loushang.coding.presentation.resume",
    "loushang.coding.presentation.tui.events",
    "loushang.coding.presentation.tui.history",
    "loushang.coding.presentation.tui.plain",
    "loushang.coding.presentation.tui.screen",
    "loushang.coding.presentation.tui.tool_transcript",
)


def test_importing_shared_screen_state_does_not_load_coding_ui() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib
import sys

importlib.import_module("loushang.harnesstui.conversation.screen_state")

assert "loushang.coding.ui" not in sys.modules
assert "loushang.coding.ui.mode" not in sys.modules
assert "loushang.coding.presentation.tui.plain" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


def test_retired_coding_ui_modules_use_canonical_owners() -> None:
    for module in RETIRED_CODING_UI_MODULES:
        relative = Path(*module.split("."))
        module_path = Path("src") / relative.with_suffix(".py")
        package_path = Path("src") / relative / "__init__.py"
        assert not module_path.exists(), module
        assert not package_path.exists(), module

    canonical_modules = tuple(
        sorted(
            {owner for owners in RETIRED_CODING_UI_MODULES.values() for owner in owners}
        )
    )
    result = _run_python_import_boundary_check(
        f"""
import importlib.util

canonical = {canonical_modules!r}

for module in canonical:
    assert importlib.util.find_spec(module) is not None, module
"""
    )

    assert result.returncode == 0, result.stderr


def test_coding_ui_module_manifest_contains_only_product_adapters() -> None:
    root = Path("src/loushang/coding/ui")
    actual: set[str] = set()
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if relative.name == "__init__.py":
            if relative.parent != Path("."):
                actual.add(".".join(relative.parent.parts))
            continue
        actual.add(".".join(relative.with_suffix("").parts))

    assert actual == RETAINED_CODING_UI_PRODUCT_ADAPTER_MODULES


def test_coding_ui_package_stays_within_the_product_adapter_budget() -> None:
    root = Path("src/loushang/coding/ui")
    line_counts = {
        path.relative_to(root).as_posix(): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in sorted(root.rglob("*.py"))
    }

    assert sum(line_counts.values()) <= 2_200, line_counts
    assert line_counts["mode.py"] <= 350


def test_repository_imports_use_canonical_owners_for_retired_modules() -> None:
    retired = tuple(RETIRED_CODING_UI_MODULES)
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples"), Path("scripts")):
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == Path(__file__).resolve():
                continue
            for target in _absolute_import_targets(path):
                matched = next(
                    (
                        module
                        for module in retired
                        if target == module or target.startswith(f"{module}.")
                    ),
                    None,
                )
                if matched is not None:
                    offenders.append(f"{path}:{target} -> {matched}")

    assert offenders == []


def test_coding_tui_testing_package_is_extinct() -> None:
    root = Path("src/loushang/coding/testing") / "tui"
    assert not tuple(root.rglob("*.py"))

    retired_prefix = ".".join(("loushang", "coding", "testing", "tui"))
    offenders: list[str] = []
    for root in (Path("src"), Path("tests"), Path("examples"), Path("scripts")):
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == Path(__file__).resolve():
                continue
            for target in _absolute_import_targets(path):
                if target == retired_prefix or target.startswith(f"{retired_prefix}."):
                    offenders.append(f"{path}:{target}")

    assert offenders == []


def test_non_ui_coding_owners_do_not_depend_on_ui_layers() -> None:
    modules = tuple(
        Path("src", *module.split(".")).with_suffix(".py")
        for module in NON_UI_CODING_OWNERS
    )
    forbidden = (
        "loushang.coding.ui",
        "loushang.harnesstui",
        "loushang.tui",
    )

    offenders = [
        f"{path}:{target}"
        for path in modules
        for target in _absolute_import_targets(path)
        if target.startswith(forbidden)
    ]

    assert offenders == []


def test_importing_non_ui_coding_owners_does_not_load_ui_layers() -> None:
    result = _run_python_import_boundary_check(
        f"""
import importlib
import sys

for module in {NON_UI_CODING_OWNERS!r}:
    importlib.import_module(module)

for module in sys.modules:
    assert module != "loushang.coding.ui" and not module.startswith("loushang.coding.ui."), module
    assert module != "loushang.harnesstui" and not module.startswith("loushang.harnesstui."), module
    assert module != "loushang.tui" and not module.startswith("loushang.tui."), module
"""
    )

    assert result.returncode == 0, result.stderr


def test_feature_local_coding_tui_owners_do_not_depend_on_coding_ui() -> None:
    modules = tuple(
        Path("src", *module.split(".")).with_suffix(".py")
        for module in CODING_TUI_FEATURE_OWNERS
    )
    offenders = [
        f"{path}:{target}"
        for path in modules
        for target in _absolute_import_targets(path)
        if target.startswith("loushang.coding.ui")
    ]
    assert offenders == []

    result = _run_python_import_boundary_check(
        f"""
import importlib
import sys

for module in {CODING_TUI_FEATURE_OWNERS!r}:
    importlib.import_module(module)

for module in sys.modules:
    assert module != "loushang.coding.ui" and not module.startswith("loushang.coding.ui."), module
"""
    )
    assert result.returncode == 0, result.stderr


def test_mode_is_only_the_coding_tui_composition_root() -> None:
    source = Path("src/loushang/coding/ui/mode.py").read_text(encoding="utf-8")

    for token in (
        "set_approval_presenter",
        "get_session_file",
        "inspect.signature",
        "base64",
        "traceback",
        "def _is_interactive",
    ):
        assert token not in source

    for token in (
        "ScreenCodingConversationActionHost",
        "build_screen_coding_event_projection",
        "build_plain_coding_event_projection",
        "ScreenSurfaceManager",
        "run_action_host_conversation_screen",
        "CODING_SCREEN_RUN_PROFILE",
        "build_plain_coding_tui_app",
        "PreparedScreenConversationRun",
        "run_prepared_screen_conversation",
        "PreparedPlainConversationRun",
        "run_prepared_plain_conversation",
        "TuiLaunchProfile",
        "run_tui_launch_shell",
        "class _CodingTuiSessionPort",
        "get_tool_definition",
        "get_steering_messages",
        "get_follow_up_messages",
        "get_keybindings",
        "stable_string_queue_reader",
    ):
        assert token in source

    assert "ScreenCodingEventProjector" not in source
    assert "PlainCodingEventRenderer" not in source


def test_prepared_application_host_owns_only_neutral_run_coordination() -> None:
    shared = Path("src/loushang/harnesstui/conversation/application_host.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/ui/mode.py").read_text(encoding="utf-8")

    for token in (
        "loushang.coding",
        "ScreenCodingTuiApp",
        "CodingUiController",
        "ScreenSurfaceManager",
        "StatusProvider",
        "handle_screen_approval",
        "model_label",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "PreparedScreenConversationRun",
        "run_prepared_screen_conversation",
        "PreparedPlainConversationRun",
        "run_prepared_plain_conversation",
    ):
        assert token in shared
        assert token in coding


def test_plain_prompt_host_owns_only_neutral_turn_lifecycle() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/plain_prompt_host.py"
    ).read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/prompt_command.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "ensure_usable_session_model",
        "CodingWorkShell",
        "EventLogBackend",
        "_last_assistant_failure_message",
        "method_id",
        "plan_id",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "PlainPromptHostPorts",
        "PreparedPlainPromptRun",
        "run_plain_prompt_host",
    ):
        assert token in shared
        assert token in coding

    assert "def _run_turn" not in coding


def test_shared_resume_runtime_and_startup_keep_product_policy_outside() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in ("resume", "runtime_view", "startup")
    )
    coding = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "src/loushang/coding/presentation/resume.py",
            "src/loushang/coding/ui/startup.py",
            "src/loushang/coding/ui/mode.py",
        )
    )
    assert not Path("src/loushang/coding/presentation/tui/runtime.py").exists()

    for token in (
        "loushang.coding",
        "ensure_usable_session_model",
        "get_session_model_selection",
        "get_steering_messages",
        "get_follow_up_messages",
        "Resume this session with:",
        "session_manager",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "ConversationResumeHint",
        "write_clean_exit_resume_hint",
        "stable_string_queue_reader",
        "build_conversation_startup_view",
    ):
        assert token in shared
        assert token in coding


def test_generic_tui_launch_shell_does_not_own_product_or_harness_policy() -> None:
    shared = Path("src/loushang/tui/launch.py").read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/mode.py").read_text(encoding="utf-8")

    for token in (
        "loushang.coding",
        "loushang.harness",
        "loushang.harnesstui",
        "runtime",
        "session",
        "ScreenCodingTuiApp",
        "■ Error: ",
    ):
        assert token not in shared

    assert "TuiLaunchProfile" in coding
    assert "run_tui_launch_shell" in coding
    assert 'error_prefix="■ Error: "' in coding


def test_old_coding_ui_renderer_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.renderer")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.renderer should be named plain_renderer")
"""
    )

    assert result.returncode == 0, result.stderr


def test_old_coding_ui_events_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.events")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.events should be named plain_events")
"""
    )

    assert result.returncode == 0, result.stderr


def test_conversation_raw_event_dispatch_stays_in_coding_adapter() -> None:
    adapter = Path("src/loushang/coding/presentation/tui/events.py").read_text(
        encoding="utf-8"
    )
    assert 'event.get("type")' in adapter

    for path in (
        Path("src/loushang/coding/presentation/tui/plain.py"),
        Path("src/loushang/coding/presentation/tui/screen.py"),
    ):
        assert 'event.get("type")' not in path.read_text(encoding="utf-8")


def test_shared_transcript_style_does_not_own_screen_product_policy() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in (
            "transcript_display",
            "transcript_style",
            "transcript_presentation",
        )
    )
    screen = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    for token in (
        "loushang.coding",
        "ScreenCodingTuiApp",
        "_project_coding_tool_name",
        "_project_coding_tool_output",
        "collapse_tool_output_preview",
        "DEFAULT_TOOL_OUTPUT_PREVIEW_LINES",
        "bright_cyan",
        'user_prompt_prefix="› "',
        'tool_command_prefix="  │ "',
    ):
        assert token not in shared

    assert "ConversationTranscriptCopy" in screen
    assert 'user_prompt_prefix="› "' in screen
    assert 'tool_command_prefix="  │ "' in screen
    assert "TranscriptDisplayProjectionProfile" in shared
    assert "TranscriptDisplayProjectionProfile" in screen
    assert "compact_absolute_display_paths" in shared
    assert "compact_absolute_display_paths" in screen
    assert "_compact_display_paths" not in screen
    assert "collapse_tool_output_preview" in screen
    assert '"transcript.tool.marker": {"color": "bright_cyan"' in screen


def test_shared_performance_probe_does_not_load_coding_sessions() -> None:
    shared = Path("src/loushang/harnesstui/testing/performance.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/presentation/tui/history.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "ScreenCodingTuiApp",
        "SessionManager",
        "session_history_records",
        "AgentToolResult",
        "loushang.harness",
    ):
        assert token not in shared

    assert "SessionManager" in coding
    assert "session_history_records" in coding
    assert "load_persisted_session_history_records" in coding


def test_shared_history_dispatch_keeps_raw_coding_projection_outside() -> None:
    shared = Path("src/loushang/harnesstui/conversation/history.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/presentation/tui/history.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "loushang.ai",
        "SessionManager",
        "UserMessage",
        "ToolResultMessage",
        "CodingToolTranscriptProjection",
        "TUI_TRANSCRIPT_DISPOSITIONS",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "ConversationHistoryProjector",
        "project_context_compaction_payload",
        "project_context_branch_summary_payload",
    ):
        assert token in shared
        assert token in coding

    assert "def _transcript_record" not in coding
    assert "class SessionTranscriptSource" not in coding
    assert "def _session_transcript_items" not in coding
    assert "branch_items: Iterable[object]" in coding
    assert "manager.get_branch()" in coding

    mode = Path("src/loushang/coding/ui/mode.py").read_text(encoding="utf-8")
    assert "MaterializedTranscriptSource" in mode
    assert "session_port.session_manager.get_branch()" in mode


def test_shared_playback_support_does_not_own_coding_copy_or_budgets() -> None:
    shared = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("src/loushang/harnesstui/testing").rglob("*.py"))
    )
    for token in (
        "Conversation interrupted",
        "Operation aborted",
        ".loushang",
        "INTERACTION_FRAME_BUDGET",
        "LONG_TRANSCRIPT_FRAME_BUDGET",
        "PRODUCT_COMPOSED_FRAME_BUDGET",
        "PRODUCT_STREAMING_CONTROL_FRAME_BUDGET",
    ):
        assert token not in shared

    budgets = Path("tests/coding/tui_support/scenarios/budgets.py").read_text(
        encoding="utf-8"
    )
    binding = Path("tests/coding/tui_support/scenario_binding.py").read_text(
        encoding="utf-8"
    )
    screen_profile = Path("src/loushang/coding/ui/screen_input.py").read_text(
        encoding="utf-8"
    )
    product = Path("tests/coding/tui_support/scenarios/product.py").read_text(
        encoding="utf-8"
    )

    assert "INTERACTION_FRAME_BUDGET" in budgets
    assert "LONG_TRANSCRIPT_FRAME_BUDGET" in budgets
    assert "CODING_INTERRUPTION_MESSAGE" in binding
    assert "CODING_CANCELLATION_MESSAGE" in binding
    assert "Conversation interrupted" in screen_profile
    assert "Operation aborted" in screen_profile
    assert "PRODUCT_COMPOSED_FRAME_BUDGET" in product
    assert "PRODUCT_STREAMING_CONTROL_FRAME_BUDGET" in product


def test_shared_interaction_types_are_not_redefined_in_coding_ui() -> None:
    moved_definitions = {
        Path("src/loushang/coding/model_selection_tui.py"): ("class ModelChoice",),
        Path("src/loushang/coding/ui/screen_app.py"): (
            "def _trim_records_to_line_budget",
            "def _record_logical_line_count",
            "def _text_line_count",
            "def _tail_trim_record",
            "def _tail_trim_tool_record",
            "def _tail_trim_text",
        ),
        Path("src/loushang/coding/ui/settings_page.py"): (
            "class ModelPage",
            "class SettingsPageView",
            "class StaticLinesPage",
        ),
        Path("src/loushang/coding/presentation/tui/plain.py"): (
            "def render_user",
            "def render_assistant",
            "def render_tool_block",
            "def render_transcript",
            "class _PlainProjectionTarget",
            "class PlainConversationProjectionTarget",
        ),
        Path("src/loushang/coding/presentation/tui/history.py"): (
            "class ActiveWindowTranscriptSource",
            "def _active_window_records",
            "def _recent_assistant_texts",
            "def _merge_active_window_records",
            "def _decorated_suffix_prefix_overlap",
            "def _history_projected_record",
        ),
        Path("src/loushang/coding/ui/screen_surfaces.py"): (
            "class ModelSelectorSurface",
            "class ScreenSurfaceView",
            "class SurfaceEvent",
        ),
    }

    offenders = [
        f"{path}:{definition}"
        for path, definitions in moved_definitions.items()
        for definition in definitions
        if definition in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_shared_conversation_interaction_does_not_own_coding_policy_or_copy() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in (
            "control",
            "dispatch",
            "host",
            "info",
            "input",
            "plain_app",
            "run_context",
            "screen_runner",
        )
    )

    for token in (
        "Follow-up is only available while a run is active.",
        "Follow-up queued.",
        "Conversation interrupted - tell the model what to do differently.",
        "Operation aborted",
        ".loushang/clipboard",
        "ImagePart",
        "PromptIntent",
        "BashIntent",
    ):
        assert token not in shared

    plain_app = Path("src/loushang/coding/ui/plain_app.py").read_text(encoding="utf-8")
    profile = Path("src/loushang/coding/interaction/tui_profile.py").read_text(
        encoding="utf-8"
    )
    screen_input = Path("src/loushang/coding/ui/screen_input.py").read_text(
        encoding="utf-8"
    )
    screen_host = Path("src/loushang/coding/interaction/screen_host.py").read_text(
        encoding="utf-8"
    )

    assert "Follow-up is only available while a run is active." in plain_app
    assert "Follow-up queued." in plain_app
    assert (
        "Conversation interrupted - tell the model what to do differently."
        in screen_input
    )
    assert "Operation aborted" in screen_input
    assert "ImagePart" not in screen_input
    assert "ImagePart" in screen_host
    assert '".loushang" / "clipboard"' in screen_input
    assert "class ScreenInputResult" not in screen_input
    assert "class ScreenInputRouter" not in screen_input
    assert "bind_clipboard_image_input_router(" in screen_input
    assert "PromptIntent" in profile
    assert "BashIntent" in profile
    assert "build_plain_conversation_app" in plain_app


def test_shared_action_presentation_keeps_product_controller_and_copy_outside() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/action_presentation.py"
    ).read_text(encoding="utf-8")
    result_owner = Path("src/loushang/harness/host/types.py").read_text(
        encoding="utf-8"
    )
    controller = Path("src/loushang/coding/interaction/controller.py").read_text(
        encoding="utf-8"
    )
    screen_host = Path("src/loushang/coding/interaction/screen_host.py").read_text(
        encoding="utf-8"
    )
    profile = Path("src/loushang/coding/interaction/tui_profile.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "ImagePart",
        "PromptIntent",
        "AbortIntent",
        "Request failed:",
        "Steering failed:",
        "Follow-up failed:",
    ):
        assert token not in shared

    assert "class HostActionResult" in result_owner
    assert "ConversationUiController" in controller
    assert "HostActionResult" not in controller
    assert "class ControllerResult" not in controller
    assert "ImagePart" in screen_host
    assert "PromptIntent" in screen_host
    assert "Request failed:" in profile
    assert "Steering failed:" in profile
    assert "Follow-up failed:" in profile


def test_shared_debug_action_keeps_product_binding_and_copy_outside() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/debug_action.py"
    ).read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/plain_app.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "debug_status_text",
        "Debug logging disabled.",
        '"debug.enabled"',
        '"debug.disabled"',
        "session=session",
        "cwd=cwd",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "DebugActionCopy",
        "DebugActionHandler",
        "DebugActionPorts",
    ):
        assert token in shared
        assert token in coding


def test_shared_surface_controller_does_not_own_coding_policy_or_copy() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/surface/{module}.py").read_text(encoding="utf-8")
        for module in ("controller", "workflow")
    )
    coding = Path("src/loushang/coding/ui/screen_surfaces.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "CodingCommandCatalog",
        "build_coding_settings_page",
        "ScreenCodingTuiApp",
        "select_available_model",
        "parse_prompt_intent",
        "Action confirmed:",
        "Action rejected",
        "Approval request is no longer pending",
        "Command selected:",
    ):
        assert token not in shared
        assert token in coding


def test_shared_settings_workflow_does_not_own_coding_bindings_or_copy() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/settings/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in ("schema", "workflow")
    )
    coding = Path("src/loushang/coding/interaction/settings_profile.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "terminal.progress",
        "get_show_terminal_progress",
        "set_show_terminal_progress",
        "Invalid {binding.label} value.",
        "is not available.",
    ):
        assert token not in shared
        assert token in coding


def test_shared_catalog_interactions_do_not_own_coding_policy_or_copy() -> None:
    command_interaction = Path(
        "src/loushang/harnesstui/commands/interaction.py"
    ).read_text(encoding="utf-8")
    model_interaction = Path(
        "src/loushang/harnesstui/selection/interaction.py"
    ).read_text(encoding="utf-8")
    shared = command_interaction + model_interaction
    command_adapter = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "src/loushang/coding/commands/catalog.py",
            "src/loushang/coding/ui/completion.py",
            "src/loushang/coding/ui/plain_app.py",
            "src/loushang/coding/ui/screen_surfaces.py",
        )
    )
    model_adapter = Path("src/loushang/coding/model_selection_tui.py").read_text(
        encoding="utf-8"
    )
    coding = command_adapter + model_adapter

    for token in (
        "loushang.coding",
        "CodingCommandCatalog",
        "ModelSelection",
        "apply_model_selection",
        "persistence_warning_message",
        "settings_manager",
        "set_model",
        "Command selected:",
        "Use /command <full command> to select one.",
        "Model set:",
        "Use /model <full model> to select one.",
    ):
        assert token not in shared

    for token in (
        "CodingCommandCatalog",
        "apply_model_selection",
        "persistence_warning_message",
        "settings_manager",
        "set_model",
        "Command selected:",
        "Use /command <full command> to select one.",
        "Model set:",
        "Use /model <full model> to select one.",
    ):
        assert token in coding

    assert "loushang.harnesstui.commands.interaction" in command_adapter
    assert "loushang.harnesstui.selection.interaction" in model_adapter
    assert "present_command_interaction" in command_interaction
    assert "present_model_interaction" in model_interaction
    for removed in (
        "format_session_commands",
        "session_command_completion_provider",
        "session_command_palette",
        "select_session_command",
    ):
        assert removed not in command_adapter
    assert "available_model_palette" not in model_adapter


def test_shared_command_catalog_keeps_coding_definitions_and_raw_adaptation_outside() -> None:
    shared = Path("src/loushang/harness/commands/catalog.py").read_text(
        encoding="utf-8"
    )
    descriptors = Path("src/loushang/harness/commands/descriptors.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/commands/catalog.py").read_text(
        encoding="utf-8"
    )
    profile = Path("src/loushang/harness/commands/catalog.py").read_text(
        encoding="utf-8"
    )

    assert "loushang.coding" not in shared
    assert "loushang.coding" not in descriptors

    for token in ("coding.ui.model", "coding.session.", "raw_command"):
        assert token not in shared

    for token in ("harness.ui.model", "harness.ui.config", "model_select", "terminal"):
        assert token in profile

    for token in ("coding.session.", "CommandEffectKind", "raw_command"):
        assert token in coding

    for token in ("MixedCommandCatalog", "MixedCommandCatalogPorts"):
        assert token in shared
        assert token in coding

    assert "LocalCommandCatalogProfile" in shared
    assert "LocalCommandCatalogProfile" in shared

    for token in ("CommandCatalog", "CommandDescriptor", "split_slash_command"):
        assert token in descriptors


def test_shared_model_choice_catalog_keeps_session_and_endpoint_acquisition_outside() -> None:
    shared = Path("src/loushang/harnesstui/selection/catalog.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/model_selection_tui.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "get_available_model_details",
        "get_model_selection",
        "apply_model_selection",
        "persistence_warning_message",
        'message = f"Model set:',
        "def _string_attr",
        "def _bool_attr",
    ):
        assert token not in shared
        assert token in coding

    for token in (
        "ModelChoiceIdentity",
        "resolve_current_model_choice_value",
        "merge_model_choice_sources",
    ):
        assert token in shared
        assert token in coding


def test_shared_completion_host_does_not_own_coding_catalog_or_path_policy() -> None:
    shared_path = Path("src/loushang/harnesstui/completion/host.py")
    coding_path = Path("src/loushang/coding/ui/completion.py")
    shared = shared_path.read_text(encoding="utf-8")
    coding = coding_path.read_text(encoding="utf-8")

    for token in (
        "loushang.coding",
        "Any",
        "Session",
        "ModelSelection",
        '"/model"',
        '"Models"',
        '"Quit loushang"',
    ):
        assert token not in shared

    for token in (
        "PreparedCatalogCompletionHost",
        'model_command_value="/model"',
        'model_argument_group="Models"',
        'CatalogSlashAlias("/quit", "/exit", "Quit loushang")',
        "coding_completion_host",
        "base_path=base_path",
    ):
        assert token in coding

    assert "_session_completion_base_path" not in coding
    assert len(coding.splitlines()) <= 50


def test_shared_status_provider_does_not_own_settings_manager_adaptation() -> None:
    source = Path("src/loushang/harnesstui/status/provider.py").read_text(
        encoding="utf-8"
    )

    assert "settings_manager" not in source
    assert "status_line_settings_from_control" not in source
    assert "status_line_settings_to_patch" not in source


def test_shared_plain_presentation_does_not_own_coding_policy() -> None:
    renderer = Path("src/loushang/harnesstui/plain/renderer.py").read_text(
        encoding="utf-8"
    )
    target = Path("src/loushang/harnesstui/conversation/plain_target.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "Loushang TUI",
        "/feedback",
        "PlainCoding",
        "_coding_line",
        "CodingConversationEventAdapter",
        "AgentToolResult",
    ):
        assert token not in renderer
        assert token not in target
    assert 'event.get("type")' not in renderer
    assert 'event.get("type")' not in target


def test_tool_transcript_projection_keeps_raw_coding_policy_at_product_edge() -> None:
    shared = Path("src/loushang/harnesstui/conversation/tool_transcript.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/presentation/tui/tool_transcript.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "AgentToolResult",
        "ToolDefinitionResolver",
        'event.get("tool_call_id")',
        'event.get("tool_name")',
        "render_tool_result_presentation",
    ):
        assert token not in shared
        assert token in coding

    coding_tree = ast.parse(coding)
    coding_class_names = {
        node.name for node in ast.walk(coding_tree) if isinstance(node, ast.ClassDef)
    }
    assert "ToolTranscriptProjector" not in coding_class_names
    assert "CodingToolTranscriptViewAdapter" in coding_class_names
    assert "build_coding_tool_transcript_projection" in coding
    assert "ToolTranscriptProjectionBinding" in shared
    assert "ToolTranscriptProjectionBinding" in coding


def test_shared_screen_projection_target_does_not_own_coding_policy_or_copy() -> None:
    shared = Path("src/loushang/harnesstui/conversation/screen_target.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/presentation/tui/screen.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "CodingConversationEventAdapter",
        "ScreenCodingTuiApp",
        "AgentToolResult",
        'event.get("type")',
        'verb="Ran"',
        'verb="Tested"',
        "retry {attempt}/{max_attempts}",
        "compact start:",
        "compact error:",
        'return "compact done"',
    ):
        assert token not in shared

    tree = ast.parse(coding)
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "_ScreenProjectionTarget" not in class_names
    assert "ScreenCodingEventProjector" not in class_names
    assert "ScreenConversationProjectionTarget" in shared
    assert "build_screen_conversation_projection" in shared
    assert "build_screen_conversation_projection" in coding
    assert "build_screen_coding_event_projection" in coding
    assert "tool_title_resolver=_tool_title" in coding
    assert "tool_record_projector=tool_block_to_record" in coding
    assert "retry {attempt}/{max_attempts}" in coding
    assert "compact start:" in coding
    assert "compact error:" in coding
    assert 'return "compact done"' in coding


def test_shared_window_budget_does_not_own_screen_runtime_policy() -> None:
    shared = Path("src/loushang/harnesstui/conversation/window_budget.py").read_text(
        encoding="utf-8"
    )
    screen_app = Path("src/loushang/harnesstui/conversation/screen_app.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    for token in (
        "ScreenCodingTuiApp",
        "DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET",
        "transcript_window_trimmed:active_line_budget",
        "ActiveTranscriptWindow",
        "replace_transcript_window",
        "loushang.coding",
    ):
        assert token not in shared

    assert "DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET = 320" in coding
    assert "transcript_window_trimmed:active_line_budget" in screen_app
    assert "trim_records_to_line_budget" in screen_app


def test_tui_owns_transcript_region_while_coding_owns_presentation_policy() -> None:
    from loushang.coding.ui.screen_app import ScreenCodingTuiApp
    from loushang.tui.ui_parts.transcript import TranscriptRegion

    engine = Path("src/loushang/tui/ui_parts/transcript.py").read_text(encoding="utf-8")
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in ("transcript_display", "transcript_presentation")
    )
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    assert "class _ScreenTranscriptRegion" not in coding
    for token in (
        "_project_coding_tool_name",
        "_project_coding_tool_output",
        "collapse_tool_output_preview",
        "DEFAULT_TOOL_OUTPUT_PREVIEW_LINES",
        "bright_cyan",
    ):
        assert token not in engine
        assert token not in shared
        assert token in coding
    assert "ProfiledConversationTranscriptPresentation" in shared
    assert "TranscriptDisplayProjectionProfile" in shared
    assert "TranscriptDisplayProjectionProfile" in coding
    assert "_compact_display_paths" not in coding
    assert "_CODING_TRANSCRIPT_PRESENTATION_PROFILE" in coding

    app = ScreenCodingTuiApp(
        model_label=None,
        cwd="/workspace",
        branch=None,
        session_label=None,
    )
    assert type(app._transcript_region) is TranscriptRegion


def test_shared_screen_frame_does_not_own_coding_copy() -> None:
    shared = Path("src/loushang/harnesstui/conversation/screen_frame.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    assert "loushang.coding" not in shared
    for copy in (
        "Working",
        "Messages to be submitted after next tool call",
        "Queued follow-up inputs",
    ):
        literal = f'"{copy}"'
        assert literal not in shared
        assert literal in coding


def test_shared_screen_app_does_not_own_coding_presentation_policy() -> None:
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in (
            "screen_app",
            "transcript_display",
            "transcript_presentation",
        )
    )
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    for token in (
        "ScreenCodingTuiApp",
        "LoushangWelcomePanel",
        "Compacted summary:",
        "DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET = 320",
        "collapse_tool_output_preview",
    ):
        assert token not in shared
        assert token in coding
    assert "trim_records_to_line_budget" in shared
    assert "TranscriptDisplayProjectionProfile" in shared
    assert "class ProfiledScreenConversationApp(ScreenConversationApp)" in shared
    assert "class ScreenCodingTuiApp(ProfiledScreenConversationApp)" in coding


def test_old_coding_ui_app_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.app")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.app should be named plain_app")
"""
    )

    assert result.returncode == 0, result.stderr


def test_coding_ui_does_not_depend_on_legacy_settings_list_primitives() -> None:
    forbidden = (
        "SettingItem",
        "SettingsList",
        "SettingsListRenderer",
        "SettingsSurface",
        "legacy_settings",
    )
    offenders: list[str] = []
    for path in Path("src/loushang/coding/ui").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []


def test_active_coding_ui_surfaces_do_not_use_legacy_native_product_names() -> None:
    forbidden = (
        "NativeCoding",
        "NativeSurface",
        "NativeInput",
        "Native TUI",
        "native coding TUI",
        "native event projection",
        "native/session event",
        "native terminal TUI",
        "current native TUI",
        "native `tui`",
        "native TUI runner",
        "native TUI 已",
        "native TUI 中",
        "native TUI 属于",
        "native TUI 是",
        "src/loushang/coding/ui/native_",
        "tests/coding/test_native_coding_tui",
        "native_app",
        "native_events",
        "native_input",
        "native_loop",
        "native_state",
        "native_surfaces",
        "native_tui",
        "test_native_tui",
    )
    offenders: list[str] = []
    roots = (
        Path("src/loushang/coding/ui"),
        Path("tests/coding"),
        Path("docs/internals/architecture/coding"),
        Path("docs/internals/testing"),
    )
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if "archive" in path.parts or "history" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path}:{token}")

    assert offenders == []


def _run_python_import_boundary_check(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path.cwd() / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _absolute_import_targets(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom) or node.level != 0:
            continue
        module = node.module or ""
        if module:
            targets.append(module)
        targets.extend(
            f"{module}.{alias.name}" if module else alias.name
            for alias in node.names
            if alias.name != "*"
        )
    return tuple(targets)
