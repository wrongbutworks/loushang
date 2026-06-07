from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.package.manifest import resolve_package_manifest
from loushang.coding.package.materializer import PackageMaterializer
from loushang.coding.package.source import PackageSourceConfig, is_remote_package_source
from loushang.coding.plugin import PluginManager


@dataclass(frozen=True)
class ResolvedPackageResourceRoots:
    roots: tuple[str, ...] = ()
    filters: dict[Path, PackageSourceConfig] = field(default_factory=dict)


def resolve_package_resource_roots(
    *,
    package_roots: tuple[str, ...],
    plugin_sources: tuple[str, ...],
    package_sources: tuple[PackageSourceConfig, ...],
    materializer: PackageMaterializer,
    package_source_scopes: dict[str, str] | None = None,
    global_base_dir: str | Path | None = None,
    project_base_dir: str | Path | None = None,
    disabled_plugins: tuple[str, ...] = (),
    diagnostics_service: DiagnosticsService | None = None,
    session_id: str | None = None,
) -> ResolvedPackageResourceRoots:
    roots: list[str] = []
    filters: dict[Path, PackageSourceConfig] = {}
    for root in package_roots:
        _append_package_root(roots, root)
    manager = PluginManager(disabled_plugins=disabled_plugins)
    for source in plugin_sources:
        if is_remote_package_source(source):
            record = materializer.get_record(source)
            if record is not None and record.lifecycle == "installed":
                _append_package_root(roots, resolve_package_manifest(record.target_path).package_root)
            continue
        try:
            plugin = manager.add_plugin_source(source)
        except Exception as exc:  # noqa: BLE001
            _record_plugin_source_diagnostic(
                diagnostics_service,
                source=source,
                exc=exc,
                session_id=session_id,
            )
            continue
        if plugin.enabled:
            _append_package_root(roots, plugin.manifest.package_root or plugin.manifest.root)
    for package_source in package_sources:
        if is_remote_package_source(package_source.source):
            record = materializer.get_record(package_source.source)
            if record is None or record.lifecycle != "installed":
                continue
            root = resolve_package_manifest(record.target_path).package_root
        else:
            scope = (package_source_scopes or {}).get(package_source.source)
            root = _resolve_local_package_source(
                package_source.source,
                scope=scope,
                global_base_dir=global_base_dir,
                project_base_dir=project_base_dir,
            )
        _append_package_root(roots, root)
        filters[Path(root).expanduser().resolve()] = package_source
    return ResolvedPackageResourceRoots(roots=tuple(roots), filters=filters)


def _append_package_root(roots: list[str], root: str | Path) -> None:
    normalized = str(Path(root).expanduser().resolve())
    if normalized not in roots:
        roots.append(normalized)


def _resolve_local_package_source(
    source: str,
    *,
    scope: str | None,
    global_base_dir: str | Path | None,
    project_base_dir: str | Path | None,
) -> Path:
    path = Path(source).expanduser()
    if path.is_absolute():
        return path.resolve()
    base: str | Path | None = None
    if scope in {"user", "global"}:
        base = global_base_dir
    elif scope == "project":
        base = project_base_dir
    if base is None:
        return path.resolve()
    return (Path(base).expanduser() / path).resolve()


def _record_plugin_source_diagnostic(
    diagnostics_service: DiagnosticsService | None,
    *,
    source: str,
    exc: Exception,
    session_id: str | None,
) -> None:
    if diagnostics_service is None:
        return
    diagnostics_service.capture_failure(
        code="plugin_source_unresolved",
        error=exc,
        phase="startup",
        source="bootstrap",
        level="warning",
        session_id=session_id,
        details={"plugin_source": source, "exception_type": type(exc).__name__},
    )
