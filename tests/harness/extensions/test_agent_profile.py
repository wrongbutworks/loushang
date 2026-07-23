from __future__ import annotations

from loushang.harness.extensions.agent import (
    ExtensionAPI,
    ExtensionLoader,
    ExtensionRunner,
    policy_from_manifest,
)
from loushang.harness.extensions.loader import ExtensionLoader as CoreExtensionLoader
from loushang.harness.extensions.runner import ExtensionRunner as CoreExtensionRunner
from loushang.harness.extensions.types import ExtensionPolicyDecision
from loushang.harness.resources.types import ExtensionDescriptor


def test_agent_extension_profile_composes_existing_core_runtime() -> None:
    assert issubclass(ExtensionLoader, CoreExtensionLoader)
    assert issubclass(ExtensionRunner, CoreExtensionRunner)
    assert policy_from_manifest(None) == ExtensionPolicyDecision(enabled=True)


def test_agent_extension_loader_uses_agent_session_api(tmp_path) -> None:
    extension_path = tmp_path / "research_extension.py"
    extension_path.write_text(
        "\n".join(
            (
                "def register(api):",
                "    api.on('session_start', lambda event, context: None)",
            )
        ),
        encoding="utf-8",
    )

    loaded = ExtensionLoader().load_extension(
        ExtensionDescriptor(
            name="research-extension",
            source_path=extension_path,
            entry_path=extension_path,
        )
    )

    assert loaded is not None
    assert isinstance(loaded.api, ExtensionAPI)
    assert tuple(loaded.hooks) == ("session_start",)
