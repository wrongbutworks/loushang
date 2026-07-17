from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

UNRESOLVED_RELATIVE_IMPORT = "<unresolved-relative-import>"


@dataclass(frozen=True)
class ImportBoundary:
    name: str
    root: Path
    forbidden_prefixes: tuple[str, ...]
    allowed_paths: frozenset[str] = frozenset()


def test_core_runtime_packages_do_not_import_product_layers() -> None:
    boundaries = (
        ImportBoundary(
            name="protocol",
            root=Path("src/loushang/protocol"),
            forbidden_prefixes=(
                "loushang.agent",
                "loushang.ai",
                "loushang.channel",
                "loushang.coding",
                "loushang.harness",
                "loushang.method",
                "loushang.observability",
                "loushang.ontology",
                "loushang.resource",
                "loushang.tui",
                "loushang.work",
            ),
        ),
        ImportBoundary(
            name="ai",
            root=Path("src/loushang/ai"),
            forbidden_prefixes=(
                "loushang.agent",
                "loushang.channel",
                "loushang.coding",
                "loushang.harness",
                "loushang.method",
                "loushang.tui",
                "loushang.work",
            ),
        ),
        ImportBoundary(
            name="agent",
            root=Path("src/loushang/agent"),
            forbidden_prefixes=(
                "loushang.coding",
                "loushang.harness",
                "loushang.method",
                "loushang.tui",
                "loushang.work",
            ),
        ),
        ImportBoundary(
            name="harness",
            root=Path("src/loushang/harness"),
            forbidden_prefixes=(
                "loushang.agent.Agent",
                "loushang.agent.agent",
                "loushang.agent.harness",
                "loushang.coding",
                "loushang.method",
                "loushang.tui",
                "loushang.work",
            ),
        ),
        ImportBoundary(
            name="work",
            root=Path("src/loushang/work"),
            forbidden_prefixes=(
                "loushang.agent",
                "loushang.coding",
                "loushang.method",
                "loushang.tui",
            ),
            allowed_paths=frozenset(
                {
                    "src/loushang/work/coding.py",
                    "src/loushang/work/projection.py",
                }
            ),
        ),
        ImportBoundary(
            name="method",
            root=Path("src/loushang/method"),
            forbidden_prefixes=(
                "loushang.coding",
                "loushang.tui",
            ),
        ),
        ImportBoundary(
            name="channel",
            root=Path("src/loushang/channel"),
            forbidden_prefixes=(
                "loushang.agent",
                "loushang.ai",
                "loushang.coding",
                "loushang.harness",
                "loushang.method",
                "loushang.tui",
            ),
        ),
    )

    offenders: list[str] = []
    for boundary in boundaries:
        offenders.extend(_find_forbidden_imports(boundary))

    assert offenders == []


def test_harness_agent_profiles_have_narrow_ai_agent_dependency_allowlists() -> None:
    harness_root = Path("src/loushang/harness")
    profile_allowlists = {
        harness_root / "agent_transcript": (
            "loushang.ai.types",
            "loushang.ai.json_codec",
            "loushang.agent.types",
            "loushang.agent.json_codec",
        ),
        harness_root / "session": (
            "loushang.ai.types",
            "loushang.agent",
        ),
    }
    offenders: list[str] = []

    for path in sorted(harness_root.rglob("*.py")):
        allowed_prefixes = next(
            (
                prefixes
                for profile_root, prefixes in profile_allowlists.items()
                if path == profile_root or profile_root in path.parents
            ),
            (),
        )
        for imported in _absolute_imports(path):
            is_ai_import = _matches_any(imported, ("loushang.ai",))
            is_profile_agent_import = bool(allowed_prefixes) and _matches_any(
                imported, ("loushang.agent",)
            )
            if not is_ai_import and not is_profile_agent_import:
                continue
            if _matches_any(imported, allowed_prefixes):
                continue
            offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_neutral_conversation_core_does_not_import_agent_ai_or_products() -> None:
    boundary = ImportBoundary(
        name="conversation",
        root=Path("src/loushang/harness/conversation"),
        forbidden_prefixes=(
            "loushang.agent",
            "loushang.ai",
            "loushang.coding",
            "loushang.method",
            "loushang.tui",
            "loushang.work",
        ),
    )

    assert _find_forbidden_imports(boundary) == []


def test_neutral_storage_and_event_cores_do_not_import_runtime_or_products() -> None:
    forbidden = (
        "loushang.agent",
        "loushang.ai",
        "loushang.channel",
        "loushang.coding",
        "loushang.method",
        "loushang.tui",
        "loushang.work",
    )
    boundaries = (
        ImportBoundary(
            name="storage",
            root=Path("src/loushang/harness/storage"),
            forbidden_prefixes=forbidden,
        ),
        ImportBoundary(
            name="events",
            root=Path("src/loushang/harness/events"),
            forbidden_prefixes=forbidden,
        ),
    )

    assert [
        offender
        for boundary in boundaries
        for offender in _find_forbidden_imports(boundary)
    ] == []


def test_scenario_runtime_is_product_neutral_and_never_executes_shell() -> None:
    boundary = ImportBoundary(
        name="scenario",
        root=Path("src/loushang/harness/scenario"),
        forbidden_prefixes=(
            "loushang.agent",
            "loushang.ai",
            "loushang.channel",
            "loushang.coding",
            "loushang.method",
            "loushang.tui",
            "loushang.work",
        ),
    )

    assert _find_forbidden_imports(boundary) == []
    assert all(
        "subprocess" not in path.read_text(encoding="utf-8")
        for path in boundary.root.rglob("*.py")
    )


def test_coding_work_projection_subscribes_to_runtime_events() -> None:
    source = Path("src/loushang/coding/work_shell.py").read_text(encoding="utf-8")

    assert "subscribe_runtime_events" in source
    assert "self.session.subscribe(listener)" not in source


def test_coding_session_uses_harness_runtime_events_as_the_only_internal_stream() -> (
    None
):
    session_source = Path("src/loushang/coding/session/agent_session.py").read_text(
        encoding="utf-8"
    )
    controller_sources = [
        Path(path).read_text(encoding="utf-8")
        for path in (
            "src/loushang/coding/session/compaction_controller.py",
            "src/loushang/coding/session/retry_controller.py",
            "src/loushang/coding/session/tree_controller.py",
        )
    ]

    assert "SessionEventBus" not in session_source
    assert "self._event_bus" not in session_source
    assert not Path("src/loushang/coding/session/session_event_bus.py").exists()
    assert all("loushang.coding.event" not in source for source in controller_sources)
    assert "project_runtime_event_to_session_event" in session_source


def test_extension_message_controller_is_a_product_api_adapter() -> None:
    source = Path(
        "src/loushang/coding/session/extension_message_controller.py"
    ).read_text(encoding="utf-8")

    assert "ApplicationInputRuntime" in source
    assert "SessionManager" not in source
    assert "append_message(" not in source


def test_importing_channel_types_does_not_eagerly_load_agent_or_ai() -> None:
    script = """
import importlib
import sys

importlib.import_module("loushang.channel.types")
forbidden = sorted(
    name
    for name in sys.modules
    if name == "loushang.agent"
    or name.startswith("loushang.agent.")
    or name == "loushang.ai"
    or name.startswith("loushang.ai.")
    or name == "loushang.work.projection"
)
assert forbidden == [], forbidden
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_importing_channel_public_api_does_not_eagerly_load_runtime_or_products() -> (
    None
):
    script = """
import importlib
import sys

importlib.import_module("loushang.channel")
forbidden = sorted(
    name
    for name in sys.modules
    if name == "loushang.agent"
    or name.startswith("loushang.agent.")
    or name == "loushang.ai"
    or name.startswith("loushang.ai.")
    or name == "loushang.coding"
    or name.startswith("loushang.coding.")
    or name == "loushang.harness"
    or name.startswith("loushang.harness.")
)
assert forbidden == [], forbidden
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_legacy_agent_harness_package_has_been_removed() -> None:
    assert not Path("src/loushang/agent/harness").exists()


