from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loushang.coding.plugin.types import InstalledPlugin, PluginManifest, PluginResolvedResources, PluginSource
from loushang.coding.plugin.lifecycle import is_remote_plugin_source, remote_plugin_name


class PluginResolver:
    """Resolve local plugin directories into resource-loader package roots."""

    def resolve_plugin(self, source: PluginSource | str | Path) -> InstalledPlugin:
        plugin_source = source if isinstance(source, PluginSource) else _plugin_source_from_input(source)
        if plugin_source.kind == "remote":
            url = plugin_source.url or ""
            name = remote_plugin_name(url)
            manifest = PluginManifest(
                name=name,
                root=Path(),
                enabled=False,
                metadata={"source": url, "lifecycle": "remote_registered", "security": "allowed"},
            )
            return InstalledPlugin(manifest=manifest, source=plugin_source, enabled=False)
        if plugin_source.path is None:
            raise ValueError("Local plugin source requires a path.")
        root = plugin_source.path.expanduser().resolve()
        manifest = self._read_manifest(root, source_enabled=plugin_source.enabled)
        return InstalledPlugin(
            manifest=manifest,
            source=PluginSource(path=root, enabled=plugin_source.enabled),
            enabled=plugin_source.enabled and manifest.enabled,
        )

    def resolve_resources(self, plugin: InstalledPlugin) -> PluginResolvedResources:
        if not plugin.enabled:
            return PluginResolvedResources(plugin=plugin, package_roots=())
        package_root = plugin.manifest.package_root or plugin.manifest.root
        return PluginResolvedResources(plugin=plugin, package_roots=(package_root,))

    def _read_manifest(self, root: Path, *, source_enabled: bool) -> PluginManifest:
        if not root.is_dir():
            raise FileNotFoundError(f"Plugin source is not a directory: {root}")

        manifest_path = root / "plugin.json"
        if not manifest_path.is_file():
            return PluginManifest(name=root.name, root=root, enabled=source_enabled, package_root=root)

        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid plugin manifest JSON: {manifest_path}: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"Plugin manifest must be a JSON object: {manifest_path}")

        name = _string_value(raw.get("name")) or root.name
        version = _string_value(raw.get("version"))
        enabled = bool(raw.get("enabled", True)) and source_enabled
        package_root = _package_root(root, raw)
        return PluginManifest(
            name=name,
            root=root,
            version=version,
            enabled=enabled,
            package_root=package_root,
            metadata=dict(raw),
        )


def _package_root(root: Path, raw: dict[str, Any]) -> Path:
    value = raw.get("packageRoot", raw.get("package_root", "."))
    if not isinstance(value, str) or not value:
        return root
    return (root / value).expanduser().resolve()


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _plugin_source_from_input(source: str | Path) -> PluginSource:
    if isinstance(source, str) and is_remote_plugin_source(source):
        return PluginSource(url=source, kind="remote")
    return PluginSource(path=Path(source))
