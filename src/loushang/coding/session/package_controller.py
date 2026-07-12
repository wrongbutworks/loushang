from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from loushang.coding.control import SettingsManager
from loushang.coding.loader import DefaultResourceLoader
from loushang.coding.package.materializer import (
    PackageMaterializationRecord,
    PackageMaterializer,
)
from loushang.coding.package.projection import collect_package_entries
from loushang.coding.package.resource_roots import resolve_package_resource_roots
from loushang.coding.package.source import is_remote_package_source
from loushang.coding.package.source_manager import (
    PackageSourceResolver,
    configured_package_sources,
    package_source_scopes,
)
from loushang.coding.store import SessionManager
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.diagnostics import ResourceDiagnostic

SettingsManagerProvider = Callable[[], SettingsManager | None]
PackageMaterializerProvider = Callable[[], PackageMaterializer | None]
ResourceLoaderProvider = Callable[[], DefaultResourceLoader | None]
DiagnosticsServiceProvider = Callable[[], DiagnosticsService | None]
ResourceRefresh = Callable[[], None]


@dataclass
class PackageController:
    session_manager: SessionManager
    get_settings_manager: SettingsManagerProvider
    get_package_materializer: PackageMaterializerProvider
    get_resource_loader: ResourceLoaderProvider
    get_diagnostics_service: DiagnosticsServiceProvider
    refresh_resources: ResourceRefresh

    @property
    def session_id(self) -> str:
        return self.session_manager.get_session_record().session_id

    def get_packages(self, *, catalog_path: str | None = None) -> list[dict[str, object]]:
        settings_manager = self.get_settings_manager()
        if settings_manager is None:
            return []
        settings = settings_manager.get_settings()
        packages = collect_package_entries(
            package_roots=tuple(settings.package_roots),
            plugin_sources=tuple(settings.plugin_sources),
            package_sources=tuple(settings.package_sources),
            disabled_plugins=tuple(settings.disabled_plugins),
            cwd=Path(self.session_manager.get_cwd()),
            settings_manager=settings_manager,
            catalog_path=Path(catalog_path).expanduser().resolve() if catalog_path else None,
            materializer=self.get_package_materializer(),
        )
        self.record_package_projection_diagnostics(packages)
        return packages

    async def materialize_package(self, source: str) -> dict[str, object]:
        materializer = self.get_package_materializer()
        if materializer is None:
            raise RuntimeError("Package materializer is not available.")
        if not is_remote_package_source(source):
            path = Path(source).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"Package path does not exist: {path}")
            return serialize_package_materialization_record(
                PackageMaterializationRecord(
                    source=source,
                    name=path.name,
                    lifecycle="installed",
                    target_path=path,
                )
            )
        record = await materializer.materialize_remote_source(source)
        return serialize_package_materialization_record(record)

    async def install_package(self, source: str, *, scope: str = "project") -> dict[str, object]:
        record = await self.materialize_package(source)
        if record.get("lifecycle") != "installed":
            return record
        settings_manager = self.get_settings_manager()
        if settings_manager is not None:
            try:
                settings_manager.add_package_source(source, scope=scope)
            except ValueError:
                settings_manager.add_package_source(source, scope="session")
        self.refresh_package_resources()
        return record

    async def update_package(self, source: str) -> dict[str, object]:
        materializer = self.get_package_materializer()
        if materializer is None:
            raise RuntimeError("Package materializer is not available.")
        if not is_remote_package_source(source):
            return await self.materialize_package(source)
        record = await materializer.update_remote_source(source)
        self.refresh_package_resources()
        return serialize_package_materialization_record(record)

    async def update_packages(self) -> list[dict[str, object]]:
        materializer = self.get_package_materializer()
        if materializer is None:
            raise RuntimeError("Package materializer is not available.")
        await self.prepare_configured_remote_package_records()
        records = await materializer.update_all_remote_sources()
        self.refresh_package_resources()
        return [serialize_package_materialization_record(record) for record in records]

    async def check_package_updates(self) -> list[dict[str, object]]:
        materializer = self.get_package_materializer()
        if materializer is None:
            raise RuntimeError("Package materializer is not available.")
        await self.prepare_configured_remote_package_records()
        updates = await materializer.check_package_updates()
        self.record_package_update_check_diagnostics(updates)
        return updates

    def remove_package(self, source: str) -> dict[str, object]:
        materializer = self.get_package_materializer()
        if materializer is None:
            raise RuntimeError("Package materializer is not available.")
        if not is_remote_package_source(source):
            path = Path(source).expanduser().resolve()
            return serialize_package_materialization_record(
                PackageMaterializationRecord(
                    source=source,
                    name=path.name,
                    lifecycle="remote_registered",
                    target_path=path,
                )
            )
        record = materializer.remove_remote_source(source)
        return serialize_package_materialization_record(record)

    def uninstall_package(self, source: str, *, scope: str = "project") -> dict[str, object]:
        record = self.remove_package(source)
        settings_manager = self.get_settings_manager()
        if settings_manager is not None:
            try:
                settings_manager.remove_package_source(source, scope=scope)
            except ValueError:
                settings_manager.remove_package_source(source, scope="session")
        materializer = self.get_package_materializer()
        if materializer is not None:
            materializer.forget_remote_source(source)
        self.refresh_package_resources()
        return record

    def refresh_package_resources(self) -> None:
        if self.get_resource_loader() is None:
            return
        self.configure_package_resource_roots()
        self.refresh_resources()

    async def prepare_configured_remote_package_records(self) -> None:
        settings_manager = self.get_settings_manager()
        materializer = self.get_package_materializer()
        if settings_manager is None or materializer is None:
            return
        PackageSourceResolver(
            settings_manager=settings_manager,
            materializer=materializer,
            diagnostics_service=self.get_diagnostics_service(),
            session_id=self.session_id,
        ).prepare_configured_remote_records()

    def record_package_projection_diagnostics(self, packages: list[dict[str, object]]) -> None:
        diagnostics_service = self.get_diagnostics_service()
        if diagnostics_service is None:
            return
        records = []
        for package in packages:
            for diagnostics_key, default_code, default_message, source_kind in (
                (
                    "manifestDiagnostics",
                    "invalid_package_manifest",
                    "Package manifest diagnostic.",
                    "external_package",
                ),
                ("catalogDiagnostics", "invalid_package_catalog", "Package catalog diagnostic.", None),
                (
                    "conflictDiagnostics",
                    "package_version_conflict",
                    "Package version conflict.",
                    "external_package",
                ),
            ):
                diagnostics = package.get(diagnostics_key)
                if not isinstance(diagnostics, tuple | list):
                    continue
                for diagnostic in diagnostics:
                    if not isinstance(diagnostic, dict):
                        continue
                    path = diagnostic.get("path")
                    diagnostic_details = {
                        "package_source": str(package.get("source") or ""),
                        "package_name": str(package.get("name") or ""),
                        "package_kind": str(package.get("packageKind") or package.get("kind") or ""),
                    }
                    conflict_versions = diagnostic.get("conflictVersions")
                    if isinstance(conflict_versions, tuple | list):
                        diagnostic_details["conflict_versions"] = [str(version) for version in conflict_versions]
                    records.append(
                        diagnostics_service.normalize_resource_diagnostic(
                            ResourceDiagnostic(
                                code=str(diagnostic.get("code") or default_code),
                                message=str(diagnostic.get("message") or default_message),
                                source_path=Path(path) if isinstance(path, str) else None,
                                resource_type="package",
                                source_kind=source_kind,
                            ),
                            details=diagnostic_details,
                            phase="resource_loading",
                            source="package",
                            session_id=self.session_id,
                        )
                    )
        diagnostics_service.record_many(records)

    def record_package_update_check_diagnostics(self, updates: list[dict[str, object]]) -> None:
        diagnostics_service = self.get_diagnostics_service()
        if diagnostics_service is None:
            return
        for update in updates:
            if update.get("status") != "check_failed":
                continue
            diagnostics_service.capture_failure(
                code="package_update_check_failed",
                error=str(update.get("reason") or "Package update check failed."),
                phase="runtime",
                source="package",
                level="warning",
                session_id=self.session_id,
                details={
                    "package_source": str(update.get("source") or ""),
                    "package_name": str(update.get("name") or ""),
                    "current_commit": str(update.get("currentCommit") or ""),
                    "installed_commit": str(update.get("installedCommit") or ""),
                    "resolved_commit": str(update.get("resolvedCommit") or ""),
                    "requested_ref": str(update.get("requestedRef") or ""),
                    "available_ref": str(update.get("availableRef") or ""),
                    "dirty": bool(update.get("dirty")),
                    "pinned": bool(update.get("pinned")),
                },
            )

    def configure_package_resource_roots(self) -> None:
        resource_loader = self.get_resource_loader()
        settings_manager = self.get_settings_manager()
        materializer = self.get_package_materializer()
        if resource_loader is None or settings_manager is None:
            return
        if materializer is not None:
            settings = settings_manager.get_settings()
            resolved = resolve_package_resource_roots(
                package_roots=settings.package_roots,
                plugin_sources=settings.plugin_sources,
                package_sources=configured_package_sources(settings_manager),
                materializer=materializer,
                package_source_scopes=package_source_scopes(settings_manager),
                global_base_dir=settings_manager.global_base_dir,
                project_base_dir=settings_manager.project_base_dir,
                disabled_plugins=settings.disabled_plugins,
                diagnostics_service=self.get_diagnostics_service(),
                session_id=self.session_id,
            )
            resource_loader.set_package_roots(resolved.roots, resolved.filters)
        set_user_resource_roots = getattr(resource_loader, "set_user_resource_roots", None)
        if callable(set_user_resource_roots):
            from loushang.coding.bootstrap import _resolve_user_resource_roots

            global_resource_roots = tuple(settings_manager.get_global_settings().get("resource_roots", ()))
            user_roots, explicit_roots = _resolve_user_resource_roots(
                global_resource_roots,
                global_base_dir=settings_manager.global_base_dir,
            )
            set_user_resource_roots(user_roots, explicit_roots=explicit_roots)


def serialize_package_materialization_record(record: PackageMaterializationRecord) -> dict[str, object]:
    return {
        "source": record.source,
        "name": record.name,
        "lifecycle": record.lifecycle,
        "targetPath": str(record.target_path),
        "errorMessage": record.error_message,
        "security": record.security,
        "pinned": record.pinned,
        "requestedRef": record.requested_ref,
        "resolvedCommit": record.resolved_commit,
        "installedCommit": record.installed_commit,
        "dirty": record.dirty,
        "lastUpdatedAt": record.last_updated_at,
        "sourceType": record.source_type,
        "requirement": record.requirement,
        "resolvedName": record.resolved_name,
        "resolvedVersion": record.resolved_version,
        "installer": record.installer,
        "installedDistributions": list(record.installed_distributions),
    }
