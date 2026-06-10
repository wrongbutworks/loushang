from __future__ import annotations

from pathlib import Path


def test_method_package_does_not_import_coding_product_modules() -> None:
    method_root = Path("src/loushang/method")

    offenders = []
    for path in sorted(method_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "loushang.coding" in text:
            offenders.append(path.as_posix())

    assert offenders == []
