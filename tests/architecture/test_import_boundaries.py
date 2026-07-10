from __future__ import annotations

import ast
import importlib
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
                "loushang.ai",
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
            allowed_paths=frozenset({"src/loushang/work/coding.py"}),
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
                "loushang.coding",
                "loushang.method",
                "loushang.tui",
            ),
        ),
    )

    offenders: list[str] = []
    for boundary in boundaries:
        offenders.extend(_find_forbidden_imports(boundary))

    assert offenders == []


def test_legacy_agent_harness_package_has_been_removed() -> None:
    assert not Path("src/loushang/agent/harness").exists()


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


def test_harness_tools_core_does_not_expose_pi_style_module_aliases() -> None:
    module = importlib.import_module("loushang.harness.tools.core")

    pi_style_aliases = {
        "createToolDefinitionFromAgentTool",
        "wrapToolDefinition",
        "wrapToolDefinitions",
    }

    assert [name for name in sorted(pi_style_aliases) if hasattr(module, name)] == []


def test_harness_slice1_compatibility_lifecycle_is_documented() -> None:
    text = " ".join(
        Path("docs/internals/architecture/harness/slice-1-approval-tools-presentation-design.md")
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
    path = Path("docs/internals/architecture/harness/slice-2-execution-context-design.md")
    assert path.exists()

    text = " ".join(path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Slice 2 Execution Context Design",
        "Slice 2A status: implementation complete for `lane/harness`",
        "Slice 2B status: gated pending a second product consumer",
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
        Path("docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"),
    )
    for status_path in status_paths:
        status_text = " ".join(status_path.read_text(encoding="utf-8").split())
        assert "Slice 2A" in status_text, status_path
        assert "implementation complete" in status_text, status_path
        assert "Slice 2B" in status_text, status_path
        assert "gated pending a second product consumer" in status_text, status_path


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
    return any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes)
