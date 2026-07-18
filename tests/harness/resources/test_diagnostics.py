from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


def test_resource_diagnostic_preserves_neutral_provenance() -> None:
    from loushang.harness.resources.diagnostics import ResourceDiagnostic

    source_path = Path("/tmp/package/skills/review/SKILL.md")
    diagnostic = ResourceDiagnostic(
        code="invalid_frontmatter",
        message="Frontmatter must be a mapping.",
        source_path=source_path,
        resource_id="review",
        resource_type="skill",
        source_kind="external_package",
        metadata={"line": 2},
    )

    assert diagnostic.source_path is source_path
    assert diagnostic.source_kind == "external_package"
    assert diagnostic.metadata == {"line": 2}


def test_resource_diagnostic_has_immutable_empty_metadata() -> None:
    from loushang.harness.resources.diagnostics import ResourceDiagnostic

    diagnostic = ResourceDiagnostic(code="missing_resource", message="Missing resource.")

    assert diagnostic.metadata == {}
    with pytest.raises(TypeError):
        diagnostic.metadata["path"] = "/tmp/missing"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        diagnostic.code = "changed"  # type: ignore[misc]
