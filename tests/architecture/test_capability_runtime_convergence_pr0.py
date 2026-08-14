from __future__ import annotations

import ast
import re
from collections import defaultdict
from functools import cache
from pathlib import Path

BASELINE_PATH = Path(
    "docs/internals/architecture/harness/capability-runtime-convergence-pr0-baseline.md"
)
PLAN_PATH = Path(
    "docs/internals/architecture/harness/capability-runtime-convergence-plan.md"
)
README_PATH = Path("docs/internals/architecture/harness/README.md")
SOURCE_ROOT = Path("src/loushang")
HARNESS_ROOT = Path("src/loushang/harness")
CAPABILITIES_ROOT = HARNESS_ROOT / "capabilities"

REQUIRED_ROWS = {
    "SUR": 28,
    "COMP": 11,
    "CALL": 6,
    "OWN": 9,
    "FAULT": 14,
}

ACCEPTED_GRAPH_OWNERS: dict[str, tuple[Path, ...]] = {
    "RuntimeCapabilityGraphPlanner": (CAPABILITIES_ROOT,),
    "RuntimeCapabilityGraphBinder": (CAPABILITIES_ROOT,),
    "RuntimeCapabilityGraphRuntime": (CAPABILITIES_ROOT,),
    "RuntimeCapabilityGraphProjector": (CAPABILITIES_ROOT,),
}

FORBIDDEN_RUNTIME_SYMBOLS = frozenset(
    {
        "EffectiveRuntimeSnapshot",
        "GlobalCapabilityRegistry",
        "GlobalCapabilityProviderRegistry",
        "GlobalCapabilityGraph",
        "GlobalCapabilityContainer",
        "GlobalCapabilityContext",
    }
)

GRAPH_API_SYMBOLS = frozenset(
    {
        "RuntimeCapabilityGraphPlanner",
        "RuntimeCapabilityGraphBinder",
        "RuntimeCapabilityGraphRuntime",
        "RuntimeCapabilityGraphProjector",
    }
)

BROAD_PARAMETER_NAMES = frozenset(
    {"context", "runtime", "bindings", "services", "container"}
)


@cache
def _python_trees() -> dict[Path, ast.Module]:
    return {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in SOURCE_ROOT.rglob("*.py")
    }


