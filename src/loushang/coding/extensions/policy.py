from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loushang.coding.extensions.manifest import ExtensionManifest, PermissionLevel

ExtensionCapability = Literal[
    "exec",
    "filesystem",
    "network",
    "model",
    "session_mutation",
    "ui_mutation",
    "tool_mutation",
]

_DEFAULT_CAPABILITIES: dict[PermissionLevel, tuple[str, ...]] = {
    "safe": (),
    "standard": ("filesystem", "model"),
    "powerful": (
        "exec",
        "filesystem",
        "network",
        "model",
        "session_mutation",
        "ui_mutation",
        "tool_mutation",
    ),
}


@dataclass(frozen=True)
class ExtensionPolicyDecision:
    enabled: bool = True
    permission_level: PermissionLevel = "safe"
    capabilities: tuple[str, ...] = ()
    allow_managed_hooks_only: bool = False

    @property
    def active(self) -> bool:
        return self.enabled


def policy_from_manifest(
    manifest: ExtensionManifest | None,
    *,
    enabled: bool = True,
    allow_managed_hooks_only: bool = False,
) -> ExtensionPolicyDecision:
    if manifest is None:
        return ExtensionPolicyDecision(
            enabled=enabled,
            allow_managed_hooks_only=allow_managed_hooks_only,
        )
    capabilities = (
        manifest.permissions.capabilities
        if manifest.permissions.capabilities
        else _DEFAULT_CAPABILITIES[manifest.permissions.level]
    )
    return ExtensionPolicyDecision(
        enabled=enabled,
        permission_level=manifest.permissions.level,
        capabilities=tuple(capabilities),
        allow_managed_hooks_only=allow_managed_hooks_only,
    )
