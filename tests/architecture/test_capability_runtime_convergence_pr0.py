from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

BASELINE_PATH = Path(
    "docs/internals/architecture/harness/capability-runtime-convergence-pr0-baseline.md"
)
PLAN_PATH = Path(
    "docs/internals/architecture/harness/capability-runtime-convergence-plan.md"
)
README_PATH = Path("docs/internals/architecture/harness/README.md")
SOURCE_ROOT = Path("src/loushang")

REQUIRED_ROWS = {
    "SUR": 28,
    "COMP": 11,
    "CALL": 6,
    "OWN": 9,
    "FAULT": 14,
}

TARGET_OWNERS: dict[str, tuple[Path, ...]] = {
    "RegistrationOwner": (Path("src/loushang/harness/runtime/registration.py"),),
    "RegistrationIdentity": (
        Path("src/loushang/harness/runtime/registration.py"),
    ),
    "RegistrationDisposalResult": (
        Path("src/loushang/harness/runtime/registration.py"),
    ),
    "RegistrationScope": (Path("src/loushang/harness/runtime/registration.py"),),
    "CapabilityDefinition": (Path("src/loushang/harness/capabilities"),),
    "CapabilityRequirement": (Path("src/loushang/harness/capabilities"),),
    "RuntimeCapabilityGraphPlanner": (Path("src/loushang/harness/capabilities"),),
    "RuntimeCapabilityGraphBinder": (Path("src/loushang/harness/capabilities"),),
    "RuntimeCapabilityGraphRuntime": (Path("src/loushang/harness/capabilities"),),
    "RuntimeCapabilityGraphProjector": (
        Path("src/loushang/harness/capabilities"),
    ),
    "MountedCapability": (Path("src/loushang/harness/capabilities"),),
    "MountGraphSnapshot": (Path("src/loushang/harness/capabilities"),),
    "EffectiveRuntimeView": (Path("src/loushang/harness/capabilities"),),
    "PreparedModelRequest": (Path("src/loushang/ai"),),
    "ModelInputSnapshot": (
        Path("src/loushang/harness/transcript"),
        Path("src/loushang/harness/session"),
    ),
}

FORBIDDEN_RUNTIME_SYMBOLS = frozenset(
    {
        "EffectiveRuntimeSnapshot",
        "CapabilityProviderRegistry",
        "GlobalCapabilityRegistry",
        "GlobalCapabilityGraph",
        "CapabilityContainer",
        "CapabilityContext",
    }
)

GRAPH_API_SYMBOLS = frozenset(
    {
        "CapabilityDefinition",
        "CapabilityRequirement",
        "RuntimeCapabilityGraphPlanner",
        "RuntimeCapabilityGraphBinder",
        "RuntimeCapabilityGraphRuntime",
        "RuntimeCapabilityGraphProjector",
    }
)

BROAD_PARAMETER_NAMES = frozenset(
    {"context", "runtime", "bindings", "services", "container"}
)


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


def _is_broad_annotation(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    normalized = ast.unparse(annotation).replace(" ", "")
    if normalized.startswith("Optional[") and normalized.endswith("]"):
        normalized = normalized.removeprefix("Optional[").removesuffix("]")
    normalized = normalized.removesuffix("|None")
    return normalized in {
        "object",
        "Mapping[str,object]",
        "dict[str,object]",
        "collections.abc.Mapping[str,object]",
        "typing.Mapping[str,object]",
    }


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


def test_convergence_contracts_have_one_declared_package_owner() -> None:
    definitions = _class_definitions(_python_trees())

    for symbol, owners in TARGET_OWNERS.items():
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
        symbol: [path for path, _node in definitions[symbol]]
        for symbol in FORBIDDEN_RUNTIME_SYMBOLS
        if definitions.get(symbol)
    }
    assert forbidden == {}

    accepted_graph_managers = {
        "RuntimeCapabilityGraphRuntime",
        "RuntimeCapabilityGraphProjector",
    }
    duplicate_graph_managers = {
        symbol: [path for path, _node in locations]
        for symbol, locations in definitions.items()
        if "Capability" in symbol
        and symbol.endswith(("GraphRuntime", "GraphProjector"))
        and symbol not in accepted_graph_managers
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
                )
                for parameter in parameters:
                    if parameter.arg in BROAD_PARAMETER_NAMES and _is_broad_annotation(
                        parameter.annotation
                    ):
                        violations.append(
                            f"{path}:{node.lineno} "
                            f"{symbol}.{node.name}({parameter.arg}: "
                            f"{ast.unparse(parameter.annotation)})"
                        )

    assert violations == []
