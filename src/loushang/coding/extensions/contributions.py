from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loushang.coding.loader import ResourceDiagnostic

ContributionType = Literal[
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
class ContributionDescriptor:
    type: ContributionType
    name: str
    extension_id: str
    source_path: Path
    active: bool = True
    priority: int = 0
    permission_requirements: tuple[str, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class DuplicateContributionKeyError(KeyError):
    def __init__(self, contribution_type: str, name: str, contributions: list[ContributionDescriptor]) -> None:
        super().__init__(f"Duplicate contribution key: {contribution_type}:{name}")
        self.contribution_type = contribution_type
        self.name = name
        self.contributions = list(contributions)


@dataclass
class ContributionRegistry:
    _contributions: list[ContributionDescriptor] = field(default_factory=list)
    _by_type: dict[str, list[ContributionDescriptor]] = field(default_factory=lambda: defaultdict(list))
    _by_extension: dict[str, list[ContributionDescriptor]] = field(default_factory=lambda: defaultdict(list))
    _by_key: dict[tuple[str, str], list[ContributionDescriptor]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def from_extensions(cls, extensions: Iterable[object]) -> "ContributionRegistry":
        registry = cls()
        for extension in extensions:
            for contribution in getattr(extension, "contributions", ()):
                registry.add(contribution)
        return registry

    def add(self, contribution: ContributionDescriptor) -> None:
        self._contributions.append(contribution)
        self._by_type[contribution.type].append(contribution)
        self._by_extension[contribution.extension_id].append(contribution)
        self._by_key[(contribution.type, contribution.name)].append(contribution)

    def all(self) -> list[ContributionDescriptor]:
        return list(self._contributions)

    def by_type(self, contribution_type: str) -> list[ContributionDescriptor]:
        return list(self._by_type.get(contribution_type, ()))

    def by_extension(self, extension_id: str) -> list[ContributionDescriptor]:
        return list(self._by_extension.get(extension_id, ()))

    def by_key(self, contribution_type: str, name: str) -> list[ContributionDescriptor]:
        return list(self._by_key.get((contribution_type, name), ()))

    def get(self, contribution_type: str, name: str) -> ContributionDescriptor:
        contributions = self._by_key[(contribution_type, name)]
        if len(contributions) > 1:
            raise DuplicateContributionKeyError(contribution_type, name, contributions)
        return contributions[0]


def contributions_from_loaded_extension(extension: object) -> tuple[ContributionDescriptor, ...]:
    extension_id = _extension_id(extension)
    source_path = getattr(extension, "entry_path", None) or getattr(extension, "source_path")
    contributions: list[ContributionDescriptor] = []

    manifest = getattr(extension, "manifest", None)
    if manifest is not None:
        contributions.extend(
            ContributionDescriptor(
                type="command",
                name=command.name,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest"},
            )
            for command in manifest.commands
        )
        contributions.extend(
            ContributionDescriptor(
                type="tool",
                name=tool.name,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest"},
            )
            for tool in manifest.tools
        )
        contributions.extend(
            ContributionDescriptor(
                type="hook",
                name=hook.event,
                extension_id=extension_id,
                source_path=source_path,
                metadata={"source": "manifest", "kind": hook.kind},
            )
            for hook in manifest.hooks
        )

    contributions.extend(
        ContributionDescriptor(
            type="command",
            name=name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for name in getattr(extension, "commands", {})
    )
    contributions.extend(
        ContributionDescriptor(
            type="tool",
            name=tool.name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for tool in getattr(extension, "tool_definitions", ())
    )
    contributions.extend(
        ContributionDescriptor(
            type="hook",
            name=event_name,
            extension_id=extension_id,
            source_path=source_path,
            metadata={"source": "runtime"},
        )
        for event_name in getattr(extension, "hooks", {})
    )
    return tuple(contributions)


def _extension_id(extension: object) -> str:
    manifest = getattr(extension, "manifest", None)
    if manifest is not None:
        return manifest.id
    return str(getattr(extension, "name"))
