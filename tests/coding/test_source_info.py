from __future__ import annotations

from pathlib import Path


def test_source_info_from_resource_descriptor_projects_package_provenance() -> None:
    from loushang.coding.loader import PromptFragmentDescriptor
    from loushang.coding.source_info import source_info_from_resource_descriptor

    descriptor = PromptFragmentDescriptor(
        name="review",
        source_path=Path("/tmp/plugin/prompts/review.md"),
        text="Review carefully.",
        source="package_resource",
        source_kind="external_package",
        source_scope="package",
        source_root=Path("/tmp/plugin/prompts"),
    )

    info = source_info_from_resource_descriptor(descriptor)

    assert info.path == "/tmp/plugin/prompts/review.md"
    assert info.source == "package_resource"
    assert info.scope == "project"
    assert info.origin == "package"
    assert info.base_dir == "/tmp/plugin/prompts"


def test_source_info_from_resource_descriptor_projects_project_local_provenance() -> None:
    from loushang.coding.loader import SkillDescriptor
    from loushang.coding.source_info import source_info_from_resource_descriptor

    descriptor = SkillDescriptor(
        name="debug",
        source_path=Path("/tmp/project/skills/debug/SKILL.md"),
        content="Debug carefully.",
        source="filesystem",
        source_kind="project_local",
        source_scope="project",
        source_root=Path("/tmp/project/skills"),
    )

    info = source_info_from_resource_descriptor(descriptor)

    assert info.path == "/tmp/project/skills/debug/SKILL.md"
    assert info.source == "filesystem"
    assert info.scope == "project"
    assert info.origin == "top-level"
    assert info.base_dir == "/tmp/project/skills"
