from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.coding.resource_runtime import CodingResourceLoader
from loushang.harness.resources.packages.catalog import (
    PackageCatalogBuilder,
    PackageCatalogEntry,
    empty_package_summary,
    package_catalog_sources,
)
from loushang.harness.resources.packages.materializer import PackageMaterializer
from loushang.harness.resources.packages.projection import (
    project_package_entries,
    project_package_entry,
)
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

    return project_package_entries(
        collect_coding_package_catalog(
            package_roots=package_roots,
            plugin_sources=plugin_sources,
            disabled_plugins=disabled_plugins,
            cwd=cwd,
            package_sources=package_sources,
            settings_manager=settings_manager,
            catalog_path=catalog_path,
            materializer=materializer,
        )
    )


def collect_coding_package_catalog(
    *,
    package_roots: tuple[str, ...],
    plugin_sources: tuple[str, ...],
    disabled_plugins: tuple[str, ...],
    cwd: Path,
    package_sources: tuple[PackageSourceConfig, ...] = (),
    settings_manager: Any | None = None,
    catalog_path: Path | None = None,
    materializer: PackageMaterializer | None = None,
) -> tuple[PackageCatalogEntry, ...]:
    """Collect typed package records using Coding's resource summary policy."""

    builder = PackageCatalogBuilder(summary_provider=_summarize_coding_package_root)
    return builder.collect(
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
    return project_package_entry(entry)


remote_plugin_entry = remote_package_entry


def _summarize_coding_package_root(
    package_root: Path,
    cwd: Path,
    package_source: PackageSourceConfig | None,
) -> PackageResourceSummary:
    filters: dict[str | Path, PackageSourceConfig] | None = (
        {package_root: package_source} if package_source is not None else None
    )
    loader = CodingResourceLoader(
        package_roots=(package_root,), package_source_filters=filters
    )
    loader.discover_resources(cwd)
    summaries = loader.get_package_resource_summaries()
    return summaries[0] if summaries else empty_package_summary(package_root)
