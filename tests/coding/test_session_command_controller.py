from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.extensions import (
    ExtensionRunner,
    LoadedExtension,
    RegisteredCommand,
)
from loushang.coding.loader import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)
from loushang.coding.session.builtin_commands import BuiltinCommandBackend
from loushang.coding.session.command_controller import CommandController
from loushang.coding.store import SessionManager


def test_command_controller_lists_extension_prompt_and_enabled_skill_commands(tmp_path) -> None:
    async def _handler(args: str, ctx) -> None:
        del args, ctx

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="deploy-ext",
                source_path=Path("/tmp/project/extensions/deploy.py"),
                commands={
                    "deploy": RegisteredCommand(
                        name="deploy",
                        handler=_handler,
                        description="Deploy the project",
                    )
                },
            )
        ]
    )
    bundle = ResourceBundle(
        cwd=Path("/tmp/project"),
        prompts=[
            PromptFragmentDescriptor(
                name="plan",
                source_path=Path("/tmp/project/prompts/plan.md"),
                text="---\ndescription: Plan\n---\nPlan the change.",
                source_root=Path("/tmp/project/prompts"),
            )
        ],
        skills=[
            SkillDescriptor(
                name="debugging",
                source_path=Path("/tmp/project/skills/debugging/SKILL.md"),
                description="Debug failures.",
                source_root=Path("/tmp/project/skills"),
            ),
            SkillDescriptor(
                name="hidden",
                source_path=Path("/tmp/project/skills/hidden/SKILL.md"),
                enabled=False,
            ),
        ],
    )
    controller = CommandController(
        session_manager=manager,
        get_extension_runner=lambda: runner,
        get_resource_bundle=lambda: bundle,
        get_diagnostics_service=lambda: None,
    )

    commands = controller.list_commands()

    assert [command.name for command in commands] == ["deploy", "plan", "skill:debugging"]
    assert [command.description for command in commands] == ["Deploy the project", "Plan the change.", "Debug failures."]
    assert [command.source for command in commands] == ["extension", "prompt", "skill"]
    assert [command.source_info.path for command in commands] == [
        "/tmp/project/extensions/deploy.py",
        "/tmp/project/prompts/plan.md",
        "/tmp/project/skills/debugging/SKILL.md",
    ]


def test_command_controller_lists_builtin_commands_before_extension_and_resource_commands(tmp_path) -> None:
    async def _handler(args: str, ctx) -> None:
        del args, ctx

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="deploy-ext",
                source_path=Path("/tmp/project/extensions/deploy.py"),
                commands={"deploy": RegisteredCommand(name="deploy", handler=_handler)},
            )
        ]
    )
    bundle = ResourceBundle(
        cwd=Path("/tmp/project"),
        prompts=[PromptFragmentDescriptor(name="plan", source_path=Path("/tmp/project/prompts/plan.md"), text="Plan")],
    )
    controller = CommandController(
        session_manager=manager,
        get_extension_runner=lambda: runner,
        get_resource_bundle=lambda: bundle,
        get_diagnostics_service=lambda: None,
        builtin_backend=BuiltinCommandBackend(),
    )

    commands = controller.list_commands()

    assert [command.name for command in commands[:4]] == ["settings", "model", "scoped-models", "export"]
    assert {command.name for command in commands} >= {"copy", "name", "session", "terminal", "changelog", "deploy", "plan"}
    assert all(command.source == "builtin" for command in commands[:22])
    assert commands[0].source_info.source == "builtin"


def test_command_controller_exposes_prompt_argument_hint_from_frontmatter(tmp_path) -> None:
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    bundle = ResourceBundle(
        cwd=Path("/tmp/project"),
        prompts=[
            PromptFragmentDescriptor(
                name="review",
                source_path=Path("/tmp/project/prompts/review.md"),
                text="---\n"
                "description: Review pull requests\n"
                'argument-hint: "<PR-URL>"\n'
                "---\n\n"
                "Review $1.",
                description="Review pull requests",
                argument_hint="<PR-URL>",
                source_root=Path("/tmp/project/prompts"),
            )
        ],
    )
    controller = CommandController(
        session_manager=manager,
        get_extension_runner=lambda: None,
        get_resource_bundle=lambda: bundle,
        get_diagnostics_service=lambda: None,
    )

    commands = controller.list_commands()

    assert [(command.name, command.description, command.argument_hint) for command in commands] == [
        ("review", "Review pull requests", "<PR-URL>")
    ]


