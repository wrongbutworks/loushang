from __future__ import annotations

from loushang.harness.resources.plugins.types import InstalledPlugin


class PluginRegistry:
    def __init__(
        self, plugins: list[InstalledPlugin] | tuple[InstalledPlugin, ...] | None = None
    ) -> None:
        self._plugins: dict[str, InstalledPlugin] = {}
        for plugin in plugins or ():
            self.register(plugin)

    def register(self, plugin: InstalledPlugin) -> InstalledPlugin:
        self._plugins[plugin.manifest.name] = plugin
        return plugin

    def unregister(self, name: str) -> InstalledPlugin | None:
        return self._plugins.pop(name, None)

    def get_plugin(self, name: str) -> InstalledPlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[InstalledPlugin]:
        return [self._plugins[name] for name in sorted(self._plugins)]

    def list_enabled_plugins(self) -> list[InstalledPlugin]:
        return [plugin for plugin in self.list_plugins() if plugin.enabled]
