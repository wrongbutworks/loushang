from __future__ import annotations

import ast
from pathlib import Path

import loushang.ontology as ontology
import loushang.ontology.facts as ontology_facts
import loushang.ontology.storage as ontology_storage

ONTOLOGY_ROOT = Path("src/loushang/ontology")
LEGACY_FOUNDATION_PREFIXES = ("loushang.observability", "loushang.protocol")
FORBIDDEN_SYSTEM_PREFIXES = (
    "loushang.agent",
    "loushang.ai",
    "loushang.channel",
    "loushang.coding",
    "loushang.harness",
    "loushang.harnesswork",
    "loushang.harnesstui",
    "loushang.method",
    "loushang.resource",
    "loushang.runtime",
    "loushang.tui",
    "loushang.work",
)
REMOVED_COMPATIBILITY_MODULES = (
    "loushang.ontology.core",
    "loushang.ontology.fusion",
    "loushang.ontology.integrations",
    "loushang.ontology.rules",
)
REMOVED_COMPATIBILITY_SOURCES = (
    ONTOLOGY_ROOT / "core",
    ONTOLOGY_ROOT / "fusion",
    ONTOLOGY_ROOT / "integrations",
    ONTOLOGY_ROOT / "rules",
)
REMOVED_PUBLIC_NAMES = (
    "DataFusion",
    "FieldMapping",
    "ObjectStore",
    "Ontology",
    "OntologyStore",
    "OperationalMutationStore",
    "Rule",
    "RuleEngine",
    "SourceMapping",
)


def test_ontology_does_not_import_legacy_foundation_facades() -> None:
    offenders: list[str] = []
    for path in sorted(ONTOLOGY_ROOT.rglob("*.py")):
        for imported in _absolute_imports(path):
            if imported.startswith(LEGACY_FOUNDATION_PREFIXES):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_ontology_does_not_depend_on_product_or_execution_subsystems() -> None:
    offenders: list[str] = []
    for path in sorted(ONTOLOGY_ROOT.rglob("*.py")):
        for imported in _absolute_imports(path):
            if imported.startswith(FORBIDDEN_SYSTEM_PREFIXES):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_greenfield_compatibility_sources_are_absent() -> None:
    offenders: list[str] = []
    for path in REMOVED_COMPATIBILITY_SOURCES:
        if path.is_file():
            offenders.append(path.as_posix())
        elif path.is_dir():
            offenders.extend(item.as_posix() for item in path.rglob("*.py"))

    assert offenders == []


def test_public_surface_has_no_direct_mutation_or_compatibility_facades() -> None:
    assert {name for name in REMOVED_PUBLIC_NAMES if hasattr(ontology, name)} == set()
    assert not hasattr(ontology_storage, "SQLiteObjectStore")
    assert hasattr(ontology_storage, "SQLiteFactStore")
    assert hasattr(ontology_storage, "SQLiteProjectionStore")
    assert hasattr(ontology, "ProjectionStore")
    assert not hasattr(ontology_facts, "MemoryFactStore")


def test_production_ontology_does_not_import_removed_compatibility_modules() -> None:
    offenders: list[str] = []
    for path in sorted(ONTOLOGY_ROOT.rglob("*.py")):
        for imported in _absolute_imports(path):
            if imported.startswith(REMOVED_COMPATIBILITY_MODULES):
                offenders.append(f"{path.as_posix()} imports {imported}")

    assert offenders == []


def test_ontology_internal_dependency_direction() -> None:
    boundaries = (
        (
            Path("src/loushang/ontology/schema"),
            (
                "loushang.ontology.facts",
                "loushang.ontology.projection",
                "loushang.ontology.query",
                "loushang.ontology.storage",
            ),
        ),
        (
            Path("src/loushang/ontology/query"),
            (
                "loushang.ontology.facts",
                "loushang.ontology.storage",
            ),
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
            Path("src/loushang/ontology/facts"),
            (
                "loushang.ontology.projection",
                "loushang.ontology.query",
                "loushang.ontology.schema",
                "loushang.ontology.storage",
                "loushang.ontology.rules",
                "loushang.ontology.fusion",
                "loushang.ontology.integrations",
            ),
        ),
        (
            Path("src/loushang/ontology/projection"),
            (
                "loushang.ontology.query",
                "loushang.ontology.storage",
                "loushang.harnesswork",
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


def test_storage_adapters_do_not_depend_on_each_other() -> None:
    memory_imports = _absolute_imports(ONTOLOGY_ROOT / "storage" / "memory.py")
    sqlite_imports = _absolute_imports(ONTOLOGY_ROOT / "storage" / "sqlite.py")

    assert "loushang.ontology.storage.sqlite" not in memory_imports
    assert "loushang.ontology.storage.memory" not in sqlite_imports


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports
