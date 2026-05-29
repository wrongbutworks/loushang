from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loushang.coding.loader import DefaultResourceLoader
from loushang.coding.package.manifest import resolve_package_manifest
from loushang.coding.package.materializer import PackageMaterializer
from loushang.coding.package.source import PackageSourceConfig, is_remote_package_source, package_source_match_key, remote_package_name
from loushang.coding.plugin.manager import PluginManager


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
    entries: list[dict[str, object]] = []
    scoped_package_roots, scoped_plugin_sources, scoped_package_sources = _scoped_package_sources(
        settings_manager,
        package_roots=package_roots,
        plugin_sources=plugin_sources,
        package_sources=package_sources,
    )
    for root, scope in scoped_package_roots:
        package_root = Path(root).expanduser().resolve()
        summary = _summarize_package_root(package_root, cwd)
        entries.append(
            _package_entry(
                name=package_root.name,
                kind="package_root",
                package_kind="local_package_root",
                scope=scope,
                version="",
                source=package_root,
                path=package_root,
                enabled=True,
                summary=summary,
            )
        )

    manager = PluginManager(disabled_plugins=disabled_plugins)
    for package_source, scope in scoped_package_sources:
        source = package_source.source
        if is_remote_package_source(source):
            entries.append(
                remote_package_entry(
                    source=source,
                    scope=scope,
                    cwd=cwd,
                    materializer=materializer,
                    package_source=package_source,
                )
            )
            continue
        package_root = _resolve_scoped_local_package_source(
            source,
            scope,
            cwd=cwd,
            settings_manager=settings_manager,
        )
        summary = _summarize_package_root(package_root, cwd, package_source=package_source)
        entry = _package_entry(
            name=package_root.name,
            kind="package_root",
            package_kind="local_package_root",
            scope=scope,
            version="",
            source=package_root,
            path=package_root,
            enabled=True,
            summary=summary,
        )
        entry["filtered"] = package_source.filtered
        entries.append(entry)

    for source, scope in scoped_plugin_sources:
        if is_remote_package_source(source):
            entries.append(remote_package_entry(source=source, scope=scope, cwd=cwd, materializer=materializer))
            continue
        plugin = manager.add_plugin_source(source)
        package_root = plugin.manifest.package_root or plugin.manifest.root
        summary = _empty_package_summary(package_root) if not plugin.enabled else _summarize_package_root(package_root, cwd)
        entries.append(
            _package_entry(
                name=plugin.manifest.name,
                kind="plugin",
                package_kind="plugin_package",
                scope=scope,
                version=plugin.manifest.version or "",
                source=plugin.source.path,
                path=package_root,
                enabled=plugin.enabled,
                summary=summary,
            )
        )
    entries.extend(_load_catalog_entries(catalog_path))
    return _mark_package_conflicts(entries)


def remote_package_entry(
    *,
    source: str,
    scope: str,
    cwd: Path | None = None,
    materializer: PackageMaterializer | None = None,
    package_source: PackageSourceConfig | None = None,
) -> dict[str, object]:
    record = materializer.get_record(source) if materializer is not None else None
    lifecycle = record.lifecycle if record is not None else "remote_registered"
    path = str(record.target_path) if record is not None else ""
    security = record.security if record is not None else "allowed"
    install_path = Path(path) if path else Path()
    manifest = resolve_package_manifest(install_path, installed=lifecycle == "installed")
    summary_root = manifest.package_root if path else install_path
    summary = _empty_package_summary(summary_root) if not path else _remote_package_summary(
        path=summary_root,
        cwd=cwd,
        installed=lifecycle == "installed",
        package_source=package_source,
    )
    entry = {
        "name": remote_package_name(source),
        "kind": "remote_plugin",
        "packageKind": "remote_package",
        "scope": scope,
        "version": manifest.version,
        "source": source,
        "path": path,
        "enabled": lifecycle == "installed",
        "prompts": int(getattr(summary, "prompt_count", 0) if not isinstance(summary, dict) else summary.get("prompt_count", 0)),
        "skills": int(getattr(summary, "skill_count", 0) if not isinstance(summary, dict) else summary.get("skill_count", 0)),
        "extensions": int(
            getattr(summary, "extension_count", 0) if not isinstance(summary, dict) else summary.get("extension_count", 0)
        ),
        "themes": int(getattr(summary, "theme_count", 0) if not isinstance(summary, dict) else summary.get("theme_count", 0)),
        "diagnostics": int(
            getattr(summary, "diagnostic_count", 0) if not isinstance(summary, dict) else summary.get("diagnostic_count", 0)
        )
        + len(manifest.diagnostics),
        "lifecycle": lifecycle,
        "security": security,
        "pinned": record.pinned if record is not None else False,
        "requestedRef": record.requested_ref if record is not None else "",
        "resolvedCommit": record.resolved_commit if record is not None else "",
        "installedCommit": record.installed_commit if record is not None else "",
        "dirty": record.dirty if record is not None else False,
        "lastUpdatedAt": record.last_updated_at if record is not None else "",
        "filtered": package_source.filtered if package_source is not None else False,
        "description": "",
    }
    if record is not None:
        entry.update(
            {
                "sourceType": record.source_type,
                "requirement": record.requirement or "",
                "resolvedName": record.resolved_name or "",
                "resolvedVersion": record.resolved_version or "",
                "installer": record.installer or "",
                "installedDistributions": list(record.installed_distributions),
            }
        )
    if path and manifest.package_root != manifest.root:
        entry["packageRoot"] = str(manifest.package_root)
    if manifest.diagnostics:
        entry["manifestDiagnostics"] = manifest.diagnostics
    return entry


