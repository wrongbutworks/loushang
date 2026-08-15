from __future__ import annotations

import ast
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

BASELINE_PATH = Path(
    "docs/internals/architecture/harness/"
    "composition-lifecycle-authority-cla0-baseline.md"
)
PLAN_PATH = Path(
    "docs/internals/architecture/harness/composition-lifecycle-authority-plan.md"
)
README_PATH = Path("docs/internals/architecture/harness/README.md")
CATALOG_PATH = Path("docs/internals/architecture/harness/capability-catalog.md")
CATALOG_GENERATOR_PATH = Path("scripts/generate_harness_capability_catalog.py")
SOURCE_ROOT = Path("src/loushang")

REQUIRED_ROWS = {
    "AUTH": 15,
    "ENTRY": 5,
    "SLOT": 10,
    "ORDER": 6,
}

EXPECTED_CONSTRUCTION_SITES = {
    "RuntimeCapabilityGraphRuntime": {
        (
            Path("src/loushang/harness/session/model_call.py"),
            "SessionModelCallRuntime.__init__",
        ),
    },
    "RuntimeCapabilityGraphBinder": {
        (
            Path("src/loushang/harness/session/model_call.py"),
            "SessionModelCallRuntime.__init__",
        ),
    },
    "RuntimeCapabilityGraphProjector": {
        (
            Path("src/loushang/harness/session/model_call.py"),
            "SessionModelCallPreparer.__init__",
        ),
        (
            Path("src/loushang/harness/session/model_call.py"),
            "SessionModelCallRuntime._projector",
        ),
    },
    "RuntimeProfileBinder": {
        (
            Path("src/loushang/coding/continuity.py"),
            "bind_coding_continuity",
        ),
        (
            Path("src/loushang/harness/capabilities/composition_runtime.py"),
            "bind_capability_composition_runtime",
        ),
        (
            Path("src/loushang/harness/transcript/runtime_profile.py"),
            "AgentTranscriptProfileRuntime.__init__",
        ),
    },
    "CapabilityCompositionRuntime": {
        (
            Path("src/loushang/harness/capabilities/composition_runtime.py"),
            "bind_capability_composition_runtime",
        ),
    },
}

EXPECTED_COMPOSITION_BIND_CALLERS = {
    (
        Path("src/loushang/coding/bootstrap.py"),
        "<module>",
    ),
    (
        Path("src/loushang/coding/runtime_capability_admission.py"),
        "CodingCapabilityProfileResolution.bind",
    ),
    (
        Path("src/loushang/coding/session/agent_session.py"),
        "AgentSession.__init__",
    ),
}
TRACKED_CALL_SYMBOLS = frozenset(
    {
        *EXPECTED_CONSTRUCTION_SITES,
        "bind_capability_composition_runtime",
        "_publish_generation",
    }
)
GUARDED_IMPORT_SYMBOLS = frozenset(
    {*EXPECTED_CONSTRUCTION_SITES, "bind_capability_composition_runtime"}
)


@cache
def _source_trees() -> dict[Path, ast.Module]:
    return {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in SOURCE_ROOT.rglob("*.py")
    }


def _call_name(value: ast.expr) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


class _ScopedCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self._scope: list[str] = []
        self.sites: dict[str, list[str]] = {
            symbol: [] for symbol in TRACKED_CALL_SYMBOLS
        }

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        symbol = _call_name(node.func)
        if symbol in self.sites:
            self.sites[symbol].append(".".join(self._scope) or "<module>")
        self.generic_visit(node)


@cache
def _tracked_call_sites() -> dict[str, set[tuple[Path, str]]]:
    sites: dict[str, set[tuple[Path, str]]] = {
        symbol: set() for symbol in TRACKED_CALL_SYMBOLS
    }
    for path, tree in _source_trees().items():
        visitor = _ScopedCallVisitor()
        visitor.visit(tree)
        for symbol, scopes in visitor.sites.items():
            sites[symbol].update((path, scope) for scope in scopes)
    return sites


def _construction_sites(symbol: str) -> set[tuple[Path, str]]:
    return _tracked_call_sites()[symbol]


def _method_node(
    path: Path,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = _source_trees()[path]
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    )


def test_cla0_baseline_keeps_required_rows_and_test_evidence() -> None:
    text = BASELINE_PATH.read_text(encoding="utf-8")

    for prefix, count in REQUIRED_ROWS.items():
        actual = re.findall(rf"^\| ({prefix}-\d{{2}}) \|", text, re.MULTILINE)
        expected = [f"{prefix}-{index:02d}" for index in range(1, count + 1)]
        assert actual == expected

    evidence_references = sorted(
        set(re.findall(r"`(tests/[\w./-]+\.py)::(test_[\w]+)`", text))
    )
    assert evidence_references
    for raw_path, function_name in evidence_references:
        path = Path(raw_path)
        assert path.is_file(), f"missing CLA0 evidence file: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_name in functions, (
            f"missing CLA0 evidence function: {raw_path}::{function_name}"
        )


