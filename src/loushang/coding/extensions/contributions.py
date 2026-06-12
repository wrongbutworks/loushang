from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loushang.coding.loader import ResourceDiagnostic

ExtensionSurfaceType = Literal[
    "command",
    "tool",
    "prompt",
    "skill",
    "hook",
    "model_provider",
    "ui",
    "autocomplete",
    "resource_root",
]


@dataclass(frozen=True)
class ExtensionSurfaceDescriptor:
    type: ExtensionSurfaceType
    name: str
    extension_id: str
    source_path: Path
    active: bool = True
    priority: int = 0
    permission_requirements: tuple[str, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class DuplicateExtensionSurfaceKeyError(KeyError):
    def __init__(self, surface_type: str, name: str, surfaces: list[ExtensionSurfaceDescriptor]) -> None:
        super().__init__(f"Duplicate extension surface key: {surface_type}:{name}")
        self.surface_type = surface_type
        self.contribution_type = surface_type
        self.name = name
        self.surfaces = list(surfaces)
        self.contributions = list(surfaces)


@dataclass
class ExtensionInventory:
    _surfaces: list[ExtensionSurfaceDescriptor] = field(default_factory=list)
    _by_type: dict[str, list[ExtensionSurfaceDescriptor]] = field(default_factory=lambda: defaultdict(list))
    _by_extension: dict[str, list[ExtensionSurfaceDescriptor]] = field(default_factory=lambda: defaultdict(list))
    _by_key: dict[tuple[str, str], list[ExtensionSurfaceDescriptor]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def from_extensions(cls, extensions: Iterable[object]) -> "ExtensionInventory":
        inventory = cls()
        for extension in extensions:
            for surface in getattr(extension, "surfaces", getattr(extension, "contributions", ())):
                inventory.add(surface)
        return inventory

    def add(self, surface: ExtensionSurfaceDescriptor) -> None:
        self._surfaces.append(surface)
        self._by_type[surface.type].append(surface)
        self._by_extension[surface.extension_id].append(surface)
        self._by_key[(surface.type, surface.name)].append(surface)

    def all(self) -> list[ExtensionSurfaceDescriptor]:
        return list(self._surfaces)

    def by_type(self, surface_type: str) -> list[ExtensionSurfaceDescriptor]:
        return list(self._by_type.get(surface_type, ()))

    def by_extension(self, extension_id: str) -> list[ExtensionSurfaceDescriptor]:
        return list(self._by_extension.get(extension_id, ()))

    def by_key(self, surface_type: str, name: str) -> list[ExtensionSurfaceDescriptor]:
        return list(self._by_key.get((surface_type, name), ()))

    def get(self, surface_type: str, name: str) -> ExtensionSurfaceDescriptor:
        surfaces = self._by_key[(surface_type, name)]
        if len(surfaces) > 1:
            raise DuplicateExtensionSurfaceKeyError(surface_type, name, surfaces)
        return surfaces[0]


def surfaces_from_loaded_extension(extension: object) -> tuple[ExtensionSurfaceDescriptor, ...]:
    extension_id = _extension_id(extension)
    source_path = getattr(extension, "entry_path", None) or getattr(extension, "source_path")
    surfaces: list[ExtensionSurfaceDescriptor] = []

    manifest = getattr(extension, "manifest", None)
    if manifest is not None:
        surfaces.extend(
            ExtensionSurfaceDescriptor(
                type="command",
                name=command.name,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest"},
            )
            for command in manifest.commands
        )
        surfaces.extend(
            ExtensionSurfaceDescriptor(
                type="tool",
                name=tool.name,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest"},
            )
            for tool in manifest.tools
        )
        surfaces.extend(
            ExtensionSurfaceDescriptor(
                type="hook",
                name=hook.event,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest", "kind": hook.kind},
            )
            for hook in manifest.hooks
        )

    surfaces.extend(
        ExtensionSurfaceDescriptor(
            type="command",
            name=name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for name in getattr(extension, "commands", {})
    )
    surfaces.extend(
        ExtensionSurfaceDescriptor(
            type="tool",
            name=tool.name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for tool in getattr(extension, "tool_definitions", ())
    )
    surfaces.extend(
        ExtensionSurfaceDescriptor(
            type="hook",
            name=event_name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for event_name in getattr(extension, "hooks", {})
    )
    return tuple(surfaces)


def _extension_id(extension: object) -> str:
    manifest = getattr(extension, "manifest", None)
    if manifest is not None:
        return manifest.id
    return str(getattr(extension, "name"))


ContributionType = ExtensionSurfaceType
ContributionDescriptor = ExtensionSurfaceDescriptor
DuplicateContributionKeyError = DuplicateExtensionSurfaceKeyError
ContributionRegistry = ExtensionInventory
contributions_from_loaded_extension = surfaces_from_loaded_extension
