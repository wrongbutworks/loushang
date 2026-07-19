from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


def test_importing_coding_ui_state_does_not_load_tui_mode_entrypoint() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib
import sys

importlib.import_module("loushang.coding.ui.screen_state")

assert "loushang.coding.ui.mode" not in sys.modules
assert "loushang.coding.ui.plain_renderer" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


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
    adapter = Path(
        "src/loushang/coding/ui/conversation_event_adapter.py"
    ).read_text(encoding="utf-8")
    assert 'event.get("type")' in adapter

    for path in (
        Path("src/loushang/coding/ui/plain_events.py"),
        Path("src/loushang/coding/ui/screen_events.py"),
    ):
        assert 'event.get("type")' not in path.read_text(encoding="utf-8")


def test_coding_ui_playback_modules_are_compatibility_facades() -> None:
    facade_functions = {
        Path("src/loushang/coding/ui/playback.py"): {"__getattr__", "__dir__"},
        Path("src/loushang/coding/ui/playback_fakes.py"): set(),
        Path("src/loushang/coding/ui/playback_runner.py"): {"main"},
        Path("src/loushang/coding/ui/playback_suite.py"): set(),
    }
    implementation_imports = {
        Path("src/loushang/coding/ui/playback.py"): (
            "loushang.coding.testing.tui.playback"
        ),
        Path("src/loushang/coding/ui/playback_fakes.py"): (
            "loushang.coding.testing.tui.fakes"
        ),
        Path("src/loushang/coding/ui/playback_runner.py"): (
            "loushang.coding.testing.tui.runner"
        ),
        Path("src/loushang/coding/ui/playback_suite.py"): "loushang.tui.playback_suite",
    }

    offenders: list[str] = []
    for path, allowed_functions in facade_functions.items():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        unexpected = definitions - allowed_functions
        offenders.extend(f"{path}:{name}" for name in sorted(unexpected))
        if implementation_imports[path] not in source:
            offenders.append(f"{path}:missing implementation facade import")

    scenario_root = Path("src/loushang/coding/ui/playback_scenarios")
    for path in sorted(scenario_root.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        offenders.extend(f"{path}:{name}" for name in definitions)
        if path.name != "__init__.py":
            owner = f"loushang.coding.testing.tui.scenarios.{path.stem}"
            if owner not in source:
                offenders.append(f"{path}:missing {owner} facade import")

    assert offenders == []


def test_coding_ui_perf_probe_is_a_compatibility_facade() -> None:
    path = Path("src/loushang/coding/ui/perf_probe.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert definitions == []
    assert "loushang.harnesstui.testing.performance" in source
    assert "loushang.coding.testing.tui.performance" in source


def test_coding_transcript_style_is_a_compatibility_facade() -> None:
    path = Path("src/loushang/coding/ui/transcript_style.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert definitions == []
    assert "loushang.harnesstui.conversation.transcript_style" in source


def test_shared_transcript_style_does_not_own_screen_product_policy() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/transcript_style.py"
    ).read_text(encoding="utf-8")
    screen = Path("src/loushang/coding/ui/screen_app.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "loushang.coding",
        "ScreenCodingTuiApp",
        "_coding_line",
        "_coding_lines",
        "_compact_display_paths",
        "collapse_tool_output_preview",
        "DEFAULT_TOOL_OUTPUT_PREVIEW_LINES",
        "bright_cyan",
    ):
        assert token not in shared

    assert "_coding_line" in screen
    assert "_coding_lines" in screen
    assert "_compact_display_paths" in screen
    assert "collapse_tool_output_preview" in screen
    assert '"transcript.tool.marker": {"color": "bright_cyan"' in screen


def test_shared_performance_probe_does_not_load_coding_sessions() -> None:
    shared = Path(
        "src/loushang/harnesstui/testing/performance.py"
    ).read_text(encoding="utf-8")
    coding = Path(
        "src/loushang/coding/testing/tui/performance.py"
    ).read_text(encoding="utf-8")

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
    assert "load_session_history_records" in coding


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

    budgets = Path(
        "src/loushang/coding/testing/tui/scenarios/budgets.py"
    ).read_text(encoding="utf-8")
    binding = Path(
        "src/loushang/coding/testing/tui/scenario_binding.py"
    ).read_text(encoding="utf-8")
    product = Path(
        "src/loushang/coding/testing/tui/scenarios/product.py"
    ).read_text(encoding="utf-8")

    assert "INTERACTION_FRAME_BUDGET" in budgets
    assert "LONG_TRANSCRIPT_FRAME_BUDGET" in budgets
    assert "Conversation interrupted" in binding
    assert "Operation aborted" in binding
    assert "PRODUCT_COMPOSED_FRAME_BUDGET" in product
    assert "PRODUCT_STREAMING_CONTROL_FRAME_BUDGET" in product


def test_shared_interaction_types_are_not_redefined_in_coding_ui() -> None:
    moved_definitions = {
        Path("src/loushang/coding/ui/lifecycle.py"): ("class RunLifecycle",),
        Path("src/loushang/coding/ui/model_list.py"): ("class ModelChoice",),
        Path("src/loushang/coding/ui/prompt_dispatch.py"): (
            "class PromptDispatchOutcome",
        ),
        Path("src/loushang/coding/ui/run_context.py"): (
            "def _stable_emit_factory",
        ),
        Path("src/loushang/coding/ui/screen_loop.py"): (
            "async def _finish_active_task",
            "def _write_startup_welcome",
            "def _configure_runtime_for_terminal_context",
            "def _elapsed_since",
            "def _pop_interrupt_pending_steer",
            "async def _run_surface_intent_handler",
            "async def _maybe_await",
            "def _supports_keyword",
            "def _terminal_size",
        ),
        Path("src/loushang/coding/ui/screen_app.py"): (
            "def _trim_records_to_line_budget",
            "def _record_logical_line_count",
            "def _text_line_count",
            "def _tail_trim_record",
            "def _tail_trim_tool_record",
            "def _tail_trim_text",
        ),
        Path("src/loushang/coding/ui/settings_common.py"): ("class ConfigRow",),
        Path("src/loushang/coding/ui/settings_config.py"): (
            "class ConfigSettingsPage",
        ),
        Path("src/loushang/coding/ui/settings_page.py"): (
            "class ModelPage",
            "class StaticLinesPage",
        ),
        Path("src/loushang/coding/ui/settings_status_line.py"): (
            "class StatusLineSettingsPage",
        ),
        Path("src/loushang/coding/ui/plain_toolbar.py"): (
            "class PlainToolbarSnapshot",
            "def render_plain_toolbar",
        ),
        Path("src/loushang/coding/ui/plain_renderer.py"): (
            "def render_user",
            "def render_assistant",
            "def render_tool_block",
            "def render_transcript",
        ),
        Path("src/loushang/coding/ui/plain_events.py"): (
            "class _PlainProjectionTarget",
            "class PlainConversationProjectionTarget",
        ),
        Path("src/loushang/coding/ui/pending_queue.py"): (
            "def pending_queue_view",
            "def session_pending_messages",
            "def cleared_queue_messages",
            "def restore_queued_messages",
        ),
        Path("src/loushang/coding/ui/screen_state.py"): (
            "class ScreenCodingTuiState",
            "class ScreenTranscriptWindow",
        ),
        Path("src/loushang/coding/ui/status_provider.py"): (
            "class CodingTuiStatusProvider",
            "class StatusSnapshot",
        ),
        Path("src/loushang/coding/ui/steer.py"): ("class SteerHandler",),
        Path("src/loushang/coding/ui/transcript_source.py"): (
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


def test_shared_conversation_interaction_does_not_own_coding_policy_or_copy() -> (
    None
):
    shared = "\n".join(
        Path(f"src/loushang/harnesstui/conversation/{module}.py").read_text(
            encoding="utf-8"
        )
        for module in ("control", "dispatch", "input", "run_context", "screen_runner")
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

    follow_up = Path("src/loushang/coding/ui/follow_up_queue.py").read_text(
        encoding="utf-8"
    )
    screen_loop = Path("src/loushang/coding/ui/screen_loop.py").read_text(
        encoding="utf-8"
    )
    screen_input = Path("src/loushang/coding/ui/screen_input.py").read_text(
        encoding="utf-8"
    )
    prompt_dispatch = Path(
        "src/loushang/coding/ui/prompt_dispatch.py"
    ).read_text(encoding="utf-8")

    assert "Follow-up is only available while a run is active." in follow_up
    assert "Follow-up queued." in follow_up
    assert (
        "Conversation interrupted - tell the model what to do differently."
        in screen_loop
    )
    assert "Operation aborted" in screen_loop
    assert "ImagePart" in screen_input
    assert 'Path(self.app.cwd) / ".loushang" / "clipboard"' in screen_input
    assert "PromptIntent" in prompt_dispatch
    assert "BashIntent" in prompt_dispatch


def test_shared_surface_controller_does_not_own_coding_policy_or_copy() -> None:
    shared = Path(
        "src/loushang/harnesstui/surface/controller.py"
    ).read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/screen_surfaces.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "CodingCommandCatalog",
        "SettingsPageView",
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
    target = Path(
        "src/loushang/harnesstui/conversation/plain_target.py"
    ).read_text(encoding="utf-8")

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


def test_shared_screen_projection_target_does_not_own_coding_policy_or_copy() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/screen_target.py"
    ).read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/screen_events.py").read_text(
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
    assert "ScreenConversationProjectionTarget" in coding
    assert "tool_title_resolver=_tool_title" in coding
    assert "tool_record_projector=tool_block_to_record" in coding
    assert "retry {attempt}/{max_attempts}" in coding
    assert "compact start:" in coding
    assert "compact error:" in coding
    assert 'return "compact done"' in coding


def test_shared_window_budget_does_not_own_screen_runtime_policy() -> None:
    shared = Path(
        "src/loushang/harnesstui/conversation/window_budget.py"
    ).read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(
        encoding="utf-8"
    )

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
    assert "transcript_window_trimmed:active_line_budget" in coding
    assert "trim_records_to_line_budget" in coding


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
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