def test_coding_message_legacy_package_and_imports_have_been_removed() -> None:
    assert not any(Path("src/loushang/coding/message").glob("*.py"))
    offenders = [
        f"{path.as_posix()} imports {imported}"
        for path in sorted(Path("src/loushang/coding").rglob("*.py"))
        for imported in _absolute_imports(path)
        if _matches_any(imported, ("loushang.coding.message",))
    ]
    assert offenders == []


def test_harness_slice1_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    slice1_symbols = {
        "ApprovalDecision",
        "ApprovalRequest",
        "ApprovalResolver",
        "DenyApprovalResolver",
        "HeadlessApprovalResolver",
        "MaybeAwaitable",
        "ToolDefinitionResolver",
        "ToolContribution",
        "ToolDefinition",
        "ToolPackDefinition",
        "ToolRegistry",
        "ToolRenderContext",
        "ToolRenderResultOptions",
        "ToolRenderRuntime",
        "ToolResolutionDiagnostic",
        "ToolResolutionError",
        "ToolResolutionResult",
        "ToolResultPresentation",
        "collapse_text",
        "normalize_display_text",
        "normalize_line_endings",
        "resolve_approval",
        "resolve_tool_contributions",
        "strip_ansi",
        "tool",
    }

    assert slice1_symbols.isdisjoint(set(harness.__all__))


def test_harness_workspace_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    workspace_symbols = {
        "ExecBackend",
        "ExecOutputChunk",
        "ExecRequest",
        "ExecResult",
        "ExecService",
        "ExecUpdateCallback",
        "TruncationResult",
        "truncate_head",
        "truncate_tail",
    }

    assert workspace_symbols.isdisjoint(set(harness.__all__))


def test_harness_contribution_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    contribution_symbols = {
        "ContributionDescriptor",
        "ContributionRegistry",
        "ContributionType",
        "DuplicateContributionKeyError",
        "DuplicateExtensionSurfaceKeyError",
        "ExtensionInventory",
        "ExtensionSurfaceDescriptor",
        "ExtensionSurfaceType",
    }

    assert contribution_symbols.isdisjoint(set(harness.__all__))


def test_harness_context_and_journal_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    context_symbols = {
        "CompactionBudget",
        "CompactionCoordinator",
        "ContextCompactionCoordinator",
        "ContextItem",
        "ContextPacker",
        "ContextUsageEstimate",
        "ContextSalienceRanker",
        "BranchGraph",
        "JsonProjectionIndex",
        "JsonlJournal",
        "LayeredConfig",
        "SummaryProfile",
        "TranscriptRepository",
        "calculate_compaction_budget",
    }

    assert context_symbols.isdisjoint(set(harness.__all__))


def test_harness_diagnostics_symbols_are_not_package_exports() -> None:
    import loushang.harness as harness
    import loushang.harness.diagnostics as diagnostics

    diagnostic_symbols = {
        "DiagnosticLevel",
        "DiagnosticPhase",
        "DiagnosticRecord",
        "DiagnosticSource",
        "DiagnosticSummary",
        "DiagnosticsQuery",
        "DiagnosticsService",
        "ErrorReport",
        "StartupCheck",
        "StartupCheckResult",
    }

    assert diagnostic_symbols.isdisjoint(set(harness.__all__))
    assert diagnostics.__all__ == []


def test_harness_host_symbols_are_not_package_exports() -> None:
    import loushang.harness as harness
    import loushang.harness.host as host

    host_symbols = {
        "HostInputQueue",
        "HostLifecycleEvent",
        "HostRuntime",
        "HostSnapshot",
        "HostStateError",
        "OrderedEventBus",
        "QueueSnapshot",
        "QueuedMessageSnapshot",
        "RunState",
    }

    assert host_symbols.isdisjoint(set(harness.__all__))
    assert host.__all__ == []


def test_product_runtime_core_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    runtime_symbols = {
        "BoundProductRuntimeContext",
        "CoalescingScheduler",
        "ProductRuntimeBindings",
        "RuntimeBindingLease",
        "RuntimeBindingState",
        "SessionTransitionHost",
        "UnboundProductRuntimeContext",
    }

    assert runtime_symbols.isdisjoint(set(harness.__all__))


def test_conversation_runtime_core_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness
    import loushang.harness.context.conversation as conversation_context
    import loushang.harness.conversation as conversation

    conversation_symbols = set(conversation.__all__)
    context_conversation_symbols = set(conversation_context.__all__)

    assert conversation_symbols.isdisjoint(set(harness.__all__))
    assert context_conversation_symbols.isdisjoint(set(harness.__all__))


def test_conversation_runtime_core_does_not_import_channel_implementations() -> None:
    boundaries = (
        ImportBoundary(
            name="conversation",
            root=Path("src/loushang/harness/conversation"),
            forbidden_prefixes=("loushang.channel",),
        ),
        ImportBoundary(
            name="conversation context",
            root=Path("src/loushang/harness/context"),
            forbidden_prefixes=("loushang.channel",),
        ),
    )

    offenders = [
        offender
        for boundary in boundaries
        for offender in _find_forbidden_imports(boundary)
    ]
    assert offenders == []