def test_cla0_baseline_is_linked_from_plan_and_harness_index() -> None:
    link = "composition-lifecycle-authority-cla0-baseline.md"
    assert link in PLAN_PATH.read_text(encoding="utf-8")
    assert link in README_PATH.read_text(encoding="utf-8")


def test_graph_and_profile_construction_sites_match_cla0_allowlist() -> None:
    aliased_imports = {
        (path, alias.name, alias.asname)
        for path, tree in _source_trees().items()
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in GUARDED_IMPORT_SYMBOLS
        and alias.asname not in {None, alias.name}
    }
    assert aliased_imports == set()

    for symbol, expected in EXPECTED_CONSTRUCTION_SITES.items():
        assert _construction_sites(symbol) == expected


def test_composition_binding_entrypoint_families_match_cla0_allowlist() -> None:
    assert (
        _construction_sites("bind_capability_composition_runtime")
        == EXPECTED_COMPOSITION_BIND_CALLERS
    )


def test_current_entrypoint_construction_counts_are_frozen() -> None:
    managed = _method_node(
        Path("src/loushang/harness/session/bootstrap_construction.py"),
        "AgentProductConstructionBinding",
        "construct",
    )
    managed_calls = [
        _call_name(node.func)
        for node in ast.walk(managed)
        if isinstance(node, ast.Call)
    ]
    assert managed_calls.count("bind_capabilities") == 1
    assert managed_calls.count("bind_session_capabilities") == 1

    direct = _method_node(
        Path("src/loushang/coding/session/agent_session.py"),
        "AgentSession",
        "__init__",
    )
    fallback = next(
        node
        for node in ast.walk(direct)
        if isinstance(node, ast.IfExp)
        and {
            _call_name(call.func)
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        }
        == {
            "bind_coding_capability_composition_runtime",
            "bind_capability_composition_runtime",
        }
    )
    assert isinstance(fallback, ast.IfExp)

    model_call = _method_node(
        Path("src/loushang/harness/session/model_call.py"),
        "SessionModelCallRuntime",
        "__init__",
    )
    model_calls = [
        _call_name(node.func)
        for node in ast.walk(model_call)
        if isinstance(node, ast.Call)
    ]
    assert model_calls.count("RuntimeCapabilityGraphRuntime") == 1
    assert model_calls.count("RuntimeCapabilityGraphBinder") == 1

    extension_candidate = _method_node(
        Path("src/loushang/harness/extensions/runner.py"),
        "ExtensionRunner",
        "prepare_generation",
    )
    candidate_calls = [
        _call_name(node.func)
        for node in ast.walk(extension_candidate)
        if isinstance(node, ast.Call)
    ]
    assert candidate_calls.count("ExtensionRunner") == 1


def test_extension_generation_has_one_private_publication_entrypoint() -> None:
    assert _construction_sites("_publish_generation") == {
        (
            Path("src/loushang/harness/extensions/runner.py"),
            "PreparedExtensionGeneration.publish",
        )
    }
    publish = _method_node(
        Path("src/loushang/harness/extensions/runner.py"),
        "ExtensionRunner",
        "_publish_generation",
    )
    assert (
        sum(
            1
            for node in ast.walk(publish)
            if isinstance(node, ast.Call) and _call_name(node.func) == "commit_resource"
        )
        == 1
    )


def test_graph_binder_reuse_and_validation_precede_provider_construction() -> None:
    bind = _method_node(
        Path("src/loushang/harness/capabilities/graph_binding.py"),
        "RuntimeCapabilityGraphBinder",
        "bind",
    )
    call_lines: dict[str, list[int]] = {}
    for node in ast.walk(bind):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name is not None:
            call_lines.setdefault(name, []).append(node.lineno)

    construct_line = min(call_lines["construct"])
    assert max(call_lines["_index_bindings"]) < construct_line
    assert max(call_lines["_binding_signatures"]) < construct_line
    assert max(call_lines["_assembly_fingerprint"]) < construct_line

    reuse_checks = [
        node
        for node in ast.walk(bind)
        if isinstance(node, ast.Compare)
        and (
            "assembly_fingerprint == assembly_fingerprint" in ast.unparse(node)
            or "previous.binding_signature == signature" in ast.unparse(node)
        )
    ]
    assert len(reuse_checks) == 2
    assert all(node.lineno < construct_line for node in reuse_checks)


def test_generated_catalog_distinguishes_source_complete_from_mounted() -> None:
    result = subprocess.run(
        [sys.executable, str(CATALOG_GENERATOR_PATH), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    statuses = dict(
        re.findall(
            r"^\| `([\w.]+)` \| `([\w-]+)`(?:<br>[^|]+)? \|",
            catalog,
            re.MULTILINE,
        )
    )
    assert statuses == {
        "harness.model_input": "production-mounted",
        "harness.workspace": "source-complete",
    }
