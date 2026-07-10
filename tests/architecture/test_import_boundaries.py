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
    design_path = Path("docs/internals/architecture/harness/contribution-inventory-boundary.md")
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Contribution Inventory Boundary",
        "`loushang.harness.contributions`",
        "same harness-owned classes",
        "`surfaces_from_loaded_extension`",
        "This inventory migration moves records and indexing only",
        "must not import coding, method, work, TUI, AI, agent runtime, provider, or product packages",
    }
    assert sorted(phrase for phrase in required_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(
        encoding="utf-8"
    )
    assert "Contribution Inventory Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.contributions`" in inventory_text
    assert "contribution inventory implementation complete" in inventory_text


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

    design_path = Path("docs/internals/architecture/harness/workspace-operation-boundary.md")
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
    assert sorted(phrase for phrase in required_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(encoding="utf-8")
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

    design_path = Path("docs/internals/architecture/harness/workspace-path-mutation-boundary.md")
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
    assert sorted(phrase for phrase in required_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(encoding="utf-8")
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

    design_path = Path("docs/internals/architecture/harness/resource-frontmatter-boundary.md")
    assert design_path.exists()
    design_text = " ".join(design_path.read_text(encoding="utf-8").split())
    required_phrases = {
        "Harness Resource Frontmatter Boundary",
        "`loushang.harness.resources.frontmatter`",
        "Both paths re-export the same harness-owned classes and functions",
        "does not move or redesign",
        "must not import coding, method, work, TUI, AI, or provider packages",
    }
    assert sorted(phrase for phrase in required_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(encoding="utf-8")
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

    design_path = Path("docs/internals/architecture/harness/resource-provenance-boundary.md")
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
    assert sorted(phrase for phrase in required_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(encoding="utf-8")
    assert "Resource Provenance Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.resources.source`" in inventory_text
    assert "resource provenance implementation complete" in inventory_text


def test_harness_workspace_execution_boundary_is_documented() -> None:
    design_path = Path("docs/internals/architecture/harness/workspace-execution-boundary.md")
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
    assert sorted(phrase for phrase in required_design_phrases if phrase not in design_text) == []

    readme_text = Path("docs/internals/architecture/harness/README.md").read_text(encoding="utf-8")
    assert "Workspace Execution Boundary" in readme_text

    inventory_text = Path(
        "docs/internals/architecture/harness/coding-to-harness-migration-inventory.md"
    ).read_text(encoding="utf-8")
    assert "`loushang.harness.workspace.truncation`" in inventory_text
    assert "workspace execution implementation complete" in inventory_text

    coding_exec_text = Path("docs/internals/architecture/coding/component-interfaces/exec.md").read_text(
        encoding="utf-8"
    )
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
    return any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes)
