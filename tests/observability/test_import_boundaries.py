from __future__ import annotations

import ast
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loushang" / "observability"


def test_observability_package_uses_only_stdlib_and_relative_imports() -> None:
    assert PACKAGE_ROOT.exists()

    failures: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root not in sys.stdlib_module_names:
                        failures.append(f"{path.relative_to(PACKAGE_ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if not node.module:
                    continue
                root = node.module.split(".", 1)[0]
                if root not in sys.stdlib_module_names:
                    failures.append(f"{path.relative_to(PACKAGE_ROOT)} imports {node.module}")

    assert failures == []
