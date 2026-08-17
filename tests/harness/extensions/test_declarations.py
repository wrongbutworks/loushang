from __future__ import annotations

from pathlib import Path

import pytest

from loushang.harness.extensions.agent import ExtensionRunner
from loushang.harness.extensions.declarations import (
    ExtensionCapabilityDeclarationSnapshot,
)
from loushang.harness.extensions.manifest import (
    ExtensionManifest,
    ExtensionPermissionDeclaration,
)
from loushang.harness.extensions.types import (
    ExtensionPolicyDecision,
    LoadedExtension,
    RegisteredRuntimeCapabilityReplacement,
)


def _extension(
    extension_id: str,
    *,
    name: str,
    version: int,
    priority: int,
    permissions: tuple[str, ...],
    create,
) -> LoadedExtension:
    return LoadedExtension(
        name=extension_id,
        source_path=Path(f"/tmp/{extension_id}.py"),
        manifest=ExtensionManifest(
            id=extension_id,
            name=extension_id,
            permissions=ExtensionPermissionDeclaration(capabilities=permissions),
        ),
        policy=ExtensionPolicyDecision(capabilities=permissions),
        runtime_capability_replacements=[
            RegisteredRuntimeCapabilityReplacement(
                slot="prompt.sections",
                name=name,
                create=create,
                implementation_version=version,
                priority=priority,
            )
        ],
    )


def test_extension_capability_declaration_snapshot_is_canonical_and_redacted() -> None:
    created: list[str] = []
    first = _extension(
        "zeta",
        name="zeta-provider",
        version=2,
        priority=7,
        permissions=("tool.packs", "prompt.sections"),
        create=lambda: created.append("zeta") or object(),
    )
    second = _extension(
        "alpha",
        name="alpha-provider",
        version=1,
        priority=3,
        permissions=("prompt.sections",),
        create=lambda: created.append("alpha") or object(),
    )

    forward = ExtensionCapabilityDeclarationSnapshot.from_extensions((first, second))
    reverse = ExtensionCapabilityDeclarationSnapshot.from_extensions((second, first))

    assert forward == reverse
    assert forward.fingerprint == reverse.fingerprint
    assert [item.extension_id for item in forward.declarations] == ["alpha", "zeta"]
    assert forward.declarations[1].granted_permissions == (
        "prompt.sections",
        "tool.packs",
    )
    assert created == []
    payload = forward.to_json()
    assert "create" not in repr(payload)
    assert "/tmp" not in repr(payload)


def test_extension_capability_declarations_reject_duplicate_extension_identity() -> (
    None
):
    first = _extension(
        "duplicate",
        name="first",
        version=1,
        priority=1,
        permissions=("prompt.sections",),
        create=object,
    )
    second = _extension(
        "duplicate",
        name="second",
        version=1,
        priority=2,
        permissions=("prompt.sections",),
        create=object,
    )

    with pytest.raises(ValueError, match="unique Extension identities"):
        ExtensionCapabilityDeclarationSnapshot.from_extensions((first, second))


def test_prepared_generation_freezes_candidate_declarations() -> None:
    current = _extension(
        "demo",
        name="current",
        version=1,
        priority=1,
        permissions=("prompt.sections",),
        create=object,
    )
    candidate_extension = _extension(
        "demo",
        name="candidate",
        version=2,
        priority=2,
        permissions=("prompt.sections",),
        create=object,
    )
    prepared = ExtensionRunner([current]).prepare_generation([candidate_extension])
    frozen = prepared.capability_declarations

    candidate_extension.runtime_capability_replacements.clear()

    assert prepared.capability_declarations == frozen
    assert [item.name for item in frozen.declarations] == ["candidate"]
