"""Optional compatibility gate for an already-installed Pyright Server."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from loushang.coding.lsp import (
    LspServerDefinition,
    bind_coding_lsp_runtime,
    default_lsp_environment,
)
from loushang.coding.sandbox import (
    bind_coding_sandbox_runtime,
    coding_workspace_execution_profile,
)
from loushang.harness.sandbox import SandboxSettings
from loushang.harness.tools.process_hosting import ProcessExecutionScope
from loushang.harness.workspace.exec import ExecService

_PYRIGHT = shutil.which("pyright-langserver")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        _PYRIGHT is None,
        reason=(
            "pyright-langserver is not installed; optional LSP compatibility "
            "verification skipped"
        ),
    ),
]


class _NoApprovalResolver:
    actor_id = "coding-lsp-pyright-live"

    def resolve(self, request: object) -> object:
        del request
        raise AssertionError("an admitted Pyright launch must not request approval")


def test_installed_pyright_definition_outline_and_shutdown(tmp_path: Path) -> None:
    async def scenario() -> None:
        assert _PYRIGHT is not None
        project = tmp_path / "project"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            "[project]\nname = \"lsp-live-smoke\"\nversion = \"0.0.0\"\n",
            encoding="utf-8",
        )
        source = project / "main.py"
        source.write_text(
            "def target(value: int) -> int:\n"
            "    return value\n\n"
            "result = target(1)\n",
            encoding="utf-8",
        )
        sandbox_runtime = bind_coding_sandbox_runtime(
            workspace_root=project,
            writable_workspace=True,
            settings=SandboxSettings(enabled=False),
            base_exec_service=ExecService(),
        )
        runtime = bind_coding_lsp_runtime(
            workspace_root=project,
            definitions=(
                LspServerDefinition(
                    id="pyright-live",
                    command=(_PYRIGHT, "--stdio"),
                    language_extensions={"python": (".py",)},
                    root_markers=("pyproject.toml",),
                    startup_timeout_seconds=15,
                    request_timeout_seconds=15,
                    shutdown_timeout_seconds=5,
                ),
            ),
            process_launcher_binder=sandbox_runtime,
            execution_scope=ProcessExecutionScope(
                approval_resolver=_NoApprovalResolver(),
                execution_profile_ceiling=coding_workspace_execution_profile(
                    project,
                    writable=True,
                ),
            ),
            read_text=lambda path: path.read_text(encoding="utf-8"),
            baseline_environment=default_lsp_environment(),
        )
        try:
            assert runtime.status().servers == ()
            definition = await runtime.inspect_symbol(
                path="main.py",
                line=4,
                character=10,
                correlation_id="pyright-live-definition",
            )
            outline = await runtime.document_outline(
                path="main.py",
                correlation_id="pyright-live-outline",
            )

            assert definition.count >= 1
            assert any(item.path == "main.py" for item in definition.items)
            assert any(item.name == "target" for item in outline.items)
            status = runtime.status()
            assert status.ready_count == 1
            assert status.servers[0].open_document_count == 1
        finally:
            await runtime.close()
            await sandbox_runtime.close()

        status = runtime.status()
        assert status.disposed is True
        assert status.servers[0].state == "stopped"

    asyncio.run(scenario())