def _class_definitions(
    trees: dict[Path, ast.Module],
) -> dict[str, list[tuple[Path, ast.ClassDef]]]:
    definitions: dict[str, list[tuple[Path, ast.ClassDef]]] = defaultdict(list)
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                definitions[node.name].append((path, node))
    return definitions


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _annotation_name(annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        prefix = _annotation_name(annotation.value)
        return annotation.attr if prefix is None else f"{prefix}.{annotation.attr}"
    return None


def _subscript_items(annotation: ast.Subscript) -> tuple[ast.expr, ...]:
    if isinstance(annotation.slice, ast.Tuple):
        return tuple(annotation.slice.elts)
    return (annotation.slice,)


def _is_broad_annotation(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return True
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            parsed = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return False
        return _is_broad_annotation(parsed)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _is_broad_annotation(annotation.left) or _is_broad_annotation(
            annotation.right
        )

    name = _annotation_name(annotation)
    if name is not None:
        return name.rsplit(".", maxsplit=1)[-1] in {
            "Any",
            "Mapping",
            "MutableMapping",
            "dict",
            "object",
        }
    if not isinstance(annotation, ast.Subscript):
        return False

    container = _annotation_name(annotation.value)
    if container is None:
        return False
    container = container.rsplit(".", maxsplit=1)[-1]
    items = _subscript_items(annotation)
    if container in {"Optional", "Union"}:
        return any(_is_broad_annotation(item) for item in items)
    if container == "Annotated":
        return bool(items) and _is_broad_annotation(items[0])
    if container in {"Mapping", "MutableMapping", "dict"}:
        return len(items) != 2 or _is_broad_annotation(items[1])
    return False


def test_pr0_inventory_keeps_required_rows_and_evidence() -> None:
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
        assert path.is_file(), f"missing PR0 evidence file: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_name in functions, (
            f"missing PR0 evidence function: {raw_path}::{function_name}"
        )


def test_pr0_baseline_is_linked_from_the_plan_and_harness_catalog() -> None:
    link = "capability-runtime-convergence-pr0-baseline.md"
    assert link in PLAN_PATH.read_text(encoding="utf-8")
    assert link in README_PATH.read_text(encoding="utf-8")


def test_accepted_graph_contracts_have_one_declared_package_owner() -> None:
    definitions = _class_definitions(_python_trees())

    for symbol, owners in ACCEPTED_GRAPH_OWNERS.items():
        locations = [path for path, _node in definitions.get(symbol, [])]
        assert len(locations) <= 1, (
            f"duplicate convergence contract {symbol}: {locations}"
        )
        assert all(
            any(_is_relative_to(path, owner) for owner in owners) for path in locations
        ), (
            f"{symbol} must be owned by one of {owners}, found {locations}"
        )

    legacy_runtime_locations = [
        path for path, _node in definitions.get("CapabilityCompositionRuntime", [])
    ]
    assert legacy_runtime_locations == [
        Path("src/loushang/harness/capabilities/composition_runtime.py")
    ]

    forbidden = {
        symbol: [
            path
            for path, _node in definitions[symbol]
            if _is_relative_to(path, HARNESS_ROOT)
        ]
        for symbol in FORBIDDEN_RUNTIME_SYMBOLS
        if any(
            _is_relative_to(path, HARNESS_ROOT)
            for path, _node in definitions.get(symbol, [])
        )
    }
    assert forbidden == {}

    accepted_graph_managers = {
        "RuntimeCapabilityGraphRuntime",
        "RuntimeCapabilityGraphProjector",
    }
    duplicate_graph_managers = {
        symbol: [path for path, _node in locations]
        for symbol, locations in definitions.items()
        if symbol.endswith(("GraphRuntime", "GraphProjector"))
        and symbol not in accepted_graph_managers
        and any(_is_relative_to(path, CAPABILITIES_ROOT) for path, _node in locations)
    }
    assert duplicate_graph_managers == {}


def test_target_graph_apis_reject_broad_service_locator_parameters() -> None:
    definitions = _class_definitions(_python_trees())
    violations: list[str] = []

    for symbol in GRAPH_API_SYMBOLS:
        for path, class_node in definitions.get(symbol, []):
            for node in class_node.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                parameters = (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                    *(() if node.args.vararg is None else (node.args.vararg,)),
                    *(() if node.args.kwarg is None else (node.args.kwarg,)),
                )
                for parameter in parameters:
                    if parameter.arg in BROAD_PARAMETER_NAMES and _is_broad_annotation(
                        parameter.annotation
                    ):
                        annotation = (
                            "<unannotated>"
                            if parameter.annotation is None
                            else ast.unparse(parameter.annotation)
                        )
                        violations.append(
                            f"{path}:{node.lineno} "
                            f"{symbol}.{node.name}({parameter.arg}: "
                            f"{annotation})"
                        )

    assert violations == []


def test_broad_annotation_syntax_gate_covers_obvious_locator_shapes() -> None:
    broad = (
        "object",
        "'object'",
        "Any",
        "typing.Optional[object]",
        "Union[None, Mapping[str, Any]]",
        "None | object",
        "Annotated[object, 'runtime services']",
        "dict[str, object]",
    )
    narrow = (
        "WorkspaceContext",
        "Mapping[str, WorkspaceFacet]",
        "tuple[CapabilityRequirement, ...]",
    )

    assert all(_is_broad_annotation(ast.parse(value, mode="eval").body) for value in broad)
    assert not any(
        _is_broad_annotation(ast.parse(value, mode="eval").body) for value in narrow
    )