def test_coding_internal_diagnostics_imports_use_harness_owners() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/diagnostics/__init__.py",
        "src/loushang/coding/diagnostics/service.py",
        "src/loushang/coding/diagnostics/types.py",
    }
    legacy_symbols = (
        "loushang.coding.DiagnosticRecord",
        "loushang.coding.DiagnosticSummary",
        "loushang.coding.DiagnosticsQuery",
        "loushang.coding.DiagnosticsService",
        "loushang.coding.ErrorReport",
        "loushang.coding.StartupCheck",
        "loushang.coding.StartupCheckResult",
        "loushang.coding.diagnostics.DiagnosticLevel",
        "loushang.coding.diagnostics.DiagnosticPhase",
        "loushang.coding.diagnostics.DiagnosticRecord",
        "loushang.coding.diagnostics.DiagnosticSource",
        "loushang.coding.diagnostics.DiagnosticSummary",
        "loushang.coding.diagnostics.DiagnosticsQuery",
        "loushang.coding.diagnostics.DiagnosticsService",
        "loushang.coding.diagnostics.ErrorReport",
        "loushang.coding.diagnostics.StartupCheck",
        "loushang.coding.diagnostics.StartupCheckResult",
        "loushang.coding.diagnostics.service.DiagnosticsService",
        "loushang.coding.diagnostics.types.DiagnosticLevel",
        "loushang.coding.diagnostics.types.DiagnosticPhase",
        "loushang.coding.diagnostics.types.DiagnosticRecord",
        "loushang.coding.diagnostics.types.DiagnosticSource",
        "loushang.coding.diagnostics.types.DiagnosticSummary",
        "loushang.coding.diagnostics.types.DiagnosticsQuery",
        "loushang.coding.diagnostics.types.ErrorReport",
        "loushang.coding.diagnostics.types.StartupCheck",
        "loushang.coding.diagnostics.types.StartupCheckResult",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_diagnostics_core_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/diagnostics-core-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Diagnostics Core Boundary",
        "`loushang.harness.diagnostics.types`",
        "`loushang.harness.diagnostics.service`",
        "same Harness-owned objects",
        "`coding.diagnostics.serialization`",
        "`coding.diagnostics.problem_bridge`",
        "must not import coding, method, work, TUI, AI, agent runtime, provider, observability, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Diagnostics Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.diagnostics`" in inventory_text
    assert "diagnostics core implementation complete" in inventory_text


def test_coding_internal_context_budget_imports_use_harness_owners() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/compaction/__init__.py",
        "src/loushang/coding/compaction/policy.py",
        "src/loushang/coding/compaction/types.py",
    }
    legacy_symbols = (
        "loushang.coding.ContextUsageEstimate",
        "loushang.coding.compaction.CompactionBudget",
        "loushang.coding.compaction.ContextUsageEstimate",
        "loushang.coding.compaction.calculate_compaction_budget",
        "loushang.coding.compaction.policy.CompactionBudget",
        "loushang.coding.compaction.policy.calculate_compaction_budget",
        "loushang.coding.compaction.types.ContextUsageEstimate",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_context_budget_and_accounting_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/context-budget-accounting-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Context Budget And Accounting Boundary",
        "`loushang.harness.context.budget`",
        "`loushang.harness.context.usage`",
        "same Harness-owned objects",
        "This migration establishes budget and accounting ownership only",
        "must not import coding, method, work, TUI, AI, agent runtime, provider, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Context Budget And Accounting Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.context`" in inventory_text
    assert "context budget and accounting implementation complete" in inventory_text


def test_harness_context_compaction_and_journal_design_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/context-compaction-journal-foundations.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Context, Compaction, And Journal Foundations",
        "Status: implementation complete for integration into `lane/harness`",
        "`RecentWindowStrategy`",
        "`RollingSummaryStrategy`",
        "`CodingCompactionStrategy`",
        "`JournalFormatProfile`",
        "`JournalDurabilityProfile`",
        "`JournalLoadPolicy`",
        "context compaction changes the bounded projection sent to a model and never deletes source journal records",
        "journal-offset checkpoints, destructive journal vacuum, and retention remain deferred",
        "AI owns the stable base-message and message-part codec",
        "Agent owns the extension-message codec protocol and registry",
        "Work adopts only common JSONL I/O in the first wave",
        "three delivery batches for foundation, engines, and product cutover",
        "No type-only, protocol-only, codec-only, or single-adapter change counts as a finished delivery batch",
        "remove the replaced Coding and Work implementations in the same batch as their adapters",
        "must not depend on context",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Context, Compaction, And Journal Foundations" in readme_text

    inventory_text = " ".join(
        Path(
            "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
        )
        .read_text(encoding="utf-8")
        .split()
    )
    assert (
        "context, compaction, journal, and branch implementation complete"
        in inventory_text
    )
    assert "rebuildable generic JSON projection indexes" in inventory_text


def test_context_compaction_and_journal_mechanics_use_harness_owners() -> None:
    expected_imports = {
        Path("src/loushang/coding/compaction/service.py"): {
            "loushang.harness.context.compaction.CompactionCoordinator",
        },
        Path("src/loushang/coding/store/file_codec.py"): {
            "loushang.harness.conversation.NativeConversationHeaderCodec",
            "loushang.harness.conversation.NativeConversationRecordCodec",
            "loushang.harness.journal.JsonlJournal",
        },
        Path("src/loushang/coding/store/file_lock.py"): {
            "loushang.harness.journal.jsonl.journal_file_lock",
        },
        Path("src/loushang/coding/store/session_manager.py"): {
            "loushang.harness.conversation.ConversationRepository",
        },
        Path("src/loushang/work/event_log.py"): {
            "loushang.harness.journal.FunctionalJournalRecordCodec",
            "loushang.harness.journal.JsonlJournal",
        },
    }

    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []


def test_harness_runtime_data_foundations_are_documented_and_adopted() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/runtime-data-foundations.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Runtime Data Foundations",
        "`harness/runtime-data-foundations`",
        "`loushang.harness.journal.TranscriptRepository[H, R]`",
        "`JsonProjectionIndex[P]`",
        "`loushang.harness.config.LayeredConfig[T]`",
        "`ContextSalienceRanker`",
        "`SummaryProfile`",
        "Only the separate optional Agent transcript profile serializes Agent messages",
        "Harness never stores credentials",
        "No type-only, protocol-only, or duplicate parallel implementation counts as a completed batch",
        "Lack of a second production consumer is not a blocking gate",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Runtime Data Foundations" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "parent-linked transcript repositories" in inventory_text
    assert "`loushang.harness.config`" in inventory_text
    assert "summary-profile mechanics" in inventory_text

    expected_imports = {
        Path("src/loushang/coding/store/session_manager.py"): {
            "loushang.harness.conversation.ConversationCatalog",
            "loushang.harness.conversation.ConversationRepository",
            "loushang.harness.journal.JsonProjectionIndex",
        },
        Path("src/loushang/coding/control/settings_manager.py"): {
            "loushang.harness.config.LayeredConfig",
        },
        Path("src/loushang/coding/compaction/compaction.py"): {
            "loushang.harness.context.ConversationCompactionPlanner",
            "loushang.harness.context.summary.build_summary_prompt",
        },
        Path("src/loushang/coding/compaction/summary_quality.py"): {
            "loushang.harness.context.validate_summary",
        },
    }
    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []

    assert "import json" not in Path(
        "src/loushang/coding/store/file_codec.py"
    ).read_text(encoding="utf-8")
    assert "import json" not in Path("src/loushang/work/event_log.py").read_text(
        encoding="utf-8"
    )


def test_product_configuration_runtime_boundary_is_documented_and_adopted() -> None:
    import loushang.harness as harness

    design_path = Path(
        "docs/internals/architecture/harness/product-configuration-runtime-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Product Configuration Runtime Boundary",
        "`loushang.harness.config`",
        "`ConfigFieldSpec[T]`",
        "`SchemaConfigCodec`",
        "`ScopedConfigRuntime`",
        "`ConfigActivationRuntime`",
        "`ConfigValueResolver`",
        "Harness configuration never stores credentials",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Product Configuration Runtime Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.config`" in inventory_text
    assert "### Product Configuration Runtime" in inventory_text
    assert "`harness/product-configuration-runtime`" in inventory_text
    assert (
        "Keep `coding.control` frozen during runtime consolidation."
        not in inventory_text
    )

    expected_imports = {
        Path("src/loushang/coding/control/settings_manager.py"): {
            "loushang.harness.config.ConfigFieldSpec",
            "loushang.harness.config.LayeredConfig",
            "loushang.harness.config.SchemaConfigCodec",
            "loushang.harness.config.ScopedConfigRuntime",
        },
        Path("src/loushang/coding/control/config_value.py"): {
            "loushang.harness.config.values.ConfigValueResolver",
        },
        Path("src/loushang/coding/bootstrap.py"): {
            "loushang.harness.config.ConfigActivationRuntime",
        },
    }
    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []

    assert (
        _find_forbidden_imports(
            ImportBoundary(
                name="harness config",
                root=Path("src/loushang/harness/config"),
                forbidden_prefixes=("loushang.ai", "loushang.coding"),
            )
        )
        == []
    )

    value_imports = _absolute_imports(Path("src/loushang/harness/config/values.py"))
    assert not any(
        _matches_any(imported, ("subprocess",)) for imported in value_imports
    )

    config_symbols = {
        "ConfigActivationRuntime",
        "ConfigFieldSpec",
        "ConfigValueResolver",
        "LayeredConfig",
        "SchemaConfigCodec",
        "ScopedConfigRuntime",
    }
    assert config_symbols.isdisjoint(set(harness.__all__))


def test_harness_conversation_runtime_core_is_documented_and_adopted() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/conversation-runtime-core-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Conversation Runtime Core Boundary",
        "Status: implementation complete for integration into `lane/harness`",
        "`ConversationRepository`",
        "`ConversationReplayFolder`",
        "`ConversationCatalog`",
        "`ConversationCompactionPlanner`",
        "`CommandExecutionRecord`",
        "These neutral conversation packages must not import Coding, Agent, AI messages, model/provider code, Product stores, Method, Work, TUI, or channel implementations",
        "the neutral core owns control mechanics, the optional Agent profile owns common Agent transcript meanings",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Conversation Runtime Core Boundary" in readme_text

    coding_store_imports = {
        imported
        for path in (
            Path("src/loushang/coding/store/file_codec.py"),
            Path("src/loushang/coding/store/session_manager.py"),
        )
        for imported in _absolute_imports(path)
    }
    assert "loushang.harness.conversation.ConversationRepository" in (
        coding_store_imports
    )
    assert "loushang.harness.journal.TranscriptRepository" not in (coding_store_imports)
    assert "loushang.harness.journal.BranchGraph" not in coding_store_imports

    compaction_imports = set(
        _absolute_imports(Path("src/loushang/coding/compaction/compaction.py"))
    )
    assert "loushang.harness.context.ConversationCompactionPlanner" in (
        compaction_imports
    )


def test_coding_internal_contribution_imports_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/extensions/__init__.py",
        "src/loushang/coding/extensions/contributions.py",
    }
    legacy_symbols = (
        "loushang.coding.extensions.ContributionDescriptor",
        "loushang.coding.extensions.ContributionRegistry",
        "loushang.coding.extensions.ContributionType",
        "loushang.coding.extensions.DuplicateContributionKeyError",
        "loushang.coding.extensions.DuplicateExtensionSurfaceKeyError",
        "loushang.coding.extensions.ExtensionInventory",
        "loushang.coding.extensions.ExtensionSurfaceDescriptor",
        "loushang.coding.extensions.ExtensionSurfaceType",
        "loushang.coding.extensions.contributions.ContributionDescriptor",
        "loushang.coding.extensions.contributions.ContributionRegistry",
        "loushang.coding.extensions.contributions.ContributionType",
        "loushang.coding.extensions.contributions.DuplicateContributionKeyError",
        "loushang.coding.extensions.contributions.DuplicateExtensionSurfaceKeyError",
        "loushang.coding.extensions.contributions.ExtensionInventory",
        "loushang.coding.extensions.contributions.ExtensionSurfaceDescriptor",
        "loushang.coding.extensions.contributions.ExtensionSurfaceType",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_contribution_inventory_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/contribution-inventory-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Contribution Inventory Boundary",
        "`loushang.harness.contributions`",
        "same harness-owned classes",
        "`surfaces_from_loaded_extension`",
        "`loushang.harness.extensions.contributions`",
        "must not import coding, method, work, TUI, AI, agent runtime, provider, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Contribution Inventory Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.contributions`" in inventory_text
    assert "contribution inventory implementation complete" in inventory_text


def test_harness_extension_runtime_core_boundary_is_documented() -> None:
    import loushang.harness as harness
    import loushang.harness.extensions as extensions

    design_path = Path(
        "docs/internals/architecture/harness/extension-runtime-core-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Extension Runtime Core Boundary",
        "`loushang.harness.extensions`",
        "`ExtensionContributionAPI`",
        "same Harness-owned objects",
        "Coding keeps",
        "must not import coding, method, work, TUI, AI",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    assert extensions.__all__ == []
    assert "ExtensionContributionAPI" not in harness.__all__

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Extension Runtime Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "extension runtime core implementation" in inventory_text
    assert "Wave 2: Extension Runtime Core" in inventory_text


def test_harness_control_plane_runtime_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/control-plane-runtime-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Control Plane Runtime Boundary",
        "`loushang.harness.extensions.routing`",
        "`PolicyEvaluatorChain`",
        "`ApprovalBroker`",
        "Products and OEM adapters continue to own:",
        "Harness must not import Coding, Design, Research, PPT, Cowork, Method, Work, Channel, TUI, AI",
        "No compatibility module may retain a parallel routing, pending-request, command normalization, or rule-evaluation implementation",
        "top-level `loushang.harness.__all__` remains unchanged",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    design_link = "[Control Plane Runtime Boundary](control-plane-runtime-boundary.md)"
    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert design_link in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert design_link in inventory_text
    assert "Wave 2 Follow-On: Control Plane Runtime" in inventory_text


def test_harness_control_plane_symbols_are_not_top_level_exports() -> None:
    import loushang.harness as harness

    control_plane_symbols = {
        "ApprovalBroker",
        "ApprovalPresenter",
        "ApprovalRequestCollisionError",
        "CommandPolicySubject",
        "CommandSubstringMatcher",
        "CommandTokenSequenceMatcher",
        "CustomPolicySubject",
        "ExactToolNameMatcher",
        "ExtensionContextFactory",
        "ExtensionRouteError",
        "ExtensionRoutePlan",
        "ExtensionRouter",
        "ExtensionRuntimeErrorHandler",
        "IncompleteCommandMatcher",
        "PathPolicySubject",
        "PathSubstringMatcher",
        "PolicyChainStrategy",
        "PolicyDisposition",
        "PolicyEvaluationError",
        "PolicyEvaluator",
        "PolicyEvaluatorChain",
        "PolicyMatcher",
        "PolicyRule",
        "RegisteredExtensionHandler",
        "ResolvedControlContributions",
        "ResolvedExtensionRoute",
        "RouteErrorPolicy",
        "RouteReducer",
        "RouteStep",
        "RulePolicyEvaluator",
        "ShellPayloadSubstringMatcher",
        "ToolPolicySubject",
        "build_path_policy_subjects",
        "build_tool_policy_subject",
        "ensure_approval_action_id",
        "evaluate_policy",
        "normalize_command_subject",
        "resolve_control_contributions",
    }

    assert control_plane_symbols.isdisjoint(set(harness.__all__))


def test_coding_control_plane_adapters_use_harness_mechanisms() -> None:
    approval_path = Path("src/loushang/coding/policy/approval.py")
    approval_imports = set(_absolute_imports(approval_path))
    assert "loushang.harness.approval.ApprovalBroker" in approval_imports

    approval_tree = ast.parse(
        approval_path.read_text(encoding="utf-8"),
        filename=approval_path.as_posix(),
    )
    approval_names = {
        node.id for node in ast.walk(approval_tree) if isinstance(node, ast.Name)
    }
    approval_attributes = {
        node.attr for node in ast.walk(approval_tree) if isinstance(node, ast.Attribute)
    }
    approval_calls = {
        node.func.id
        for node in ast.walk(approval_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "ApprovalBroker" in approval_calls
    assert not any(
        _matches_any(imported, ("asyncio",)) for imported in approval_imports
    )
    assert {"Future", "create_future", "_pending"}.isdisjoint(
        approval_names | approval_attributes
    )

    policy_path = Path("src/loushang/coding/policy/engine.py")
    policy_imports = set(_absolute_imports(policy_path))
    assert {
        "loushang.harness.policy.RulePolicyEvaluator",
        "loushang.harness.policy.normalize_command_subject",
    }.issubset(policy_imports)

    policy_tree = ast.parse(
        policy_path.read_text(encoding="utf-8"),
        filename=policy_path.as_posix(),
    )
    policy_function_names = {
        node.name
        for node in ast.walk(policy_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert {
        "_direct_command_tokens",
        "_split_env_string",
        "_unwrap_env_command",
        "_unwrap_leading_wrappers",
    }.isdisjoint(policy_function_names)
    assert not any(_matches_any(imported, ("shlex",)) for imported in policy_imports)

    extension_paths = (
        Path("src/loushang/coding/extensions/hooks.py"),
        Path("src/loushang/coding/extensions/runner.py"),
    )
    extension_imports = {
        imported for path in extension_paths for imported in _absolute_imports(path)
    }
    assert {
        "loushang.harness.extensions.routing.ExtensionRoutePlan",
        "loushang.harness.extensions.routing.ExtensionRouter",
    }.issubset(extension_imports)

    route_calls: set[str] = set()
    route_function_names: set[str] = set()
    for path in extension_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        route_calls.update(
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        )
        route_function_names.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
    assert {"from_extensions", "intercept", "observe", "reduce"}.issubset(route_calls)
    assert {
        "_order_routes",
        "_route_order_key",
        "_strongly_connected_components",
        "_topological_sort",
    }.isdisjoint(route_function_names)


def test_harness_control_plane_modules_do_not_import_product_layers() -> None:
    control_plane_paths = (
        Path("src/loushang/harness/approval.py"),
        Path("src/loushang/harness/policy.py"),
        Path("src/loushang/harness/extensions/control.py"),
        Path("src/loushang/harness/extensions/routing.py"),
    )
    assert [path.as_posix() for path in control_plane_paths if not path.exists()] == []

    forbidden_prefixes = (
        "loushang.ai",
        "loushang.channel",
        "loushang.coding",
        "loushang.cowork",
        "loushang.design",
        "loushang.method",
        "loushang.ppt",
        "loushang.research",
        "loushang.tui",
        "loushang.work",
    )
    offenders = [
        f"{path.as_posix()} imports {imported}"
        for path in control_plane_paths
        for imported in _absolute_imports(path)
        if _matches_any(imported, forbidden_prefixes)
    ]
    assert offenders == []


def test_coding_extension_compatibility_paths_share_harness_owners() -> None:
    from loushang.coding.extensions.loader import ExtensionLoader as CodingLoader
    from loushang.coding.extensions.manifest import (
        ExtensionManifest as CodingManifest,
    )
    from loushang.coding.extensions.policy import (
        ExtensionPolicyDecision as CodingPolicyDecision,
    )
    from loushang.coding.extensions.types import LoadedExtension as CodingLoaded
    from loushang.harness.extensions.loader import ExtensionLoader as HarnessLoader
    from loushang.harness.extensions.manifest import (
        ExtensionManifest as HarnessManifest,
    )
    from loushang.harness.extensions.types import (
        ExtensionPolicyDecision as HarnessPolicyDecision,
    )
    from loushang.harness.extensions.types import LoadedExtension as HarnessLoaded

    assert issubclass(CodingLoader, HarnessLoader)
    assert CodingManifest is HarnessManifest
    assert CodingPolicyDecision is HarnessPolicyDecision
    assert CodingLoaded is HarnessLoaded


def test_coding_internal_exec_imports_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/exec/__init__.py",
        "src/loushang/coding/exec/service.py",
        "src/loushang/coding/exec/types.py",
    }
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if imported.startswith("loushang.coding.exec"):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_coding_internal_workspace_operation_imports_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/tools/__init__.py",
        "src/loushang/coding/tools/operations.py",
    }
    legacy_symbols = (
        "loushang.coding.tools.operations.EditOperations",
        "loushang.coding.tools.operations.FindOperations",
        "loushang.coding.tools.operations.GrepOperations",
        "loushang.coding.tools.operations.LOCAL_TOOL_OPERATIONS",
        "loushang.coding.tools.operations.LocalToolOperations",
        "loushang.coding.tools.operations.LsOperations",
        "loushang.coding.tools.operations.ReadOperations",
        "loushang.coding.tools.operations.ToolOperations",
        "loushang.coding.tools.operations.WriteOperations",
        "loushang.coding.tools.operations.resolve_operation",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_workspace_operation_boundary_is_documented() -> None:
    import loushang.harness as harness

    operation_symbols = {
        "EditOperations",
        "FindOperations",
        "GrepOperations",
        "LOCAL_TOOL_OPERATIONS",
        "LocalToolOperations",
        "LsOperations",
        "OperationResult",
        "ReadOperations",
        "ToolOperations",
        "WriteOperations",
        "resolve_operation",
    }
    assert operation_symbols.isdisjoint(set(harness.__all__))

    design_path = Path(
        "docs/internals/architecture/harness/workspace-operation-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Workspace Operation Boundary",
        "`loushang.harness.workspace.operations`",
        "same harness-owned protocols, class, and singleton",
        "keeps all `normalize_*_operations` functions",
        "does not select an allowed root",
        "must not import coding, method, work, TUI, AI, provider, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Workspace Operation Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.workspace.operations`" in inventory_text
    assert "workspace operation implementation complete" in inventory_text


def test_coding_internal_mutation_queue_imports_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/tools/__init__.py",
        "src/loushang/coding/tools/file_mutation_queue.py",
    }
    legacy_symbols = (
        "loushang.coding.tools.file_mutation_queue.run_with_file_mutation_queue",
        "loushang.coding.tools.file_mutation_queue.with_file_mutation_queue",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_workspace_path_and_mutation_boundary_is_documented() -> None:
    import loushang.harness as harness

    path_mutation_symbols = {
        "PathNormalizer",
        "PathVariantProvider",
        "canonicalize_workspace_path",
        "expand_user_path",
        "normalize_unicode_spaces",
        "resolve_path_from_cwd",
        "resolve_workspace_path",
        "run_with_file_mutation_queue",
        "user_input_path_variants",
        "with_file_mutation_queue",
    }
    assert path_mutation_symbols.isdisjoint(set(harness.__all__))

    design_path = Path(
        "docs/internals/architecture/harness/workspace-path-mutation-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Workspace Path And Mutation Boundary",
        "`loushang.harness.workspace.paths`",
        "`loushang.harness.workspace.mutation_queue`",
        "The engine does not enable product syntax or correction policy by itself",
        "the Pi/coding `@` reference prefix",
        "must not import coding, method, work, TUI, AI, provider, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Workspace Path And Mutation Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.workspace.paths`" in inventory_text
    assert "workspace path and mutation implementation complete" in inventory_text


def test_harness_tools_core_does_not_expose_pi_style_module_aliases() -> None:
    module = importlib.import_module("loushang.harness.tools.core")

    pi_style_aliases = {
        "createToolDefinitionFromAgentTool",
        "wrapToolDefinition",
        "wrapToolDefinitions",
    }

    assert [name for name in sorted(pi_style_aliases) if hasattr(module, name)] == []


def test_harness_workspace_tool_pack_boundary_is_documented() -> None:
    import loushang.harness as harness

    workspace_tool_symbols = {
        "BashToolOptions",
        "ReadToolOptions",
        "ToolContext",
        "ToolsOptions",
        "create_all_tool_definitions",
        "create_read_tool_definition",
    }
    assert workspace_tool_symbols.isdisjoint(set(harness.__all__))

    design_path = Path(
        "docs/internals/architecture/harness/workspace-tool-pack-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Workspace Tool Pack Boundary",
        "`loushang.harness.tools.workspace`",
        "reusable concrete workspace tool pack",
        "builtin pack membership, default activation, and activation order",
        "`coding.control` is frozen",
        "does not import Coding or AI packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Workspace Tool Pack Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "Workspace Tool Pack" in inventory_text
    assert "reusable concrete workspace tools implemented" in inventory_text


def test_coding_internal_workspace_tool_imports_use_harness_owners() -> None:
    compatibility_paths = {
        "src/loushang/coding/__init__.py",
        "src/loushang/coding/tools/__init__.py",
        "src/loushang/coding/tools/builtins.py",
        "src/loushang/coding/tools/factory.py",
        "src/loushang/coding/tools/registry.py",
    }
    legacy_prefixes = tuple(
        f"loushang.coding.tools.{module_name}"
        for module_name in (
            "bash",
            "builtin_renderers",
            "context",
            "edit",
            "edit_diff",
            "external_tools",
            "find",
            "grep",
            "ignore",
            "ls",
            "normalize",
            "operations",
            "output_preview",
            "path_utils",
            "policy",
            "presentation",
            "process",
            "protocol",
            "read",
            "runtime",
            "truncate",
            "wrapper",
            "write",
        )
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_prefixes):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_slice1_compatibility_lifecycle_is_documented() -> None:
    text = " ".join(
        Path(
            "docs/internals/architecture/harness/slice-1-approval-tools-presentation-design.md"
        )
        .read_text(encoding="utf-8")
        .split()
    )

    required_phrases = {
        "`__module__`",
        "harness-owned classes keep their harness `__module__`",
        "coding compatibility shims preserve import paths, not class module identity",
        "Pi-style wrapper aliases stay in `loushang.coding.tools.wrapper`",
        "internal-only shims",
        "public SDK compatibility paths",
    }

    assert sorted(phrase for phrase in required_phrases if phrase not in text) == []


def test_harness_slice1_closure_status_is_documented() -> None:
    path = Path("docs/internals/architecture/harness/slice-1-status.md")
    assert path.exists()

    text = " ".join(path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Slice 1 Closure Status",
        "Current status: closed on `lane/harness`",
        "`loushang.harness.approval`",
        "`loushang.harness.tools.core`",
        "`loushang.harness.tools.contribution`",
        "`loushang.harness.presentation`",
        "Coding still owns",
        "Compatibility shims",
        "Deferred items",
        "Validation matrix",
        "runtime dynamic extension registration",
        "concrete coding tools",
        "TUI controller/render loop",
        "AI provider/model/auth",
    }

    assert sorted(phrase for phrase in required_phrases if phrase not in text) == []


def test_harness_slice2_execution_context_design_is_documented() -> None:
    path = Path(
        "docs/internals/architecture/harness/slice-2-execution-context-design.md"
    )
    assert path.exists()

    text = " ".join(path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Slice 2 Execution Context Design",
        "Slice 2A status: implementation complete for `lane/harness`",
        "Slice 2B status: eligible under the neutrality evidence gate; not yet "
        "implemented",
        "neutral execution context",
        "product execution adapter",
        "runtime dynamic extension registration",
        "`loushang.coding.tools.context.ToolContext`",
        "`ExtensionRuntimeBindings.register_tool`",
        "`ToolController.register_runtime_tool`",
        "`harness.tools.contribution`",
        "Product-owned behavior remains product-owned",
        "resolver diagnostics are advisory inputs to coding policy",
        "runtime duplicate overwrite behavior remains coding-owned",
        "No neutral execution context API is introduced by Slice 2A",
        "Deferred implementation items",
        "not import `loushang.coding`",
    }

    assert sorted(phrase for phrase in required_phrases if phrase not in text) == []

    status_paths = (
        Path("docs/internals/architecture/harness/README.md"),
        Path(
            "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
        ),
    )
    for status_path in status_paths:
        status_text = " ".join(status_path.read_text(encoding="utf-8").split())
        assert "Slice 2A" in status_text, status_path
        assert "implementation complete" in status_text, status_path
        assert "Slice 2B" in status_text, status_path
        assert "eligible under the neutrality evidence gate" in status_text, status_path


def test_harness_neutrality_evidence_gate_is_documented() -> None:
    path = Path("docs/internals/architecture/harness/refactoring-principles.md")
    text = " ".join(path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Neutrality Evidence Gate",
        "does not require a second production consumer",
        "the existing product adapter proves compatibility",
        "an independent contract probe",
        "a minimal reference adapter",
        "a product-neutral test fixture",
        "A renamed Coding fixture is not sufficient",
        "product imports, product defaults, or product-specific storage and UI semantics",
        "its absence is not a migration blocker",
    }
    assert sorted(phrase for phrase in required_phrases if phrase not in text) == []


def test_harness_dependency_first_migration_rule_is_documented() -> None:
    principles_path = Path(
        "docs/internals/architecture/harness/refactoring-principles.md"
    )
    principles_text = " ".join(principles_path.read_text(encoding="utf-8").split())
    required_principles = {
        "Dependency-First Migration Order",
        "Move `B` before `A` when `B` belongs in Harness",
        "decide ownership before considering topology",
        "strongly connected component",
        "Dependency count is evidence about leverage, not evidence about ownership",
        "Use capability-sized migration batches",
        "Do not create a separate branch or named slice for every leaf type",
        "Batch size never relaxes neutrality, dependency direction, compatibility, or test requirements",
    }
    assert (
        sorted(
            phrase for phrase in required_principles if phrase not in principles_text
        )
        == []
    )

    inventory_path = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    )
    inventory_text = " ".join(inventory_path.read_text(encoding="utf-8").split())
    required_inventory = {
        "Accelerated Dependency-First Execution",
        "Wave 1: Resource And Package Runtime",
        "Wave 2: Extension Runtime Core",
        "Wave 3: Persistence, Context, And Workflow Mechanics",
        "Wave 4: Session And Runtime Consolidation",
        "This is one capability batch",
        "The later Agent Transcript Profile wave completed this ownership transfer",
    }
    assert (
        sorted(phrase for phrase in required_inventory if phrase not in inventory_text)
        == []
    )


def test_resource_package_runtime_has_harness_owners() -> None:
    from loushang.coding.loader import (
        DefaultResourceLoader,
    )
    from loushang.coding.loader import (
        ResourceBundle as CodingResourceBundle,
    )
    from loushang.coding.package import (
        PackageMaterializer as CodingPackageMaterializer,
    )
    from loushang.coding.package import (
        PackageSourceConfig as CodingPackageSourceConfig,
    )
    from loushang.coding.plugin import PluginManager as CodingPluginManager
    from loushang.coding.policy import PolicyDecision as CodingPolicyDecision
    from loushang.harness.policy import PolicyDecision
    from loushang.harness.resources.loader import ResourceLoader
    from loushang.harness.resources.packages import (
        PackageMaterializer,
        PackageSourceConfig,
    )
    from loushang.harness.resources.plugins import PluginManager
    from loushang.harness.resources.types import ResourceBundle

    assert CodingResourceBundle is ResourceBundle
    assert CodingPackageSourceConfig is PackageSourceConfig
    assert CodingPluginManager is PluginManager
    assert CodingPolicyDecision is PolicyDecision
    assert issubclass(DefaultResourceLoader, ResourceLoader)
    assert issubclass(CodingPackageMaterializer, PackageMaterializer)


def test_coding_internal_resource_consumers_use_harness_owners() -> None:
    compatibility_paths = {
        "src/loushang/coding/loader/__init__.py",
        "src/loushang/coding/loader/types.py",
        "src/loushang/coding/package/__init__.py",
        "src/loushang/coding/package/manifest.py",
        "src/loushang/coding/package/resource_roots.py",
        "src/loushang/coding/package/source.py",
        "src/loushang/coding/plugin/__init__.py",
        "src/loushang/coding/plugin/lifecycle.py",
        "src/loushang/coding/plugin/manager.py",
        "src/loushang/coding/plugin/registry.py",
        "src/loushang/coding/plugin/resolver.py",
        "src/loushang/coding/plugin/types.py",
        "src/loushang/coding/policy/__init__.py",
        "src/loushang/coding/policy/types.py",
    }
    legacy_prefixes = (
        "loushang.coding.loader.types",
        "loushang.coding.package.manifest",
        "loushang.coding.package.resource_roots",
        "loushang.coding.package.source",
        "loushang.coding.plugin.lifecycle",
        "loushang.coding.plugin.manager",
        "loushang.coding.plugin.registry",
        "loushang.coding.plugin.resolver",
        "loushang.coding.plugin.types",
        "loushang.coding.policy.types",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for prefix in legacy_prefixes
            ):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_host_runtime_boundary_is_documented() -> None:
    design_path = Path("docs/internals/architecture/harness/host-runtime-boundary.md")
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Host Runtime Boundary",
        "implementation complete for integration into `lane/harness`",
        "`loushang.harness.host.runtime.HostRuntime`",
        "`loushang.harness.host.queue.HostInputQueue`",
        "`loushang.harness.events.OrderedEventBus`",
        "must not implement a second agent loop",
        "Coding maps running, aborting, and disposing",
        "product-neutral reference driver",
        "no host symbols are added to top-level `loushang.harness.__all__`",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Host Runtime Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "host runtime core implementation complete" in inventory_text


def test_harness_product_runtime_core_is_documented_and_adopted() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/product-runtime-core-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Product Runtime Core Boundary",
        "implementation complete for integration into `lane/harness`",
        "`ProductRuntimeBindings`",
        "`RuntimeBindingState`",
        "`BoundProductRuntimeContext`",
        "`SessionTransitionHost`",
        "`CoalescingScheduler`",
        "Candidate preparation failure leaves the previous session current",
        "Research-shaped fixture",
        "does not import AI or Product",
        "full non-live repository test suite passes",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Product Runtime Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "product runtime core implementation complete" in inventory_text
    assert "coalesced index scheduling" in inventory_text

    from loushang.ai.auth import AuthResolution
    from loushang.ai.model import ModelSelection
    from loushang.coding.control import AuthResolution as CodingAuthResolution
    from loushang.coding.extensions.runner import (
        _BoundExtensionContext,
        _RunnerContext,
    )
    from loushang.coding.extensions.types import ExtensionRuntimeBindings
    from loushang.coding.types import ModelSelection as CodingModelSelection
    from loushang.harness.runtime import (
        BoundProductRuntimeContext,
        ProductRuntimeBindings,
        UnboundProductRuntimeContext,
    )

    assert CodingModelSelection is ModelSelection
    assert CodingAuthResolution is AuthResolution
    assert issubclass(ExtensionRuntimeBindings, ProductRuntimeBindings)
    assert issubclass(_BoundExtensionContext, BoundProductRuntimeContext)
    assert issubclass(_RunnerContext, UnboundProductRuntimeContext)

    expected_imports = {
        Path("src/loushang/coding/extensions/runner.py"): {
            "loushang.harness.runtime.BoundProductRuntimeContext",
            "loushang.harness.runtime.RuntimeBindingState",
            "loushang.harness.runtime.UnboundProductRuntimeContext",
        },
        Path("src/loushang/coding/runtime/agent_session_runtime.py"): {
            "loushang.harness.runtime.CoalescingScheduler",
            "loushang.harness.runtime.SessionTransitionHost",
        },
    }
    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []


def test_host_turn_session_orchestration_core_is_documented_and_adopted() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/host-turn-session-orchestration-core.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Host Turn And Session Orchestration Core Boundary",
        "implementation complete for integration into `lane/harness`",
        "`TurnOrchestrator`",
        "`TurnInputQueue`",
        "`RetryCoordinator`",
        "`SessionOperationCoordinator`",
        "`NavigationTransactionCoordinator`",
        "prepare -> load -> discover -> commit",
        "Cancellation during candidate preparation or replacement cleans up",
        "Product retains controller policy, Product semantics, and adapters",
        "full non-live repository suite pass",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Host Turn And Session Orchestration Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert (
        "host turn and session orchestration core implementation complete"
        in inventory_text
    )

    expected_imports = {
        Path("src/loushang/coding/runtime/agent_session_runtime.py"): {
            "loushang.harness.runtime.SessionOperationCoordinator",
            "loushang.harness.runtime.stage_file_import",
        },
        Path("src/loushang/coding/session/compaction_controller.py"): {
            "loushang.harness.context.compaction.CompactionCoordinator",
        },
        Path("src/loushang/coding/session/extension_runtime_controller.py"): {
            "loushang.harness.extensions.lifecycle.ExtensionRuntimeCoordinator",
        },
        Path("src/loushang/harness/session/prompt_controller.py"): {
            "loushang.harness.host.turn.TurnOrchestrator",
        },
        Path("src/loushang/harness/session/queue_controller.py"): {
            "loushang.harness.host.turn.TurnInputQueue",
        },
        Path("src/loushang/coding/session/resource_refresh_controller.py"): {
            "loushang.harness.resources.refresh.ResourceRefreshCoordinator",
        },
        Path("src/loushang/coding/session/retry_controller.py"): {
            "loushang.harness.host.retry.RetryCoordinator",
        },
        Path("src/loushang/coding/session/tree_controller.py"): {
            "loushang.harness.runtime.NavigationTransactionCoordinator",
        },
    }
    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []

    from loushang.coding.session.resource_watcher import (
        ResourceChangeWatcher as CodingResourceChangeWatcher,
    )
    from loushang.harness import __all__ as harness_exports
    from loushang.harness.resources.watcher import ResourceChangeWatcher

    assert CodingResourceChangeWatcher is ResourceChangeWatcher
    assert "RetryCoordinator" not in harness_exports
    assert "SessionOperationCoordinator" not in harness_exports
    assert "TurnOrchestrator" not in harness_exports


def test_product_capability_composition_core_is_documented_and_adopted() -> None:
    import loushang.harness as harness
    import loushang.harness.capabilities as capabilities

    capability_symbols = {
        "CommandCatalog",
        "CommandDescriptor",
        "CommandDispatchOutcome",
        "PreparedPrompt",
        "PromptSection",
        "PromptTemplateExpander",
        "ToolActivationCoordinator",
        "ToolActivationDiff",
        "ToolActivationSnapshot",
    }
    assert capability_symbols.isdisjoint(set(harness.__all__))
    assert capabilities.__all__ == []

    design_path = Path(
        "docs/internals/architecture/harness/product-capability-composition-core.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Product Capability Composition Core Boundary",
        "Implementation complete for integration into `lane/harness`",
        "`loushang.harness.capabilities.commands`",
        "`loushang.harness.capabilities.prompt`",
        "`loushang.harness.capabilities.tools`",
        "Product supplies every section",
        "Coding and future Product adapters retain",
        "full non-live repository suite remain merge gates",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Product Capability Composition Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "Wave 5: Product Capability Composition" in inventory_text
    assert (
        "product capability composition core implementation complete" in inventory_text
    )

    expected_imports = {
        Path("src/loushang/coding/commands/catalog.py"): {
            "loushang.harness.capabilities.commands.CommandCatalog",
        },
        Path("src/loushang/coding/prompt/assembler.py"): {
            "loushang.harness.capabilities.prompt.PromptSection",
            "loushang.harness.capabilities.prompt.compose_prompt_sections",
        },
        Path("src/loushang/coding/session/command_controller.py"): {
            "loushang.harness.capabilities.commands.dispatch_command_async",
        },
        Path("src/loushang/coding/session/tool_controller.py"): {
            "loushang.harness.capabilities.tools.ToolActivationCoordinator",
        },
    }
    missing: list[str] = []
    for path, required in expected_imports.items():
        imports = set(_absolute_imports(path))
        missing.extend(
            f"{path.as_posix()} missing {name}" for name in sorted(required - imports)
        )
    assert missing == []


def test_tool_output_projection_core_is_documented_and_adopted() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/tool-output-projection-core.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Tool Output Projection Core Boundary",
        "implementation complete for integration into `lane/harness`",
        "`loushang.protocol` owns `JSONValue`",
        "`ToolOutputProjector[TDetails]`",
        "Transcript, event, and hook projections are snapshotted independently",
        "`tool_output_projection_failed`",
        "The raw unprojectable value is not copied into a journal",
        "live rendering and replay rendering consume the same result semantics",
        "In-memory and JSONL event logs enforce the same strict snapshot contract",
        "Channel envelope encoding validates the complete wire object",
        "`loushang.observability` remains a documented compatibility exception",
        "Product adapters still own tool-specific detail vocabulary",
        "Protocol -> AI -> Agent -> Harness -> Product dependency direction",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Tool Output Projection Core Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "multi-view tool-output projection core live in Agent" in inventory_text

    from loushang.agent import AgentToolResult, ToolOutputProjector
    from loushang.protocol import JSONValue, require_json_value

    assert (
        AgentToolResult.__annotations__["projector"] == "ToolOutputProjector[TDetails]"
    )
    assert ToolOutputProjector is not None
    assert require_json_value({"ok": True}) == {"ok": True}
    assert JSONValue is not None


def test_observability_json_compatibility_exception_does_not_expand() -> None:
    allowed_consumers = {
        "src/loushang/ai/errors.py",
        "src/loushang/ai/event_stream/raw_parts.py",
        "src/loushang/ai/provider/errors.py",
        "src/loushang/ai/structured.py",
        "src/loushang/ai/trace.py",
    }
    actual_consumers: set[str] = set()
    for path in Path("src/loushang").rglob("*.py"):
        if path.is_relative_to("src/loushang/observability"):
            continue
        if any(
            imported.startswith("loushang.observability.problem.")
            for imported in _absolute_imports(path)
        ):
            actual_consumers.add(path.as_posix())

    assert actual_consumers == allowed_consumers


def test_coding_internal_run_state_imports_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/session/__init__.py",
        "src/loushang/coding/session/types.py",
    }
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if imported == "loushang.coding.session.types.RunState":
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_product_kernel_ownership_is_documented() -> None:
    path = Path("docs/internals/architecture/harness/shared-capability-boundaries.md")
    text = " ".join(path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Product Kernel Ownership",
        "product goals, domain language, and completion criteria",
        "system prompt and prompt-section content",
        "skill content and default activation policy",
        "domain-specific concrete tools",
        "selection and activation policy for shared tool packs",
        "context salience, compaction, and summarization policy",
        "risk classification, approval defaults, and permission policy",
        "artifact semantics",
        "product commands, configuration defaults, and presentation projections",
        "product resource content, convention activation, additional/override roots",
        "cross-product platform defaults such as standard resource roots",
        "these semantics must not migrate merely to reduce the number of lines",
    }
    assert sorted(phrase for phrase in required_phrases if phrase not in text) == []

    readme_text = " ".join(
        Path("docs/internals/architecture/harness/README.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "product kernel that must remain product-owned" in readme_text


def test_harness_platform_resource_layout_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/platform-resource-layout-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Platform Resource Layout Boundary",
        "resource and package runtime implementation complete for integration into `lane/harness`",
        "a **platform default** is useful to every Loushang product",
        "$LOUSHANG_HOME, otherwise ~/.loushang/",
        "<workspace>/.loushang/",
        "temporary > project > user > package > built_in",
        "`AGENTS.md` is a cross-product agent-instruction convention",
        "Products own their built-in resource content and register it with Harness",
        "Resource discovery is not resource authorization",
        "`DefaultResourceLoader` is now a small Coding facade",
        "must not import Coding, Design, Research, PPT, Cowork, TUI, Method, Work, or AI provider packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Platform Resource Layout Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "Resource And Package Runtime" in inventory_text
    assert "resource and package runtime implementation complete" in inventory_text

    authoritative_text = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "docs/internals/architecture/harness/refactoring-principles.md",
            "docs/internals/architecture/harness/shared-capability-boundaries.md",
            "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md",
        )
    )
    assert (
        "resource search roots, file conventions, and compatibility formats"
        not in authoritative_text
    )
    assert "AGENTS.md or equivalent loading policy" not in authoritative_text


def test_frontmatter_consumers_use_harness_owner() -> None:
    compatibility_paths = {
        "src/loushang/coding/frontmatter.py",
        "src/loushang/resource/__init__.py",
        "src/loushang/resource/frontmatter.py",
    }
    legacy_prefixes = (
        "loushang.coding.frontmatter",
        "loushang.resource.frontmatter",
    )
    offenders: list[str] = []
    for root in (Path("src/loushang/coding"), Path("src/loushang/method")):
        for path in sorted(root.rglob("*.py")):
            if path.as_posix() in compatibility_paths:
                continue
            for imported in _absolute_imports(path):
                if imported.startswith(legacy_prefixes):
                    offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_resource_frontmatter_boundary_is_documented() -> None:
    import loushang.harness as harness

    resource_symbols = {
        "FrontmatterParseError",
        "ParsedFrontmatter",
        "parse_frontmatter",
        "strip_frontmatter",
    }
    assert resource_symbols.isdisjoint(set(harness.__all__))

    design_path = Path(
        "docs/internals/architecture/harness/resource-frontmatter-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Resource Frontmatter Boundary",
        "`loushang.harness.resources.frontmatter`",
        "Both paths re-export the same harness-owned classes and functions",
        "does not move or redesign",
        "must not import coding, method, work, TUI, AI, or provider packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Resource Frontmatter Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.resources.frontmatter`" in inventory_text
    assert "frontmatter parsing implementation complete" in inventory_text


def test_resource_provenance_consumers_use_harness_owners() -> None:
    compatibility_paths = {
        "src/loushang/coding/extensions/__init__.py",
        "src/loushang/coding/loader/__init__.py",
        "src/loushang/coding/loader/types.py",
        "src/loushang/coding/source_info.py",
    }
    legacy_symbols = (
        "loushang.coding.extensions.SourceInfo",
        "loushang.coding.extensions.types.SourceInfo",
        "loushang.coding.loader.ResourceDiagnostic",
        "loushang.coding.loader.types.ResourceDiagnostic",
        "loushang.coding.source_info.SourceInfo",
        "loushang.coding.source_info.SourceOrigin",
        "loushang.coding.source_info.SourceScope",
    )
    offenders: list[str] = []
    for path in sorted(Path("src/loushang/coding").rglob("*.py")):
        if path.as_posix() in compatibility_paths:
            continue
        for imported in _absolute_imports(path):
            if _matches_any(imported, legacy_symbols):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_harness_resource_provenance_boundary_is_documented() -> None:
    import loushang.harness as harness

    provenance_symbols = {
        "ResourceDiagnostic",
        "SourceInfo",
        "SourceOrigin",
        "SourceScope",
    }
    assert provenance_symbols.isdisjoint(set(harness.__all__))

    design_path = Path(
        "docs/internals/architecture/harness/resource-provenance-boundary.md"
    )
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Resource Provenance Boundary",
        "`loushang.harness.resources.source`",
        "`loushang.harness.resources.diagnostics`",
        "same harness-owned classes",
        "does not move or redesign",
        "must not import coding, method, work, TUI, AI, provider, or product packages",
    }
    assert (
        sorted(phrase for phrase in required_phrases if phrase not in design_text) == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Resource Provenance Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.resources.source`" in inventory_text
    assert "resource provenance implementation complete" in inventory_text


def test_harness_workspace_execution_boundary_is_documented() -> None:
    design_path = Path(
        "docs/internals/architecture/harness/workspace-execution-boundary.md"
    )
    assert design_path.exists()

    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_design_phrases = {
        "Harness Workspace Execution Boundary",
        "`loushang.harness.workspace.truncation`",
        "`loushang.harness.workspace.exec`",
        "Coding remains a product adapter",
        "Harness-owned classes keep their harness `__module__`",
        "does not introduce a neutral execution context",
    }
    assert (
        sorted(
            phrase for phrase in required_design_phrases if phrase not in design_text
        )
        == []
    )

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Workspace Execution Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.workspace.truncation`" in inventory_text
    assert "workspace execution implementation complete" in inventory_text

    coding_exec_text = Path(
        "docs/internals/architecture/coding/component-interfaces/exec.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.workspace.exec`" in coding_exec_text
    assert "compatibility" in coding_exec_text


def test_absolute_imports_include_child_aliases_from_package_import(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "src/loushang/coding/example.py",
        "from loushang import harness\n",
    )

    assert "loushang.harness" in _absolute_imports(path)


def test_harness_boundary_rejects_agent_facade_reexport(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "src/loushang/harness/example.py",
        "from loushang.agent import Agent\n",
    )

    assert _find_forbidden_imports(
        ImportBoundary(
            name="harness",
            root=tmp_path / "src/loushang/harness",
            forbidden_prefixes=("loushang.agent.Agent",),
        )
    ) == [f"harness: {path.as_posix()} imports loushang.agent.Agent"]


def test_absolute_imports_resolve_relative_imports_from_package_path(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "src/loushang/agent/example.py",
        "from ..harness import run_agent\n",
    )

    imports = _absolute_imports(path)

    assert "loushang.harness" in imports
    assert "loushang.harness.run_agent" in imports


def _write_module(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return path


def _find_forbidden_imports(boundary: ImportBoundary) -> list[str]:
    offenders: list[str] = []
    for path in sorted(boundary.root.rglob("*.py")):
        relative_path = path.as_posix()
        if relative_path in boundary.allowed_paths:
            continue
        for imported in _absolute_imports(path):
            if imported.startswith(UNRESOLVED_RELATIVE_IMPORT):
                offenders.append(
                    f"{boundary.name}: {relative_path} has unresolved relative import {imported}"
                )
            elif _matches_any(imported, boundary.forbidden_prefixes):
                offenders.append(f"{boundary.name}: {relative_path} imports {imported}")
    return offenders


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_import_from_targets(path, node))
    return imports


def _import_from_targets(path: Path, node: ast.ImportFrom) -> list[str]:
    module = _resolve_import_from_module(path, node)
    if module is None:
        return [f"{UNRESOLVED_RELATIVE_IMPORT}:{_format_import_from(node)}"]

    imports = [module]
    imports.extend(
        f"{module}.{alias.name}" for alias in node.names if alias.name != "*"
    )
    return imports


def _resolve_import_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    package_parts = _package_parts(path)
    if package_parts is None:
        return None

    ancestor_length = len(package_parts) - (node.level - 1)
    if ancestor_length <= 0:
        return None

    module_parts = package_parts[:ancestor_length]
    if node.module is not None:
        module_parts.extend(node.module.split("."))

    return ".".join(module_parts)


def _package_parts(path: Path) -> list[str] | None:
    path_parts = path.with_suffix("").parts
    src_indices = [index for index, part in enumerate(path_parts) if part == "src"]
    if not src_indices:
        return None

    package_parts = list(path_parts[src_indices[-1] + 1 : -1])
    if not package_parts:
        return None

    return package_parts


def _format_import_from(node: ast.ImportFrom) -> str:
    module = "." * node.level + (node.module or "")
    names = ", ".join(alias.name for alias in node.names)
    return f"from {module} import {names}"


def _matches_any(imported: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes
    )
