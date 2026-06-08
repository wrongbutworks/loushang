from __future__ import annotations


def test_extension_manifest_parser_accepts_capability_manifest(tmp_path) -> None:
    from loushang.coding.extensions.manifest import parse_extension_manifest

    manifest_path = tmp_path / "loushang-extension.toml"
    manifest_path.write_text(
        """
[extension]
id = "acme.review"
name = "Acme Review"
version = "0.1.0"
description = "Review helpers"

[permissions]
level = "standard"
capabilities = ["filesystem", "model"]

[[commands]]
name = "acme-review"
description = "Run review"

[[tools]]
name = "acme_lookup"
description = "Look up metadata"

[[hooks]]
event = "before_agent_start"
kind = "augment"
handler = "extension:before_agent_start"

[dependencies.python]
packages = ["acme-sdk>=0.3"]
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    result = parse_extension_manifest(manifest_path)

    assert result.manifest is not None
    assert result.diagnostics == []
    assert result.manifest.id == "acme.review"
    assert result.manifest.name == "Acme Review"
    assert result.manifest.permissions.level == "standard"
    assert result.manifest.permissions.capabilities == ("filesystem", "model")
    assert [command.name for command in result.manifest.commands] == ["acme-review"]
    assert [tool.name for tool in result.manifest.tools] == ["acme_lookup"]
    assert [(hook.event, hook.kind) for hook in result.manifest.hooks] == [
        ("before_agent_start", "augment")
    ]
    assert result.manifest.dependencies.python.packages == ("acme-sdk>=0.3",)


def test_extension_manifest_parser_reports_invalid_input_without_throwing(tmp_path) -> None:
    from loushang.coding.extensions.manifest import parse_extension_manifest

    manifest_path = tmp_path / "loushang-extension.toml"
    manifest_path.write_text(
        """
[extension]
id = "bad.extension"
name = "Bad Extension"

[permissions]
level = "root"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    result = parse_extension_manifest(manifest_path)

    assert result.manifest is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "invalid_extension_permission_level"
    ]
    assert result.diagnostics[0].source_path == manifest_path
    assert result.diagnostics[0].resource_type == "extension"


def test_extension_loader_attaches_manifest_policy_and_contributions(tmp_path) -> None:
    from loushang.coding.extensions.loader import ExtensionLoader
    from loushang.coding.loader import ExtensionDescriptor

    extension_dir = tmp_path / "review"
    extension_dir.mkdir()
    extension_file = extension_dir / "extension.py"
    extension_file.write_text(
        """
from loushang.coding.tools import ToolDefinition


async def _execute_tool(tool_name, arguments, context, signal):
    return {"ok": True}


def register(api):
    api.on("session_start", lambda event, ctx: None)
    api.register_tool(
        ToolDefinition(
            name="runtime_lookup",
            label="Runtime Lookup",
            description="runtime tool",
            parameters={},
            execute=_execute_tool,
        )
    )
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (extension_dir / "loushang-extension.toml").write_text(
        """
[extension]
id = "acme.review"
name = "Acme Review"

[permissions]
level = "standard"
capabilities = ["filesystem"]

[[commands]]
name = "acme-review"

[[tools]]
name = "manifest_lookup"

[[hooks]]
event = "before_agent_start"
kind = "augment"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    loader = ExtensionLoader()
    loaded = loader.load_extensions(
        [
            ExtensionDescriptor(
                name="review",
                source_path=extension_dir,
                entry_path=extension_file,
            )
        ]
    )

    assert len(loaded) == 1
    extension = loaded[0]
    assert extension.name == "review"
    assert [tool.name for tool in extension.tool_definitions] == ["runtime_lookup"]
    assert extension.manifest is not None
    assert extension.manifest.id == "acme.review"
    assert extension.policy is not None
    assert extension.policy.permission_level == "standard"
    assert extension.policy.capabilities == ("filesystem",)
    assert sorted((contribution.type, contribution.name) for contribution in extension.contributions) == [
        ("command", "acme-review"),
        ("hook", "before_agent_start"),
        ("hook", "session_start"),
        ("tool", "manifest_lookup"),
        ("tool", "runtime_lookup"),
    ]
    assert loader.get_diagnostics() == []


def test_contribution_registry_indexes_loaded_extension_contributions(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions.contributions import (
        ContributionDescriptor,
        ContributionRegistry,
    )
    from loushang.coding.extensions.types import LoadedExtension

    extension = LoadedExtension(
        name="review",
        source_path=Path("/tmp/review/extension.py"),
        contributions=[
            ContributionDescriptor(
                type="tool",
                name="lookup",
                extension_id="review",
                source_path=Path("/tmp/review/extension.py"),
            ),
            ContributionDescriptor(
                type="command",
                name="review",
                extension_id="review",
                source_path=Path("/tmp/review/extension.py"),
            ),
        ],
    )

    registry = ContributionRegistry.from_extensions([extension])

    assert [contribution.name for contribution in registry.by_type("tool")] == ["lookup"]
    assert [contribution.name for contribution in registry.by_extension("review")] == [
        "lookup",
        "review",
    ]
    assert registry.get("tool", "lookup").extension_id == "review"