def test_command_controller_executes_extension_command_before_resource_command(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    async def _handler(args: str, ctx) -> None:
        calls.append((args, ctx.cwd))

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="deploy-ext",
                source_path=Path("/tmp/project/extensions/deploy.py"),
                commands={"deploy": RegisteredCommand(name="deploy", handler=_handler)},
            )
        ]
    )
    bundle = ResourceBundle(
        cwd=Path("/tmp/project"),
        prompts=[PromptFragmentDescriptor(name="deploy", source_path=Path("/tmp/project/prompts/deploy.md"), text="Prompt deploy")],
    )
    controller = CommandController(
        session_manager=manager,
        get_extension_runner=lambda: runner,
        get_resource_bundle=lambda: bundle,
        get_diagnostics_service=lambda: None,
    )

    result = asyncio.run(controller.execute_command_async("/deploy", "now"))

    assert result is not None
    assert result.invocation_name == "deploy"
    assert result.result is None
    assert calls == [("now", "/tmp/project")]


def test_command_controller_executes_builtin_name_session_and_unsupported_commands(tmp_path) -> None:
    names: list[str | None] = []
    controller = CommandController(
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False, session_id="session-1"),
        get_extension_runner=lambda: None,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
        builtin_backend=BuiltinCommandBackend(
            set_session_name=names.append,
            get_session_info=lambda: {"session_id": "session-1", "cwd": "/tmp/project"},
        ),
    )

    name_result = asyncio.run(controller.execute_command_async("/name", "Project Alpha"))
    session_result = asyncio.run(controller.execute_command_async("/session", ""))
    model_result = asyncio.run(controller.execute_command_async("/model", ""))

    assert name_result is not None
    assert name_result.result == {"source": "builtin", "command": "name", "status": "ok", "name": "Project Alpha"}
    assert names == ["Project Alpha"]
    assert session_result is not None
    assert session_result.result == {
        "source": "builtin",
        "command": "session",
        "status": "ok",
        "session": {"session_id": "session-1", "cwd": "/tmp/project"},
    }
    assert model_result is not None
    assert model_result.result == {
        "source": "builtin",
        "command": "model",
        "status": "unsupported",
        "message": 'Builtin command "/model" is handled by the interactive shell.',
    }


def test_command_controller_executes_builtin_runtime_session_commands(tmp_path) -> None:
    calls: list[tuple[str, object]] = []

    async def _new_session(options: object | None = None) -> dict[str, object]:
        calls.append(("new", options))
        return {"cancelled": False}

    async def _resume_session(session_path: str, options: object | None = None) -> dict[str, object]:
        calls.append(("resume", (session_path, options)))
        return {"cancelled": False}

    async def _fork(entry_id: str, options: object | None = None) -> dict[str, object]:
        calls.append(("fork", (entry_id, options)))
        return {"cancelled": False, "selected_text": "selected"}

    async def _clone() -> dict[str, object]:
        calls.append(("clone", None))
        return {"cancelled": False}

    async def _navigate_tree(target_id: str, options: object | None = None) -> dict[str, object]:
        calls.append(("tree", (target_id, options)))
        return {"cancelled": False}

    async def _import_session(input_path: str, cwd_override: str | None = None) -> dict[str, object]:
        calls.append(("import", (input_path, cwd_override)))
        return {"cancelled": False}

    controller = CommandController(
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        get_extension_runner=lambda: None,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
        builtin_backend=BuiltinCommandBackend(
            new_session=_new_session,
            resume_session=_resume_session,
            fork_session=_fork,
            clone_session=_clone,
            navigate_tree=_navigate_tree,
            import_session=_import_session,
        ),
    )

    results = [
        asyncio.run(controller.execute_command_async("/new", "/tmp/next")),
        asyncio.run(controller.execute_command_async("/resume", "/tmp/session.jsonl")),
        asyncio.run(controller.execute_command_async("/fork", "entry-1 before")),
        asyncio.run(controller.execute_command_async("/clone", "")),
        asyncio.run(controller.execute_command_async("/tree", "entry-2 --summarize --label chosen")),
        asyncio.run(controller.execute_command_async("/import", "/tmp/import.jsonl /tmp/project")),
    ]

    assert [result.result for result in results if result is not None] == [
        {"source": "builtin", "command": "new", "status": "ok", "result": {"cancelled": False}},
        {"source": "builtin", "command": "resume", "status": "ok", "result": {"cancelled": False}},
        {
            "source": "builtin",
            "command": "fork",
            "status": "ok",
            "result": {"cancelled": False, "selected_text": "selected"},
        },
        {"source": "builtin", "command": "clone", "status": "ok", "result": {"cancelled": False}},
        {"source": "builtin", "command": "tree", "status": "ok", "result": {"cancelled": False}},
        {"source": "builtin", "command": "import", "status": "ok", "result": {"cancelled": False}},
    ]
    assert calls == [
        ("new", {"cwd": "/tmp/next"}),
        ("resume", ("/tmp/session.jsonl", None)),
        ("fork", ("entry-1", {"position": "before"})),
        ("clone", None),
        ("tree", ("entry-2", {"summarize": True, "label": "chosen"})),
        ("import", ("/tmp/import.jsonl", "/tmp/project")),
    ]


def test_command_controller_records_missing_command_without_resource_bundle(tmp_path) -> None:
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    diagnostics_service = DiagnosticsService()
    controller = CommandController(
        session_manager=manager,
        get_extension_runner=lambda: None,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: diagnostics_service,
    )

    assert asyncio.run(controller.execute_command_async("missing", "args")) is None

    records = diagnostics_service.get_diagnostics(code="command_not_found")
    assert len(records) == 1
    assert records[0].details == {"invocation_name": "missing", "args": "args"}


def test_command_controller_extracts_and_rejects_queued_extension_commands(tmp_path) -> None:
    async def _handler(args: str, ctx) -> None:
        del args, ctx

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="deploy-ext",
                source_path=Path("/tmp/project/extensions/deploy.py"),
                commands={"deploy": RegisteredCommand(name="deploy", handler=_handler)},
            )
        ]
    )
    controller = CommandController(
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        get_extension_runner=lambda: runner,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    assert controller.extract_extension_command_invocation("/deploy now") == ("deploy", "now")
    assert controller.extract_extension_command_invocation("deploy now") is None
    assert controller.extract_extension_command_invocation("/missing now") is None

    with pytest.raises(RuntimeError, match='Extension command "/deploy" cannot be queued'):
        controller.raise_if_queued_extension_command("/deploy now")


def test_command_controller_preflight_async_consumes_extension_command(tmp_path) -> None:
    calls: list[str] = []

    async def _handler(args: str, ctx) -> None:
        del ctx
        calls.append(args)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="deploy-ext",
                source_path=Path("/tmp/project/extensions/deploy.py"),
                commands={"deploy": RegisteredCommand(name="deploy", handler=_handler)},
            )
        ]
    )
    controller = CommandController(
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        get_extension_runner=lambda: runner,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    result = asyncio.run(controller.preflight_user_input_async("/deploy now"))

    assert result.consumed is True
    assert result.text == "/deploy now"
    assert calls == ["now"]


def test_command_controller_preflight_async_consumes_builtin_command(tmp_path) -> None:
    names: list[str | None] = []
    controller = CommandController(
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        get_extension_runner=lambda: None,
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
        builtin_backend=BuiltinCommandBackend(set_session_name=names.append),
    )

    result = asyncio.run(controller.preflight_user_input_async("/name Project Alpha"))

    assert result.consumed is True
    assert result.text == "/name Project Alpha"
    assert names == ["Project Alpha"]
