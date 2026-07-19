from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

RETIRED_CODING_UI_COMPATIBILITY_MODULES: dict[str, tuple[str, ...]] = {
    "loushang.coding.ui.lifecycle": ("loushang.harnesstui.conversation.control",),
    "loushang.coding.ui.pending_queue": ("loushang.harnesstui.conversation.queue",),
    "loushang.coding.ui.perf_probe": (
        "loushang.harnesstui.testing.performance",
        "loushang.coding.testing.tui.performance",
    ),
    "loushang.coding.ui.plain_toolbar": ("loushang.harnesstui.status.plain",),
    "loushang.coding.ui.playback": ("loushang.coding.testing.tui.playback",),
    "loushang.coding.ui.playback_fakes": ("loushang.coding.testing.tui.fakes",),
    "loushang.coding.ui.playback_runner": ("loushang.coding.testing.tui.runner",),
    "loushang.coding.ui.playback_suite": ("loushang.tui.playback_suite",),
    "loushang.coding.ui.playback_scenarios": ("loushang.coding.testing.tui.scenarios",),
    "loushang.coding.ui.playback_scenarios.budgets": (
        "loushang.coding.testing.tui.scenarios.budgets",
    ),
    "loushang.coding.ui.playback_scenarios.command": (
        "loushang.coding.testing.tui.scenarios.command",
    ),
    "loushang.coding.ui.playback_scenarios.composer": (
        "loushang.coding.testing.tui.scenarios.composer",
    ),
    "loushang.coding.ui.playback_scenarios.lifecycle": (
        "loushang.coding.testing.tui.scenarios.lifecycle",
    ),
    "loushang.coding.ui.playback_scenarios.product": (
        "loushang.coding.testing.tui.scenarios.product",
    ),
    "loushang.coding.ui.playback_scenarios.surface": (
        "loushang.coding.testing.tui.scenarios.surface",
    ),
    "loushang.coding.ui.playback_scenarios.terminal": (
        "loushang.coding.testing.tui.scenarios.terminal",
    ),
    "loushang.coding.ui.playback_scenarios.transcript": (
        "loushang.coding.testing.tui.scenarios.transcript",
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
    "loushang.coding.ui.command_list": (
        "loushang.coding.commands.tui",
    ),
    "loushang.coding.ui.controller": (
        "loushang.coding.interaction.controller",
    ),
    "loushang.coding.ui.debug_status": (
        "loushang.coding.diagnostics.debug_status",
    ),
    "loushang.coding.ui.event_policy": (
        "loushang.coding.event.presentation_policy",
    ),
    "loushang.coding.ui.intent": ("loushang.coding.interaction.intent",),
    "loushang.coding.ui.model": ("loushang.coding.model_selection",),
    "loushang.coding.ui.model_list": (
        "loushang.coding.model_selection_tui",
    ),
    "loushang.coding.ui.session_view": (
        "loushang.coding.presentation.session",
    ),
    "loushang.coding.ui.settings_config": (
        "loushang.coding.presentation.settings",
        "loushang.harnesstui.settings.workflow",
    ),
    "loushang.coding.ui.status_provider": (
        "loushang.harnesstui.status.persistence",
        "loushang.harnesstui.status.provider",
        "loushang.harnesstui.status.snapshot",
    ),
}

RETIRED_CODING_UI_MODULES = {
    **RETIRED_CODING_UI_COMPATIBILITY_MODULES,
    **MOVED_CODING_UI_PRODUCT_MODULES,
}

RETAINED_CODING_UI_PRODUCT_ADAPTER_MODULES = {
    "abort",
    "cli",
    "completion",
    "conversation_event_adapter",
    "debug_command",
    "event_stream",
    "follow_up_queue",
    "handlers",
    "hotkeys",
    "mode",
    "plain_app",
    "plain_events",
    "plain_renderer",
    "prompt_dispatch",
    "prompt_result",
    "prompt_routing",
    "run_context",
    "screen_app",
    "screen_events",
    "screen_input",
    "screen_loop",
    "screen_surfaces",
    "session_history",
    "settings_page",
    "startup",
    "tool_blocks",
    "transcript_projection",
    "transcript_source",
}

NON_UI_CODING_OWNERS = (
    "loushang.coding.model_selection",
    "loushang.coding.diagnostics.debug_status",
    "loushang.coding.event.presentation_policy",
    "loushang.coding.interaction.controller",
    "loushang.coding.interaction.intent",
    "loushang.coding.presentation.session",
    "loushang.coding.presentation.settings",
)

CODING_TUI_FEATURE_OWNERS = (
    "loushang.coding.commands.tui",
    "loushang.coding.model_selection_tui",
)


def test_importing_shared_screen_state_does_not_load_coding_ui() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib
import sys

importlib.import_module("loushang.harnesstui.conversation.screen_state")

assert "loushang.coding.ui" not in sys.modules
assert "loushang.coding.ui.mode" not in sys.modules
assert "loushang.coding.ui.plain_renderer" not in sys.modules
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
            {
                owner
                for owners in RETIRED_CODING_UI_MODULES.values()
                for owner in owners
            }
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
    adapter = Path("src/loushang/coding/ui/conversation_event_adapter.py").read_text(
        encoding="utf-8"
    )
    assert 'event.get("type")' in adapter

    for path in (
        Path("src/loushang/coding/ui/plain_events.py"),
        Path("src/loushang/coding/ui/screen_events.py"),
    ):
        assert 'event.get("type")' not in path.read_text(encoding="utf-8")


def test_shared_transcript_style_does_not_own_screen_product_policy() -> None:
    shared = Path("src/loushang/harnesstui/conversation/transcript_style.py").read_text(
        encoding="utf-8"
    )
    screen = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

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
    shared = Path("src/loushang/harnesstui/testing/performance.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/testing/tui/performance.py").read_text(
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

    budgets = Path("src/loushang/coding/testing/tui/scenarios/budgets.py").read_text(
        encoding="utf-8"
    )
    binding = Path("src/loushang/coding/testing/tui/scenario_binding.py").read_text(
        encoding="utf-8"
    )
    product = Path("src/loushang/coding/testing/tui/scenarios/product.py").read_text(
        encoding="utf-8"
    )

    assert "INTERACTION_FRAME_BUDGET" in budgets
    assert "LONG_TRANSCRIPT_FRAME_BUDGET" in budgets
    assert "Conversation interrupted" in binding
    assert "Operation aborted" in binding
    assert "PRODUCT_COMPOSED_FRAME_BUDGET" in product
    assert "PRODUCT_STREAMING_CONTROL_FRAME_BUDGET" in product


def test_shared_interaction_types_are_not_redefined_in_coding_ui() -> None:
    moved_definitions = {
        Path("src/loushang/coding/model_selection_tui.py"): ("class ModelChoice",),
        Path("src/loushang/coding/ui/prompt_dispatch.py"): (
            "class PromptDispatchOutcome",
        ),
        Path("src/loushang/coding/ui/run_context.py"): ("def _stable_emit_factory",),
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
        Path("src/loushang/coding/ui/settings_page.py"): (
            "class ModelPage",
            "class SettingsPageView",
            "class StaticLinesPage",
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


def test_shared_conversation_interaction_does_not_own_coding_policy_or_copy() -> None:
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
    prompt_dispatch = Path("src/loushang/coding/ui/prompt_dispatch.py").read_text(
        encoding="utf-8"
    )

    assert "Follow-up is only available while a run is active." in follow_up
    assert "Follow-up queued." in follow_up
    assert (
        "Conversation interrupted - tell the model what to do differently."
        in screen_loop
    )
    assert "Operation aborted" in screen_loop
    assert "ImagePart" in screen_input
    assert '".loushang" / "clipboard"' in screen_input
    assert "class ScreenInputResult" not in screen_input
    assert "class ScreenInputRouter" not in screen_input
    assert "ConversationInputRouter(" in screen_input
    assert "PromptIntent" in prompt_dispatch
    assert "BashIntent" in prompt_dispatch


def test_shared_surface_controller_does_not_own_coding_policy_or_copy() -> None:
    shared = Path("src/loushang/harnesstui/surface/controller.py").read_text(
        encoding="utf-8"
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


def test_shared_catalog_interactions_do_not_own_coding_policy_or_copy() -> None:
    command_interaction = Path(
        "src/loushang/harnesstui/commands/interaction.py"
    ).read_text(encoding="utf-8")
    model_interaction = Path(
        "src/loushang/harnesstui/selection/interaction.py"
    ).read_text(encoding="utf-8")
    shared = command_interaction + model_interaction
    command_adapter = Path("src/loushang/coding/commands/tui.py").read_text(
        encoding="utf-8"
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


def test_shared_screen_projection_target_does_not_own_coding_policy_or_copy() -> None:
    shared = Path("src/loushang/harnesstui/conversation/screen_target.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/ui/screen_events.py").read_text(encoding="utf-8")

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
    shared = Path("src/loushang/harnesstui/conversation/window_budget.py").read_text(
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
    assert "transcript_window_trimmed:active_line_budget" in coding
    assert "trim_records_to_line_budget" in coding


def test_tui_owns_transcript_region_while_coding_owns_presentation_policy() -> None:
    from loushang.coding.ui.screen_app import ScreenCodingTuiApp
    from loushang.tui.ui_parts.transcript import TranscriptRegion

    shared = Path("src/loushang/tui/ui_parts/transcript.py").read_text(encoding="utf-8")
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    assert "class _ScreenTranscriptRegion" not in coding
    for token in (
        "_screen_coding_display_record",
        "_coding_lines",
        "_compact_display_paths",
        "collapse_tool_output_preview",
        "DEFAULT_TOOL_OUTPUT_PREVIEW_LINES",
        "bright_cyan",
    ):
        assert token not in shared
        assert token in coding

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
    shared = Path("src/loushang/harnesstui/conversation/screen_app.py").read_text(
        encoding="utf-8"
    )
    coding = Path("src/loushang/coding/ui/screen_app.py").read_text(encoding="utf-8")

    for token in (
        "ScreenCodingTuiApp",
        "_CodingTranscriptPresentation",
        "LoushangWelcomePanel",
        "Compacted summary:",
        "trim_records_to_line_budget",
        "DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET = 320",
        "collapse_tool_output_preview",
    ):
        assert token not in shared
        assert token in coding
    assert "class ScreenCodingTuiApp(ScreenConversationApp)" in coding


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
