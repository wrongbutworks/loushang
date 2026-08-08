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


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports
