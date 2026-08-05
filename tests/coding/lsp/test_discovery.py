from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from loushang.coding.lsp import (
    LspServerDefinition,
    default_lsp_environment,
    discover_lsp_catalog,
)


def _write_config(path: Path, servers: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"servers": servers}), encoding="utf-8")


def test_catalog_merges_config_by_product_precedence_and_admits_available_server(
    tmp_path: Path,
) -> None:
    user_config = tmp_path / "user-lsp.json"
    project_config = tmp_path / "project-lsp.json"
    _write_config(
        user_config,
        [
            {
                "id": "python-custom",
                "command": ["custom-lsp", "--stdio"],
                "language_extensions": {"python": [".py"]},
                "environment": {"CUSTOM_LSP_HOME": "/trusted/home"},
            },
            {"id": "disabled-default", "enabled": False},
        ],
    )
    _write_config(
        project_config,
        [
            {
                "id": "python-custom",
                "command": ["custom-lsp", "--stdio"],
                "language_extensions": {"python": ["py", "pyi"]},
                "priority": 20,
                "settings": {"analysis": {"strict": True}},
            },
            {"id": "broken", "command": "not-an-array"},
        ],
    )
    probe_environments: list[dict[str, str]] = []

    def resolve(command: str, environment: Mapping[str, str]) -> str | None:
        resolved_environment = dict(environment)
        probe_environments.append(resolved_environment)
        return (
            f"{resolved_environment['PATH']}/{command}"
            if command == "custom-lsp"
            else None
        )

    snapshot = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={"PATH": "/tools"},
        global_config_path=user_config,
        project_config_path=project_config,
        executable_resolver=resolve,
        include_product_defaults=False,
    )

    assert snapshot.admitted_count == 1
    assert snapshot.definitions[0].command == ("/tools/custom-lsp", "--stdio")
    assert snapshot.definitions[0].extensions == (".py", ".pyi")
    assert snapshot.definitions[0].environment == {"CUSTOM_LSP_HOME": "/trusted/home"}
    assert probe_environments == [
        {"PATH": "/tools", "CUSTOM_LSP_HOME": "/trusted/home"}
    ]
    assert [
        (record.definition_id, record.source, record.state)
        for record in snapshot.records
    ] == [
        ("broken", "project-config", "rejected"),
        ("disabled-default", "user-config", "disabled"),
        ("python-custom", "project-config", "admitted"),
    ]
    assert snapshot.records[-1].executable == "/tools/custom-lsp"
    assert len(snapshot.generation) == 12

    _write_config(
        project_config,
        [
            {
                "id": "python-custom",
                "command": ["custom-lsp", "--stdio"],
                "language_extensions": {"python": [".py"]},
                "settings": {"analysis": {"strict": False}},
            }
        ],
    )
    changed = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={"PATH": "/tools"},
        global_config_path=user_config,
        project_config_path=project_config,
        executable_resolver=lambda command, _environment: f"/tools/{command}",
        include_product_defaults=False,
    )
    assert changed.generation != snapshot.generation


def test_project_config_cannot_alter_arguments_of_trusted_command(
    tmp_path: Path,
) -> None:
    user_config = tmp_path / "user-lsp.json"
    project_config = tmp_path / "project-lsp.json"
    _write_config(
        user_config,
        [
            {
                "id": "python-custom",
                "command": ["python", "-m", "trusted_lsp"],
                "language_extensions": {"python": [".py"]},
            }
        ],
    )
    _write_config(
        project_config,
        [
            {
                "id": "python-custom",
                "command": ["python", "-c", "run_untrusted_code()"],
                "language_extensions": {"python": [".py"]},
            }
        ],
    )

    snapshot = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={"PATH": "/tools"},
        global_config_path=user_config,
        project_config_path=project_config,
        executable_resolver=lambda command, _environment: f"/tools/{command}",
        include_product_defaults=False,
    )

    assert snapshot.admitted_count == 0
    assert snapshot.records[0].state == "rejected"
    assert "complete command" in snapshot.records[0].detail


def test_explicit_sdk_definition_is_already_admitted_without_binary_probe(
    tmp_path: Path,
) -> None:
    probes: list[str] = []
    definition = LspServerDefinition(
        id="sdk-fake",
        command=("not-installed-in-this-test", "--stdio"),
        language_extensions={"python": (".py",)},
    )

    snapshot = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={},
        explicit_definitions=(definition,),
        global_config_path=tmp_path / "missing-user.json",
        project_config_path=tmp_path / "missing-project.json",
        executable_resolver=lambda command, _environment: probes.append(command),
        include_product_defaults=False,
    )

    assert snapshot.definitions == (definition,)
    assert snapshot.records[0].state == "admitted"
    assert probes == []


def test_project_config_cannot_introduce_untrusted_executable(tmp_path: Path) -> None:
    project_config = tmp_path / "project-lsp.json"
    _write_config(
        project_config,
        [
            {
                "id": "repository-command",
                "command": ["run-anything", "--stdio"],
                "language_extensions": {"python": [".py"]},
            }
        ],
    )

    snapshot = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={"PATH": "/tools"},
        global_config_path=False,
        project_config_path=project_config,
        executable_resolver=lambda command, _environment: f"/tools/{command}",
        include_product_defaults=False,
    )

    assert snapshot.admitted_count == 0
    assert snapshot.records[0].state == "rejected"
    assert "user-level" in snapshot.records[0].detail


def test_product_defaults_report_unavailable_without_installing_or_starting(
    tmp_path: Path,
) -> None:
    probes: list[str] = []

    snapshot = discover_lsp_catalog(
        workspace_root=tmp_path,
        baseline_environment={"PATH": "/empty"},
        global_config_path=tmp_path / "missing-user.json",
        project_config_path=tmp_path / "missing-project.json",
        executable_resolver=lambda command, _environment: probes.append(command),
    )

    assert snapshot.admitted_count == 0
    assert probes == [
        "clangd",
        "gopls",
        "pyright-langserver",
        "rust-analyzer",
        "typescript-language-server",
    ]
    assert {record.state for record in snapshot.records} == {"unavailable"}


def test_default_environment_excludes_unrelated_secrets() -> None:
    environment = default_lsp_environment(
        {
            "PATH": "/bin",
            "HOME": "/home/example",
            "LANG": "C.UTF-8",
            "API_TOKEN": "secret",
            "AWS_SECRET_ACCESS_KEY": "secret",
        }
    )

    assert environment == {
        "PATH": "/bin",
        "HOME": "/home/example",
        "LANG": "C.UTF-8",
    }
