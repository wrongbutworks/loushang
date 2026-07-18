from __future__ import annotations

from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.packages.catalog import (
    PackageCatalogDiagnostic,
    PackageCatalogEntry,
)
from loushang.harness.resources.packages.catalog_diagnostics import (
    PackageCatalogDiagnosticsRecorder,
)
from loushang.harness.resources.types import PackageResourceSummary


def test_catalog_diagnostics_recorder_keeps_typed_catalog_details(tmp_path) -> None:
    manifest_path = tmp_path / "package.json"
    catalog_path = tmp_path / "catalog.json"
    entry = PackageCatalogEntry(
        name="review-pack",
        kind="remote_package",
        scope="project",
        version="1.0.0",
        source="https://example.test/review-pack.git",
        path=tmp_path,
        enabled=True,
        summary=PackageResourceSummary(source_root=tmp_path),
        manifest_diagnostics=(
            {
                "code": "invalid_package_manifest",
                "message": "Manifest is invalid.",
                "path": str(manifest_path),
            },
        ),
        catalog_diagnostics=(
            PackageCatalogDiagnostic(
                code="invalid_package_catalog",
                message="Catalog is invalid.",
                path=str(catalog_path),
            ),
        ),
        conflict_diagnostics=(
            PackageCatalogDiagnostic(
                code="package_version_conflict",
                message="Versions conflict.",
                path=str(tmp_path),
                conflict_versions=("1.0.0", "2.0.0"),
            ),
        ),
    )
    service = DiagnosticsService()

    PackageCatalogDiagnosticsRecorder(service, session_id="session-1").record([entry])

    manifest = service.get_diagnostics(code="invalid_package_manifest")[0]
    catalog = service.get_diagnostics(code="invalid_package_catalog")[0]
    conflict = service.get_diagnostics(code="package_version_conflict")[0]
    assert manifest.source_path == manifest_path
    assert catalog.source_path == catalog_path
    assert conflict.details["conflict_versions"] == ["1.0.0", "2.0.0"]
    assert conflict.details["package_name"] == "review-pack"
    assert conflict.session_id == "session-1"
