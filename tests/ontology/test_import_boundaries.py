from __future__ import annotations

import ast
from pathlib import Path

ONTOLOGY_ROOT = Path("src/loushang/ontology")
LEGACY_FOUNDATION_PREFIXES = ("loushang.observability", "loushang.protocol")


def test_ontology_does_not_import_legacy_foundation_facades() -> None:
    offenders: list[str] = []
    for path in sorted(ONTOLOGY_ROOT.rglob("*.py")):
        for imported in _absolute_imports(path):
            if imported.startswith(LEGACY_FOUNDATION_PREFIXES):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_ontology_internal_dependency_direction() -> None:
    boundaries = (
        (
            Path("src/loushang/ontology/schema"),
            (
                "loushang.ontology.core",
                "loushang.ontology.query",
                "loushang.ontology.storage",
            ),
        ),
        (
            Path("src/loushang/ontology/query"),
            ("loushang.ontology.storage",),
        ),
        (
            Path("src/loushang/ontology/storage"),
            (
                "loushang.ontology.query",
                "loushang.ontology.rules",
                "loushang.ontology.fusion",
                "loushang.ontology.integrations",
                "loushang.harnesswork",
            ),
        ),
        (
            Path("src/loushang/ontology/facts/model.py"),
            (
                "loushang.ontology.core",
                "loushang.ontology.query",
                "loushang.ontology.storage",
                "loushang.ontology.rules",
                "loushang.ontology.fusion",
                "loushang.ontology.integrations",
            ),
        ),
        (
            Path("src/loushang/ontology/facts/store.py"),
            (
                "loushang.ontology.core",
                "loushang.ontology.query",
                "loushang.ontology.storage",
                "loushang.ontology.rules",
                "loushang.ontology.fusion",
                "loushang.ontology.integrations",
            ),
        ),
        (
            Path("src/loushang/ontology/facts/projection.py"),
            (
                "loushang.ontology.query",
                "loushang.ontology.storage",
                "loushang.ontology.rules",
                "loushang.ontology.fusion",
                "loushang.ontology.integrations",
            ),
        ),
    )
    offenders: list[str] = []
    for root, forbidden_prefixes in boundaries:
        paths = (root,) if root.is_file() else tuple(sorted(root.rglob("*.py")))
        for path in paths:
            for imported in _absolute_imports(path):
                if imported.startswith(forbidden_prefixes):
                    offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports
