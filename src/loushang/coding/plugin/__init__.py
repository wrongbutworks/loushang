from loushang.coding.plugin.lifecycle import is_remote_plugin_source, remote_plugin_name
from loushang.coding.plugin.manager import PluginManager
from loushang.coding.plugin.materializer import (
    GitPackageMaterializerBackend,
    PackageMaterializationLifecycle,
    PackageMaterializationRecord,
    PackageMaterializer,
    PackageMaterializerBackend,
    PackageSourcePolicy,
)
from loushang.coding.plugin.registry import PluginRegistry
from loushang.coding.plugin.resolver import PluginResolver
from loushang.coding.plugin.types import (
    InstalledPlugin,
    PluginManifest,
    PluginResolvedResources,
    PluginSource,
)

__all__ = [
    "InstalledPlugin",
    "GitPackageMaterializerBackend",
    "PluginManager",
    "PluginManifest",
    "PluginRegistry",
    "PluginResolvedResources",
    "PluginResolver",
    "PluginSource",
    "PackageMaterializationLifecycle",
    "PackageMaterializationRecord",
    "PackageMaterializer",
    "PackageMaterializerBackend",
    "PackageSourcePolicy",
    "is_remote_plugin_source",
    "remote_plugin_name",
]
