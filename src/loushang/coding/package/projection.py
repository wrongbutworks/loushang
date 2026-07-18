from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.coding.loader import DefaultResourceLoader
from loushang.harness.resources.packages.catalog import (
    PackageCatalogBuilder,
    PackageCatalogDiagnostic,
    PackageCatalogEntry,
    empty_package_summary,
    package_catalog_sources,
)
from loushang.harness.resources.packages.materializer import PackageMaterializer
from loushang.harness.resources.packages.source import PackageSourceConfig
from loushang.harness.resources.types import PackageResourceSummary


def collect_package_entries(
    *,
    package_roots: tuple[str, ...],
    plugin_sources: tuple[str, ...],
    disabled_plugins: tuple[str, ...],
    cwd: Path,
    package_sources: tuple[PackageSourceConfig, ...] = (),
    settings_manager: Any | None = None,
    catalog_path: Path | None = None,
    materializer: PackageMaterializer | None = None,
) -> list[dict[str, object]]:
    """Project the shared package catalog into Coding's CLI/RPC wire schema."""

    builder = PackageCatalogBuilder(summary_provider=_summarize_coding_package_root)
    entries = builder.collect(
        sources=package_catalog_sources(
            settings_manager,
            package_roots=package_roots,
            plugin_sources=plugin_sources,
            package_sources=package_sources,
        ),
        disabled_plugins=disabled_plugins,
        cwd=cwd,
        catalog_path=catalog_path,
        materializer=materializer,
    )
    return [_coding_package_entry(entry) for entry in entries]


def remote_package_entry(
    *,
    source: str,
    scope: str,
    cwd: Path | None = None,
    materializer: PackageMaterializer | None = None,
    package_source: PackageSourceConfig | None = None,
) -> dict[str, object]:
    """Project one shared remote-package catalog entry for Coding callers."""

    entry = PackageCatalogBuilder(
        summary_provider=_summarize_coding_package_root
    ).remote_package_entry(
        source=source,
        scope=scope,  # type: ignore[arg-type]
        cwd=cwd,
        materializer=materializer,
        package_source=package_source,
    )
    return _coding_package_entry(entry)


remote_plugin_entry = remote_package_entry


def _summarize_coding_package_root(
    package_root: Path,
    cwd: Path,
    package_source: PackageSourceConfig | None,
) -> PackageResourceSummary:
    filters: dict[str | Path, PackageSourceConfig] | None = (
        {package_root: package_source} if package_source is not None else None
    )
    loader = DefaultResourceLoader(
        package_roots=(package_root,), package_source_filters=filters
    )
    loader.discover_resources(cwd)
    summaries = loader.get_package_resource_summaries()
    return summaries[0] if summaries else empty_package_summary(package_root)


def _coding_package_entry(entry: PackageCatalogEntry) -> dict[str, object]:
    summary = entry.summary
    package_kind = {
        "package_root": "local_package_root",
        "plugin": "plugin_package",
        "remote_package": "remote_package",
        "catalog": "catalog_package",
    }[entry.kind]
    kind = "remote_plugin" if entry.kind == "remote_package" else entry.kind
    payload: dict[str, object] = {
        "name": entry.name,
        "kind": kind,
        "packageKind": package_kind,
        "scope": entry.scope,
        "version": entry.version,
        "source": entry.source,
        "path": str(entry.path) if entry.path is not None else "",
        "enabled": entry.enabled,
        "prompts": summary.prompt_count,
        "skills": summary.skill_count,
        "extensions": summary.extension_count,
        "themes": summary.theme_count,
        "diagnostics": summary.diagnostic_count
        + len(entry.manifest_diagnostics)
        + len(entry.catalog_diagnostics),
        "description": entry.description,
    }
    if entry.lifecycle is not None:
        payload.update(
            {
                "lifecycle": entry.lifecycle,
                "security": entry.security or "allowed",
                "pinned": entry.pinned,
                "requestedRef": entry.requested_ref or "",
                "resolvedCommit": entry.resolved_commit or "",
                "installedCommit": entry.installed_commit or "",
                "dirty": entry.dirty,
                "lastUpdatedAt": entry.last_updated_at or "",
                "filtered": entry.filtered,
            }
        )
    elif entry.filtered:
        payload["filtered"] = True
    if entry.source_type is not None:
        payload.update(
            {
                "sourceType": entry.source_type,
                "requirement": entry.requirement or "",
                "resolvedName": entry.resolved_name or "",
                "resolvedVersion": entry.resolved_version or "",
                "installer": entry.installer or "",
                "installedDistributions": list(entry.installed_distributions),
            }
        )
    if entry.package_root is not None:
        payload["packageRoot"] = str(entry.package_root)
    if entry.manifest_diagnostics:
        payload["manifestDiagnostics"] = entry.manifest_diagnostics
    if entry.catalog_diagnostics:
        payload["catalogDiagnostics"] = tuple(
            _coding_catalog_diagnostic(diagnostic)
            for diagnostic in entry.catalog_diagnostics
        )
    if entry.has_version_conflict:
        versions = list(entry.conflict_versions)
        payload.update(
            {
                "version_conflict": True,
                "versionConflict": True,
                "conflictVersions": versions,
                "conflict_versions": versions,
                "conflictDiagnostics": tuple(
                    _coding_catalog_diagnostic(diagnostic)
                    for diagnostic in entry.conflict_diagnostics
                ),
            }
        )
    return payload


def _coding_catalog_diagnostic(
    diagnostic: PackageCatalogDiagnostic,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "path": diagnostic.path,
    }
    if diagnostic.package_name is not None:
        payload["packageName"] = diagnostic.package_name
    if diagnostic.conflict_versions:
        payload["conflictVersions"] = list(diagnostic.conflict_versions)
    return payload
