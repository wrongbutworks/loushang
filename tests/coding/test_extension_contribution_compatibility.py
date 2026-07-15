from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_coding_contribution_paths_share_harness_identity() -> None:
    from loushang.coding import extensions
    from loushang.coding.extensions import contributions as compatibility
    from loushang.harness import contributions as owner

    names = (
        "ContributionDescriptor",
        "ContributionRegistry",
        "ContributionType",
        "DuplicateContributionKeyError",
        "DuplicateExtensionSurfaceKeyError",
        "ExtensionInventory",
        "ExtensionSurfaceDescriptor",
        "ExtensionSurfaceType",
    )
    for name in names:
        assert getattr(compatibility, name) is getattr(owner, name)

    package_names = (
        "ContributionDescriptor",
        "ContributionRegistry",
        "DuplicateContributionKeyError",
        "DuplicateExtensionSurfaceKeyError",
        "ExtensionInventory",
        "ExtensionSurfaceDescriptor",
        "ExtensionSurfaceType",
    )
    for name in package_names:
        assert getattr(extensions, name) is getattr(owner, name)

    assert owner.ContributionDescriptor.__module__ == "loushang.harness.contributions"
    assert owner.ContributionRegistry.__module__ == "loushang.harness.contributions"


def test_loaded_extension_projection_creates_harness_records() -> None:
    from loushang.coding.extensions.contributions import surfaces_from_loaded_extension
    from loushang.harness.contributions import ContributionDescriptor

    extension = SimpleNamespace(
        name="review",
        source_path=Path("/tmp/extensions/review.py"),
        entry_path=None,
        manifest=None,
        commands={"review": object()},
        tool_definitions=[SimpleNamespace(name="lookup")],
        hooks={"before_agent_start": [object()]},
    )

    contributions = surfaces_from_loaded_extension(extension)

    assert [(item.type, item.name) for item in contributions] == [
        ("command", "review"),
        ("tool", "lookup"),
        ("hook", "before_agent_start"),
    ]
    assert all(isinstance(item, ContributionDescriptor) for item in contributions)
    assert {item.extension_id for item in contributions} == {"review"}