remote_plugin_entry = remote_package_entry


def _remote_package_summary(
    *,
    path: Path,
    cwd: Path | None,
    installed: bool,
    package_source: PackageSourceConfig | None = None,
) -> object:
    if not installed or not path.is_dir():
        return _empty_package_summary(path)
    return _summarize_package_root(path, cwd or path, package_source=package_source)


def _load_catalog_entries(catalog_path: Path | None) -> list[dict[str, object]]:
    if catalog_path is None:
        return []
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            _catalog_diagnostic_entry(
                catalog_path,
                code="invalid_package_catalog",
                message=f"Invalid package catalog JSON: {exc.msg}",
            )
        ]
    except Exception as exc:  # noqa: BLE001
        return [
            _catalog_diagnostic_entry(
                catalog_path,
                code="unreadable_package_catalog",
                message=f"Package catalog could not be read: {exc}",
            )
        ]
    items = payload.get("packages") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return [
            _catalog_diagnostic_entry(
                catalog_path,
                code="invalid_package_catalog",
                message="Package catalog must be a list or an object with a packages list.",
            )
        ]
    entries: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        version = item.get("version")
        source = item.get("source", item.get("url", ""))
        entries.append(
            {
                "name": name,
                "kind": "catalog",
                "packageKind": "catalog_package",
                "scope": "catalog",
                "version": version if isinstance(version, str) else "",
                "source": source if isinstance(source, str) else "",
                "path": "",
                "enabled": False,
                "prompts": _nonnegative_int(item.get("prompts")),
                "skills": _nonnegative_int(item.get("skills")),
                "extensions": _nonnegative_int(item.get("extensions")),
                "themes": _nonnegative_int(item.get("themes")),
                "diagnostics": 0,
                "description": item.get("description") if isinstance(item.get("description"), str) else "",
            }
        )
    return entries


def _catalog_diagnostic_entry(catalog_path: Path, *, code: str, message: str) -> dict[str, object]:
    diagnostic = {
        "code": code,
        "message": message,
        "path": str(catalog_path),
    }
    return {
        "name": catalog_path.name,
        "kind": "catalog",
        "packageKind": "catalog_package",
        "scope": "catalog",
        "version": "",
        "source": str(catalog_path),
        "path": str(catalog_path),
        "enabled": False,
        "prompts": 0,
        "skills": 0,
        "extensions": 0,
        "themes": 0,
        "diagnostics": 1,
        "description": "",
        "catalogDiagnostics": (diagnostic,),
    }


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _mark_package_conflicts(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    by_name: dict[str, set[str]] = {}
    for entry in entries:
        name = str(entry.get("name", ""))
        if not name:
            continue
        by_name.setdefault(name, set()).add(str(entry.get("version", "")))
    for entry in entries:
        name = str(entry.get("name", ""))
        versions = sorted(version for version in by_name.get(name, set()) if version)
        if len(versions) > 1:
            entry["version_conflict"] = True
            entry["versionConflict"] = True
            entry["conflictVersions"] = versions
            entry["conflict_versions"] = versions
            entry["conflictDiagnostics"] = (
                {
                    "code": "package_version_conflict",
                    "message": f"Package '{name}' has multiple configured versions: {', '.join(versions)}.",
                    "path": str(entry.get("path") or entry.get("source") or ""),
                    "packageName": name,
                    "conflictVersions": versions,
                },
            )
    return entries


def _scoped_package_sources(
    settings_manager: Any | None,
    *,
    package_roots: tuple[str, ...],
    plugin_sources: tuple[str, ...],
    package_sources: tuple[PackageSourceConfig, ...],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[PackageSourceConfig, str]]]:
    scoped_package_roots: list[tuple[str, str]] = []
    scoped_plugin_sources: list[tuple[str, str]] = []
    scoped_package_sources: list[tuple[PackageSourceConfig, str]] = []
    raw_scoped_package_sources: list[tuple[PackageSourceConfig, str]] = []
    seen_package_source_keys: set[str] = set()
    if settings_manager is not None:
        for method_name, scope in (
            ("get_global_settings", "user"),
            ("get_project_settings", "project"),
            ("get_session_settings", "session"),
        ):
            getter = getattr(settings_manager, method_name, None)
            if not callable(getter):
                continue
            patch = getter()
            if not isinstance(patch, dict):
                continue
            scoped_package_roots.extend((value, scope) for value in _string_values(patch.get("package_roots")))
            scoped_plugin_sources.extend((value, scope) for value in _string_values(patch.get("plugin_sources")))
            for value in _package_source_values(patch.get("packages", patch.get("package_sources"))):
                raw_scoped_package_sources.append((value, scope))
        for value, scope in sorted(raw_scoped_package_sources, key=lambda item: _package_source_scope_rank(item[1])):
            source_key = _scoped_package_source_match_key(value.source, scope, settings_manager)
            if source_key in seen_package_source_keys:
                continue
            seen_package_source_keys.add(source_key)
            scoped_package_sources.append((value, scope))
    if not scoped_package_sources:
        scoped_package_sources.extend((value, "merged") for value in package_sources)
    if not scoped_package_roots and not scoped_plugin_sources and not scoped_package_sources:
        return (
            [(value, "merged") for value in package_roots],
            [(value, "merged") for value in plugin_sources],
            [],
        )
    return scoped_package_roots, scoped_plugin_sources, scoped_package_sources


