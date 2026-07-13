from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.harness.extensions.api import ExtensionContributionAPI
from loushang.harness.extensions.dispatch import ExtensionDispatcher
from loushang.harness.extensions.loader import ExtensionLoader
from loushang.harness.extensions.registry import resolve_extension_registry
from loushang.harness.extensions.resources import ExtensionResourceRuntime
from loushang.harness.extensions.types import (
    LoadedExtension,
    RegisteredCommand,
    RegisteredFlag,
)
from loushang.harness.resources.types import ExtensionDescriptor, ResourceBundle
from loushang.harness.tools.core import ToolDefinition


def test_contribution_api_builds_product_neutral_extension() -> None:
    async def command_handler(arguments: str, context: object) -> None:
        del arguments, context

    api = ExtensionContributionAPI(
        name="shared",
        source_path=Path("/tmp/shared.py"),
    )
    api.on("agent_start", lambda event, context: None)
    api.register_command("inspect", handler=command_handler)
    api.register_flag("verbose", type="boolean", default=False)

    extension = api.build_loaded_extension()

    assert extension.name == "shared"
    assert list(extension.hooks) == ["agent_start"]
    assert list(extension.commands) == ["inspect"]
    assert extension.flags["verbose"].default is False


def test_loader_executes_register_api_without_coding_runtime(tmp_path: Path) -> None:
    entry_path = tmp_path / "extension.py"
    entry_path.write_text(
        """
async def _inspect(arguments, context):
    return None


def register(api):
    api.on("agent_start", lambda event, context: None)
    api.register_command("inspect", handler=_inspect)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    descriptor = ExtensionDescriptor(
        name="shared",
        source_path=entry_path,
        entry_path=entry_path,
    )

    loader = ExtensionLoader()
    extension = loader.load_extension(descriptor)

    assert extension is not None
    assert extension.api is not None
    assert list(extension.commands) == ["inspect"]
    assert extension.policy is not None
    assert extension.policy.active
    assert loader.get_diagnostics() == []


def test_loader_adapts_legacy_hooks_without_product_configuration(
    tmp_path: Path,
) -> None:
    entry_path = tmp_path / "legacy.py"
    entry_path.write_text(
        """
class LegacyExtension:
    def agent_start(self, event):
        return None


EXTENSION = LegacyExtension()
""".strip()
        + "\n",
        encoding="utf-8",
    )

    extension = ExtensionLoader().load_extension(
        ExtensionDescriptor(
            name="legacy",
            source_path=entry_path,
            entry_path=entry_path,
        )
    )

    assert extension is not None
    assert list(extension.hooks) == ["agent_start"]


def test_registry_resolves_contributions_and_preserves_first_wins() -> None:
    async def command_handler(arguments: str, context: object) -> None:
        del arguments, context

    async def execute(
        tool_call_id: str,
        arguments: dict[str, object],
        signal: object | None,
        on_update: object | None,
    ) -> object:
        del tool_call_id, arguments, signal, on_update
        return object()

    first = LoadedExtension(
        name="first",
        source_path=Path("/tmp/first.py"),
        commands={
            "inspect": RegisteredCommand(name="inspect", handler=command_handler)
        },
        flags={
            "verbose": RegisteredFlag(name="verbose", type="boolean", default=False)
        },
        tool_definitions=[
            ToolDefinition(
                name="lookup",
                label="Lookup",
                description="Lookup data",
                parameters={},
                execute=execute,  # type: ignore[arg-type]
            )
        ],
    )
    second = LoadedExtension(
        name="second",
        source_path=Path("/tmp/second.py"),
        commands={
            "inspect": RegisteredCommand(name="inspect", handler=command_handler)
        },
        flags={"verbose": RegisteredFlag(name="verbose", type="boolean", default=True)},
        tool_definitions=list(first.tool_definitions),
    )

    registry = resolve_extension_registry([first, second])

    assert [command.invocation_name for command in registry.commands] == [
        "inspect:1",
        "inspect:2",
    ]
    assert [flag.extension_name for flag in registry.flags] == ["first"]
    assert registry.flag_defaults == {"verbose": False}
    assert [tool.extension_name for tool in registry.tools] == ["first"]
    assert [diagnostic.code for diagnostic in registry.diagnostics] == [
        "duplicate_extension_tool",
        "duplicate_extension_flag",
    ]


def test_dispatcher_preserves_order_and_contains_failures() -> None:
    calls: list[str] = []
    errors: list[tuple[str, str]] = []

    def broken(event: object, context: object) -> None:
        del event, context
        calls.append("broken")
        raise RuntimeError("boom")

    async def succeeding(event: object, context: object) -> str:
        del event, context
        calls.append("succeeding")
        return "handled"

    extensions = [
        LoadedExtension(
            name="broken",
            source_path=Path("/tmp/broken.py"),
            hooks={"agent_start": [broken]},
        ),
        LoadedExtension(
            name="succeeding",
            source_path=Path("/tmp/succeeding.py"),
            hooks={"agent_start": [succeeding]},
        ),
    ]
    diagnostics = []
    dispatcher = ExtensionDispatcher(
        extensions,
        context_factory=lambda extension: {"extension": extension.name},
        diagnostics=diagnostics,
        runtime_error_handler=lambda extension, event, error: errors.append(
            (extension.name, event)
        ),
    )

    results = asyncio.run(dispatcher.dispatch("agent_start", object()))

    assert results == ("handled",)
    assert calls == ["broken", "succeeding"]
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "extension_agent_start_failed"
    ]
    assert errors == [("broken", "agent_start")]


def test_dispatcher_reduces_input_transformations_in_order() -> None:
    def first(event: object, context: object) -> dict[str, object]:
        del context
        return {"action": "transform", "text": f"{event.text} first"}

    async def second(event: object, context: object) -> dict[str, object]:
        del context
        return {"action": "transform", "text": f"{event.text} second"}

    extension = LoadedExtension(
        name="input",
        source_path=Path("/tmp/input.py"),
        hooks={"input": [first, second]},
    )
    diagnostics = []
    dispatcher = ExtensionDispatcher(
        [extension],
        context_factory=lambda loaded: loaded.name,
        diagnostics=diagnostics,
    )

    result = asyncio.run(dispatcher.dispatch_input("start"))

    assert result.action == "transform"
    assert result.text == "start first second"
    assert diagnostics == []


def test_resource_runtime_normalizes_extension_paths(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompts" / "review.md"
    prompt_path.parent.mkdir()
    prompt_path.write_text("Review carefully", encoding="utf-8")

    def discover(bundle: ResourceBundle, context: object) -> dict[str, object]:
        del bundle, context
        return {"promptPaths": [prompt_path]}

    extension = LoadedExtension(
        name="resources",
        source_path=tmp_path / "extension.py",
        hooks={"resources_discover": [discover]},
    )
    diagnostics = []
    runtime = ExtensionResourceRuntime([extension], diagnostics=diagnostics)

    bundle = runtime.discover(
        ResourceBundle(cwd=tmp_path),
        context={"cwd": str(tmp_path)},
    )

    assert [(prompt.name, prompt.text) for prompt in bundle.prompts] == [
        ("review", "Review carefully")
    ]
    assert diagnostics == []
