from __future__ import annotations

import ast
from pathlib import Path

import pytest

import loushang.ai.model as model_module

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "src/loushang/ai/model"
PROVIDER_DIRS = (
    REPO_ROOT / "src/loushang/ai/providers",
    REPO_ROOT / "src/loushang/ai/contrib",
)
REMOVED_MODULE = "compat" + "_schema"


def test_removed_model_schema_module_is_not_public() -> None:
    assert not (MODEL_DIR / f"{REMOVED_MODULE}.py").exists()
    assert not hasattr(model_module, REMOVED_MODULE)
    assert REMOVED_MODULE not in model_module.__all__


def test_core_model_package_does_not_export_removed_names() -> None:
    removed = {
        "Com" + "pat",
        "Support" + "Status",
        "Endpoint" + "ProtocolFeatures",
        "Endpoint" + "WireDialect",
    }

    assert removed.isdisjoint(set(model_module.__all__))
    for name in removed:
        assert not hasattr(model_module, name)


@pytest.mark.parametrize("root", PROVIDER_DIRS)
def test_provider_code_does_not_import_removed_model_schema(root: Path) -> None:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(_removed_schema_imports(path.relative_to(REPO_ROOT), tree))

    assert offenders == []


def _removed_schema_imports(relative_path: Path, tree: ast.AST) -> list[str]:
    full_module = f"loushang.ai.model.{REMOVED_MODULE}"
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == full_module:
                    offenders.append(f"{relative_path} imports removed model schema")
        elif isinstance(node, ast.ImportFrom):
            if node.module == full_module:
                offenders.append(f"{relative_path} imports removed model schema")
            if node.module == "loushang.ai.model":
                for alias in node.names:
                    if alias.name == REMOVED_MODULE:
                        offenders.append(
                            f"{relative_path} imports removed model schema via package"
                        )
    return offenders