def _package_source_scope_rank(scope: str) -> int:
    return {"project": 0, "user": 1, "session": 2}.get(scope, 3)


def _resolve_scoped_local_package_source(
    source: str,
    scope: str,
    *,
    cwd: Path,
    settings_manager: Any | None,
) -> Path:
    path = Path(source).expanduser()
    if path.is_absolute():
        return path.resolve()
    base_dir: Path | None = None
    if scope == "user":
        base_dir = _settings_base_dir(settings_manager, "global_base_dir")
    elif scope == "project":
        base_dir = _settings_base_dir(settings_manager, "project_base_dir")
    if base_dir is None:
        base_dir = cwd
    return (base_dir / path).resolve()


def _scoped_package_source_match_key(source: str, scope: str, settings_manager: Any | None) -> str:
    if is_remote_package_source(source):
        return package_source_match_key(source)
    path = Path(source).expanduser()
    if path.is_absolute():
        return f"local:{path.resolve()}"
    base_dir: Path | None = None
    if scope == "user":
        base_dir = _settings_base_dir(settings_manager, "global_base_dir")
    elif scope == "project":
        base_dir = _settings_base_dir(settings_manager, "project_base_dir")
    if base_dir is None:
        return package_source_match_key(source)
    return f"local:{(base_dir / path).resolve()}"


def _settings_base_dir(settings_manager: Any | None, attr: str) -> Path | None:
    value = getattr(settings_manager, attr, None)
    if value is None:
        return None
    return Path(value).expanduser().resolve()


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _package_source_values(value: object) -> list[PackageSourceConfig]:
    if not isinstance(value, list | tuple):
        return []
    sources: list[PackageSourceConfig] = []
    for item in value:
        if isinstance(item, str):
            sources.append(PackageSourceConfig(source=item))
        elif isinstance(item, dict) and isinstance(item.get("source"), str):
            sources.append(
                PackageSourceConfig(
                    source=item["source"],
                    extensions=_tuple_or_none(item.get("extensions")),
                    skills=_tuple_or_none(item.get("skills")),
                    prompts=_tuple_or_none(item.get("prompts")),
                    themes=_tuple_or_none(item.get("themes")),
                )
            )
    return sources


def _tuple_or_none(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list | tuple):
        return None
    return tuple(item for item in value if isinstance(item, str))


def _summarize_package_root(
    package_root: Path,
    cwd: Path,
    *,
    package_source: PackageSourceConfig | None = None,
) -> object:
    filters = {package_root: package_source} if package_source is not None else None
    loader = DefaultResourceLoader(package_roots=(package_root,), package_source_filters=filters)
    loader.discover_resources(cwd)
    summaries = loader.get_package_resource_summaries()
    if summaries:
        return summaries[0]
    return _empty_package_summary(package_root)


def _empty_package_summary(package_root: Path) -> dict[str, object]:
    return {
        "source_root": package_root,
        "prompt_count": 0,
        "skill_count": 0,
        "extension_count": 0,
        "theme_count": 0,
        "diagnostic_count": 0,
    }


def _package_entry(
    *,
    name: str,
    kind: str,
    package_kind: str,
    scope: str,
    version: str,
    source: object,
    path: object,
    enabled: bool,
    summary: object,
) -> dict[str, object]:
    return {
        "name": name,
        "kind": kind,
        "packageKind": package_kind,
        "scope": scope,
        "version": version,
        "source": str(source),
        "path": str(path),
        "enabled": enabled,
        "prompts": int(getattr(summary, "prompt_count", 0) if not isinstance(summary, dict) else summary.get("prompt_count", 0)),
        "skills": int(getattr(summary, "skill_count", 0) if not isinstance(summary, dict) else summary.get("skill_count", 0)),
        "extensions": int(
            getattr(summary, "extension_count", 0) if not isinstance(summary, dict) else summary.get("extension_count", 0)
        ),
        "themes": int(getattr(summary, "theme_count", 0) if not isinstance(summary, dict) else summary.get("theme_count", 0)),
        "diagnostics": int(
            getattr(summary, "diagnostic_count", 0) if not isinstance(summary, dict) else summary.get("diagnostic_count", 0)
        ),
    }
