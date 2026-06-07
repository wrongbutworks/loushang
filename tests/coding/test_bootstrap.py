from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
from datetime import date

from loushang.ai.event_stream.stream import AssistantMessageEventStream
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, ToolCall, Usage, UserMessage


def _model() -> Model:
    return Model(
        id="faux-model",
        name="Faux",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(
            reasoning=True,
            input=("text",),
            context_window=128000,
            max_tokens=4096,
        ),
    )


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost={},
    )


def _assistant_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def _assistant_tool_call_message(tool_name: str = "calc", arguments: dict[str, object] | None = None) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[
            ToolCall(
                type="toolCall",
                id="tc_1",
                name=tool_name,
                arguments=arguments or {"x": 1},
            )
        ],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="toolUse",
        error_message=None,
        timestamp=0.0,
    )


def _stream_with_final_message(message: AssistantMessage) -> AssistantMessageEventStream:
    stream = AssistantMessageEventStream()
    stream.push({"type": "start", "partial": message})
    if message.content and isinstance(message.content[0], TextPart):
        stream.push({"type": "text_start", "content_index": 0, "partial": message})
        stream.push({"type": "text_delta", "content_index": 0, "delta": message.content[0].text, "partial": message})
        stream.push({"type": "text_end", "content_index": 0, "content": message.content[0].text, "partial": message})
    elif message.content and isinstance(message.content[0], ToolCall):
        stream.push({"type": "toolcall_start", "content_index": 0, "partial": message})
        stream.push({"type": "toolcall_delta", "content_index": 0, "delta": '{"x": 1}', "partial": message})
        stream.push({"type": "toolcall_end", "content_index": 0, "tool_call": message.content[0], "partial": message})
    stream.push({"type": "done", "reason": message.stop_reason, "message": message})  # type: ignore[typeddict-item]
    return stream


def _run_git(args: list[str], *, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _runtime_footer(cwd: str) -> str:
    return f"Current date: {date.today().isoformat()}\nCurrent working directory: {cwd}"


def test_create_agent_session_uses_manager_header_as_agent_session_id(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)

    session = create_agent_session(
        session_manager=manager,
        model=_model(),
    )

    assert session.session_manager is manager
    assert session.agent.session_id == manager.get_header().id
    assert session.get_model_selection() is not None
    assert session.get_model_selection().model_id == "faux-model"


def test_create_agent_session_result_returns_sdk_creation_snapshot(tmp_path) -> None:
    from loushang.coding import CreateAgentSessionResult, create_agent_session_result
    from loushang.coding.bootstrap import create_services
    from loushang.coding.control import ControlConfig, SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    missing_package_root = tmp_path / "missing-package"
    project_root.mkdir()
    services = create_services(
        settings_manager=SettingsManager(ControlConfig(package_roots=(str(missing_package_root),)))
    )
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    result = create_agent_session_result(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    assert isinstance(result, CreateAgentSessionResult)
    assert result.session.session_manager is manager
    assert result.resource_bundle is result.session.resource_bundle
    assert result.cwd_bound_services_audit is result.session.cwd_bound_services_audit
    assert [record.code for record in result.diagnostics if record.phase == "startup" and record.type != "info"] == [
        "package_root_unavailable"
    ]

    services.diagnostics_service.capture_failure(
        code="later_warning",
        error="later",
        phase="startup",
        source="bootstrap",
        level="warning",
        session_id=result.session.session_id,
    )

    assert [record.code for record in result.diagnostics if record.phase == "startup" and record.type != "info"] == [
        "package_root_unavailable"
    ]


def test_create_agent_session_services_builds_cwd_bound_services(tmp_path) -> None:
    from loushang.coding import AgentSessionServices, create_agent_session_services

    project_root = tmp_path / "project"
    settings_dir = project_root / ".loushang"
    settings_dir.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("Project guidance", encoding="utf-8")
    (settings_dir / "settings.json").write_text(
        '{"system_prompt": "Project prompt."}',
        encoding="utf-8",
    )

    services = create_agent_session_services(
        cwd=project_root,
        global_settings_path=tmp_path / "global" / "settings.json",
    )

    assert isinstance(services, AgentSessionServices)
    assert services.cwd == str(project_root.resolve())
    assert services.settings_manager.get_settings().system_prompt == "Project prompt."
    assert services.resource_bundle is not None
    assert services.resource_bundle.agents_md == "Project guidance"
    assert services.diagnostics == ()


def test_create_agent_session_from_services_uses_cwd_bound_services(tmp_path) -> None:
    from loushang.coding import (
        create_agent_session_from_services,
        create_agent_session_services,
    )
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    agent_services = create_agent_session_services(
        cwd=project_root,
        global_settings_path=tmp_path / "global" / "settings.json",
    )
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    result = create_agent_session_from_services(
        agent_services=agent_services,
        session_manager=manager,
        model=_model(),
    )

    assert result.session.settings_manager is agent_services.settings_manager
    assert result.session.resource_loader is agent_services.resource_loader
    assert result.session.session_manager is manager


def test_create_agent_session_services_loads_extension_flags_and_values(tmp_path) -> None:
    from loushang.coding import create_agent_session_services

    project_root = tmp_path / "project"
    extensions_dir = project_root / "extensions"
    extensions_dir.mkdir(parents=True)
    (extensions_dir / "flags.py").write_text(
        "\n".join(
            [
                "def register(api):",
                "    api.register_flag('plan', type='boolean', default=False)",
                "    api.register_flag('request-id', type='string')",
            ]
        ),
        encoding="utf-8",
    )

    agent_services = create_agent_session_services(
        cwd=project_root,
        global_settings_path=tmp_path / "global" / "settings.json",
        extension_flag_values={"plan": True, "request-id": "req-123"},
    )

    assert agent_services.extension_runner is not None
    assert [flag.name for flag in agent_services.extension_runner.get_flags()] == ["plan", "request-id"]
    assert agent_services.extension_runner.get_flag_values() == {
        "plan": True,
        "request-id": "req-123",
    }
    assert agent_services.diagnostics == ()


def test_create_agent_session_from_services_applies_extension_flag_values(tmp_path) -> None:
    from loushang.coding import (
        create_agent_session_from_services,
        create_agent_session_services,
    )
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    extensions_dir = project_root / "extensions"
    extensions_dir.mkdir(parents=True)
    (extensions_dir / "flags.py").write_text(
        "\n".join(
            [
                "def register(api):",
                "    api.register_flag('plan', type='boolean', default=False)",
                "    api.register_flag('request-id', type='string')",
            ]
        ),
        encoding="utf-8",
    )
    agent_services = create_agent_session_services(
        cwd=project_root,
        global_settings_path=tmp_path / "global" / "settings.json",
        extension_flag_values={"plan": True, "request-id": "req-123"},
    )
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    result = create_agent_session_from_services(
        agent_services=agent_services,
        session_manager=manager,
        model=_model(),
    )

    assert result.session.extension_runner.get_flag_values() == {
        "plan": True,
        "request-id": "req-123",
    }


def test_create_agent_session_services_reports_extension_flag_value_errors(tmp_path) -> None:
    from loushang.coding import create_agent_session_services

    project_root = tmp_path / "project"
    extensions_dir = project_root / "extensions"
    extensions_dir.mkdir(parents=True)
    (extensions_dir / "flags.py").write_text(
        "\n".join(
            [
                "def register(api):",
                "    api.register_flag('request-id', type='string')",
            ]
        ),
        encoding="utf-8",
    )

    agent_services = create_agent_session_services(
        cwd=project_root,
        global_settings_path=tmp_path / "global" / "settings.json",
        extension_flag_values={"unknown": True, "request-id": True},
    )

    assert [record.code for record in agent_services.diagnostics] == [
        "unknown_extension_flag",
        "extension_flag_value_required",
    ]
    assert agent_services.extension_runner is not None
    assert agent_services.extension_runner.get_flag_values() == {}


def test_audit_cwd_bound_services_reports_project_settings_mismatch(tmp_path) -> None:
    from loushang.coding.bootstrap import audit_cwd_bound_services, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.control.settings_store import default_project_settings_path
    from loushang.coding.store import SessionManager

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    settings_manager = SettingsManager(project_settings_path=default_project_settings_path(project_a))
    services = create_services(settings_manager=settings_manager)
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_b), persist=False)

    audit = audit_cwd_bound_services(session_manager=manager, services=services)

    assert audit.ok is False
    assert [issue.code for issue in audit.issues] == ["settings_project_cwd_mismatch"]
    assert audit.issues[0].details["project_root"] == str(project_a)
    assert audit.issues[0].details["session_cwd"] == str(project_b)


def test_audit_cwd_bound_services_accepts_matching_resource_bundle(tmp_path) -> None:
    from loushang.coding.bootstrap import audit_cwd_bound_services, create_services
    from loushang.coding.loader import ResourceBundle
    from loushang.coding.store import SessionManager

    project = tmp_path / "project"
    project.mkdir()
    services = create_services()
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project), persist=False)

    audit = audit_cwd_bound_services(
        session_manager=manager,
        services=services,
        resource_bundle=ResourceBundle(cwd=project),
    )

    assert audit.ok is True
    assert audit.issues == []


def test_create_agent_session_runtime_can_build_services_per_session_cwd(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session_runtime, create_services

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    created_cwds: list[str] = []

    def services_factory(cwd: str):
        created_cwds.append(cwd)
        return create_services()

    async def scenario() -> None:
        runtime = create_agent_session_runtime(
            session_dir=tmp_path / "sessions",
            model=_model(),
            services_factory=services_factory,
            persist=False,
        )

        first = await runtime.new_session(cwd=project_a)
        second = await runtime.new_session(cwd=project_b)

        assert created_cwds == [str(project_a.resolve()), str(project_b.resolve())]
        assert first.settings_manager is not second.settings_manager
        assert first.resource_loader is not second.resource_loader
        assert second.cwd_bound_services_audit.ok is True

    asyncio.run(scenario())


def test_create_agent_session_runtime_builds_working_default_sessions(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session_runtime

    async def stream_fn(model, context, options=None):
        return _stream_with_final_message(_assistant_message("bootstrapped"))

    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        runtime = create_agent_session_runtime(
            session_dir=tmp_path,
            model=_model(),
            stream_fn=stream_fn,
            persist=False,
        )

        session = await runtime.create_session(cwd=str(project))
        await session.prompt("hi")

        assert runtime.get_current_session() is session
        assert session.agent.session_id == session.session_manager.get_header().id
        assert [message.content[0].text for message in session.get_session_context().messages] == ["hi", "bootstrapped"]

    asyncio.run(scenario())


def test_create_agent_session_injects_settings_and_agents_md_into_system_prompt(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    project_root = tmp_path / "project"
    nested = project_root / "work" / "deep"
    nested.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("Use repo conventions.", encoding="utf-8")

    services = create_services(system_prompt="Base system prompt.")
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(nested), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        tool_registry=registry,
        active_tool_names=["bash"],
    )

    expected_context = (
        "# Project Context\n\n"
        "Project-specific instructions and guidelines:\n\n"
        f"## {project_root / 'AGENTS.md'}\n\n"
        "Use repo conventions."
    )
    assert session.agent.system_prompt == (
        f"Base system prompt.\n\n{expected_context}\n\nAvailable tools:\n"
        "- bash: Execute shell commands. Prefer a single command string; use cwd for the working directory.\n"
        "- Use bash for shell pipelines, redirects, and commands that are easier to express through the user's shell.\n"
        "- Prefer read, grep, find, ls, write, and edit for file operations when those tools are more precise.\n\n"
        f"{_runtime_footer(str(nested))}"
    )
    assert session.get_active_tool_names() == ["bash"]
    assert services.resource_loader.get_resource_bundle().agents_md == "Use repo conventions."


def test_create_agent_session_applies_allowed_tool_names_to_default_active_tools(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        model=_model(),
        tool_registry=registry,
        allowed_tool_names=["read", "grep"],
    )

    assert session.get_active_tool_names() == ["read", "grep"]
    assert [tool.name for tool in session.agent.tools] == ["read", "grep"]
    assert [definition.name for definition in session.get_all_tools()] == ["read", "grep"]
    assert "- bash:" not in session.agent.system_prompt


def test_create_agent_session_no_tools_builtin_keeps_dynamic_extension_tools(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ExtensionDescriptor,
        ResourceBundle,
    )
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    extension_file = tmp_path / "extensions" / "dynamic.py"
    extension_file.parent.mkdir(parents=True)
    extension_file.write_text(
        "\n".join(
            [
                "from loushang.agent.types import AgentToolResult",
                "from loushang.ai.types import TextPart",
                "from loushang.coding.tools import ToolDefinition",
                "",
                "async def _execute(tool_call_id, params, signal=None, on_update=None):",
                "    return AgentToolResult(content=[TextPart(type='text', text='ok')], details={})",
                "",
                "def register(api):",
                "    def _session_start(event, ctx):",
                "        api.register_tool(",
                "            ToolDefinition(",
                "                name='dynamic_tool',",
                "                label='Dynamic Tool',",
                "                description='Dynamic extension tool',",
                "                parameters={'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},",
                "                execute=_execute,",
                "                prompt_snippet='Run dynamic behavior',",
                "            )",
                "        )",
                "    api.on('session_start', _session_start)",
            ]
        ),
        encoding="utf-8",
    )

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=tmp_path,
                extensions=[
                    ExtensionDescriptor(
                        name="dynamic",
                        source_path=extension_file.parent,
                        entry_path=extension_file,
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    registry = ToolRegistry()
    register_builtin_tools(registry)
    session = create_agent_session(
        session_manager=SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False),
        services=create_services(resource_loader=_Loader(), system_prompt="Base system prompt."),
        model=_model(),
        tool_registry=registry,
        no_tools="builtin",
    )

    asyncio.run(session.start_extension_runtime())

    assert "dynamic_tool" in [definition.name for definition in session.get_all_tools()]
    assert "read" in [definition.name for definition in session.get_all_tools()]
    assert session.get_active_tool_names() == ["dynamic_tool"]
    assert "- dynamic_tool: Run dynamic behavior" in session.agent.system_prompt
    assert "- read:" not in session.agent.system_prompt
    assert "- bash:" not in session.agent.system_prompt


def test_create_agent_session_no_tools_all_hides_dynamic_extension_tools_and_prompts_none(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ExtensionDescriptor,
        ResourceBundle,
    )
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    extension_file = tmp_path / "extensions" / "dynamic.py"
    extension_file.parent.mkdir(parents=True)
    extension_file.write_text(
        "\n".join(
            [
                "from loushang.agent.types import AgentToolResult",
                "from loushang.ai.types import TextPart",
                "from loushang.coding.tools import ToolDefinition",
                "",
                "async def _execute(tool_call_id, params, signal=None, on_update=None):",
                "    return AgentToolResult(content=[TextPart(type='text', text='ok')], details={})",
                "",
                "def register(api):",
                "    def _session_start(event, ctx):",
                "        ctx.register_tool(",
                "            ToolDefinition(",
                "                name='dynamic_tool',",
                "                label='Dynamic Tool',",
                "                description='Dynamic extension tool',",
                "                parameters={'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False},",
                "                execute=_execute,",
                "                prompt_snippet='Run dynamic behavior',",
                "            )",
                "        )",
                "    api.on('session_start', _session_start)",
            ]
        ),
        encoding="utf-8",
    )

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=tmp_path,
                extensions=[
                    ExtensionDescriptor(
                        name="dynamic",
                        source_path=extension_file.parent,
                        entry_path=extension_file,
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    registry = ToolRegistry()
    register_builtin_tools(registry)
    session = create_agent_session(
        session_manager=SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False),
        services=create_services(resource_loader=_Loader(), system_prompt="Base system prompt."),
        model=_model(),
        tool_registry=registry,
        no_tools="all",
    )

    asyncio.run(session.start_extension_runtime())

    assert session.get_all_tools() == []
    assert session.get_active_tool_names() == []
    assert "Available tools:\n(none)" in session.agent.system_prompt
    assert "dynamic_tool" not in session.agent.system_prompt


def test_create_agent_session_runtime_applies_allowed_tool_names(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    project = tmp_path / "project"
    project.mkdir()
    registry = ToolRegistry()
    register_builtin_tools(registry)

    runtime = create_agent_session_runtime(
        session_dir=tmp_path / "sessions",
        model=_model(),
        tool_registry=registry,
        allowed_tool_names=["read", "grep"],
        persist=False,
    )

    session = asyncio.run(runtime.create_session(cwd=str(project)))

    assert isinstance(session.session_manager, SessionManager)
    assert session.get_active_tool_names() == ["read", "grep"]
    assert [definition.name for definition in session.get_all_tools()] == ["read", "grep"]


def test_create_agent_session_uses_settings_package_roots_for_external_package_prompts(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    package_root = tmp_path / "packages" / "review-pack"
    prompts_dir = package_root / "prompts"
    project_root.mkdir()
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "review.md").write_text("Package review rules", encoding="utf-8")

    global_settings_path = tmp_path / "global-settings.json"
    global_settings_path.write_text(
        json.dumps(
            {
                "system_prompt": "Base system prompt.",
                "package_roots": [str(package_root)],
            }
        ),
        encoding="utf-8",
    )

    services = create_services(
        settings_manager=SettingsManager(global_settings_path=global_settings_path),
    )
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    assert "Base system prompt." in session.agent.system_prompt
    assert "Package review rules" in session.agent.system_prompt
    assert [descriptor.source_kind for descriptor in services.resource_loader.get_resource_bundle().prompts] == [
        "external_package"
    ]
    assert [
        (command.name, command.source_info.origin, command.source_info.base_dir)
        for command in session.list_commands()
        if command.source != "builtin"
    ] == [("review", "package", str(prompts_dir))]


def test_reload_extension_runtime_reloads_settings_resource_roots(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    first_root = tmp_path / "first-resources"
    second_root = tmp_path / "second-resources"
    project_root.mkdir()
    (first_root / "prompts").mkdir(parents=True)
    (second_root / "prompts").mkdir(parents=True)
    (first_root / "prompts" / "freshness.md").write_text("Old global prompt", encoding="utf-8")
    (second_root / "prompts" / "freshness.md").write_text("Fresh global prompt", encoding="utf-8")

    global_settings_path = tmp_path / "global-settings.json"
    global_settings_path.write_text(
        json.dumps({"system_prompt": "Base system prompt.", "resource_roots": [str(first_root)]}),
        encoding="utf-8",
    )

    services = create_services(settings_manager=SettingsManager(global_settings_path=global_settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)
    session = create_agent_session(session_manager=manager, services=services, model=_model())

    assert "Old global prompt" in session.agent.system_prompt
    assert "Fresh global prompt" not in session.agent.system_prompt

    global_settings_path.write_text(
        json.dumps({"system_prompt": "Base system prompt.", "resource_roots": [str(second_root)]}),
        encoding="utf-8",
    )

    asyncio.run(session.reload_extension_runtime())

    assert services.settings_manager.get_resource_roots() == [str(second_root)]
    assert "Old global prompt" not in session.agent.system_prompt
    assert "Fresh global prompt" in session.agent.system_prompt


def test_create_agent_session_uses_settings_package_sources_with_filters(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    package_root = tmp_path / "packages" / "review-pack"
    prompts_dir = package_root / "prompts"
    skills_dir = package_root / "skills"
    project_root.mkdir()
    prompts_dir.mkdir(parents=True)
    (skills_dir / "review").mkdir(parents=True)
    (skills_dir / "debug").mkdir(parents=True)
    (prompts_dir / "review.md").write_text("Package review rules", encoding="utf-8")
    (prompts_dir / "debug.md").write_text("Package debug rules", encoding="utf-8")
    (skills_dir / "review" / "SKILL.md").write_text("Review skill", encoding="utf-8")
    (skills_dir / "debug" / "SKILL.md").write_text("Debug skill", encoding="utf-8")

    global_settings_path = tmp_path / "global-settings.json"
    global_settings_path.write_text(
        json.dumps(
            {
                "system_prompt": "Base system prompt.",
                "packages": [
                    {
                        "source": str(package_root),
                        "prompts": ["review.md"],
                        "skills": ["review"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    services = create_services(settings_manager=SettingsManager(global_settings_path=global_settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(session_manager=manager, services=services, model=_model())

    bundle = services.resource_loader.get_resource_bundle()
    assert "Package review rules" in session.agent.system_prompt
    assert "Package debug rules" not in session.agent.system_prompt
    assert [prompt.name for prompt in bundle.prompts] == ["review"]
    assert [skill.name for skill in bundle.skills] == ["review"]


def test_create_agent_session_uses_settings_plugin_sources_for_external_package_resources(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    plugin_root = tmp_path / "plugins" / "debug-pack"
    prompts_dir = plugin_root / "prompts"
    skills_dir = plugin_root / "skills" / "debug"
    extensions_dir = plugin_root / "extensions"
    project_root.mkdir()
    prompts_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    extensions_dir.mkdir(parents=True)
    (plugin_root / "plugin.json").write_text(json.dumps({"name": "debug-pack"}), encoding="utf-8")
    (prompts_dir / "debug.md").write_text("Plugin debug prompt", encoding="utf-8")
    (skills_dir / "SKILL.md").write_text("Plugin debug skill", encoding="utf-8")
    (extensions_dir / "deploy.py").write_text(
        "\n".join(
            [
                "def register(api):",
                "    async def deploy(args, ctx):",
                "        pass",
                "    api.register_command('deploy', description='Deploy from plugin', handler=deploy)",
            ]
        ),
        encoding="utf-8",
    )

    project_settings_path = tmp_path / "project-settings.json"
    project_settings_path.write_text(
        json.dumps(
            {
                "system_prompt": "Base system prompt.",
                "plugin_sources": [str(plugin_root)],
            }
        ),
        encoding="utf-8",
    )

    services = create_services(
        settings_manager=SettingsManager(project_settings_path=project_settings_path),
    )
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    bundle = services.resource_loader.get_resource_bundle()
    assert "Plugin debug prompt" in session.agent.system_prompt
    assert [skill.name for skill in bundle.skills] == ["debug"]
    assert bundle.skills[0].source_kind == "external_package"
    assert [
        (command.name, command.source_info.origin, command.source_info.base_dir)
        for command in session.list_commands()
        if command.source == "extension"
    ] == [("deploy", "package", str(extensions_dir))]


def test_create_agent_session_materializes_git_package_sources_by_default(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session
    from loushang.coding.store import SessionManager

    source_repo = tmp_path / "source"
    source_repo.mkdir()
    (source_repo / "plugin.json").write_text(
        json.dumps({"name": "review-pack", "version": "1.0.0"}),
        encoding="utf-8",
    )
    _run_git(["init"], cwd=source_repo)
    _run_git(["config", "user.email", "test@example.invalid"], cwd=source_repo)
    _run_git(["config", "user.name", "Test User"], cwd=source_repo)
    _run_git(["add", "."], cwd=source_repo)
    _run_git(["commit", "-m", "initial"], cwd=source_repo)
    remote_repo = tmp_path / "review-pack.git"
    _run_git(["clone", "--bare", str(source_repo), str(remote_repo)], cwd=tmp_path)

    manager = SessionManager.new(session_dir=tmp_path / ".loushang" / "sessions", cwd=str(tmp_path), persist=False)
    session = create_agent_session(session_manager=manager, model=_model())

    record = asyncio.run(session.materialize_package(remote_repo.as_uri()))

    assert record["lifecycle"] == "installed"
    assert record["targetPath"] == str(tmp_path / ".loushang" / "packages" / "review-pack")


def test_create_agent_session_auto_materializes_configured_remote_package_sources(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    (source_repo / "resources" / "prompts").mkdir(parents=True)
    (source_repo / "prompts").mkdir()
    (source_repo / "resources" / "prompts" / "review.md").write_text("Remote package prompt", encoding="utf-8")
    (source_repo / "prompts" / "ignored.md").write_text("Ignored root prompt", encoding="utf-8")
    (source_repo / "loushang-package.json").write_text(
        json.dumps({"name": "review-pack", "version": "1.0.0", "packageRoot": "resources"}),
        encoding="utf-8",
    )
    _run_git(["init"], cwd=source_repo)
    _run_git(["config", "user.email", "test@example.invalid"], cwd=source_repo)
    _run_git(["config", "user.name", "Test User"], cwd=source_repo)
    _run_git(["add", "."], cwd=source_repo)
    _run_git(["commit", "-m", "initial"], cwd=source_repo)
    remote_repo = tmp_path / "review-pack.git"
    _run_git(["clone", "--bare", str(source_repo), str(remote_repo)], cwd=tmp_path)

    global_settings_path = tmp_path / "global-settings.json"
    global_settings_path.write_text(json.dumps({"packages": [remote_repo.as_uri()]}), encoding="utf-8")
    services = create_services(settings_manager=SettingsManager(global_settings_path=global_settings_path))
    manager = SessionManager.new(session_dir=tmp_path / ".loushang" / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(session_manager=manager, services=services, model=_model())

    assert "Remote package prompt" in session.agent.system_prompt
    assert "Ignored root prompt" not in session.agent.system_prompt
    assert session.get_packages()[0]["lifecycle"] == "installed"


def test_create_agent_session_applies_disabled_plugin_sources(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    plugin_root = tmp_path / "plugins" / "debug-pack"
    prompts_dir = plugin_root / "prompts"
    project_root.mkdir()
    prompts_dir.mkdir(parents=True)
    (plugin_root / "plugin.json").write_text(json.dumps({"name": "debug-pack"}), encoding="utf-8")
    (prompts_dir / "debug.md").write_text("Plugin debug prompt", encoding="utf-8")

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "plugin_sources": [str(plugin_root)],
                "disabled_plugins": ["debug-pack"],
            }
        ),
        encoding="utf-8",
    )

    services = create_services(settings_manager=SettingsManager(project_settings_path=settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    assert "Plugin debug prompt" not in session.agent.system_prompt


def test_create_agent_session_marks_disabled_skills(tmp_path) -> None:
    import json

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    skill_dir = project_root / "skills" / "debug"
    project_root.mkdir()
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Debug skill", encoding="utf-8")

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"disabled_skills": ["debug"]}), encoding="utf-8")

    services = create_services(settings_manager=SettingsManager(project_settings_path=settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    assert [skill.name for skill in session.resource_bundle.skills] == ["debug"]
    assert session.resource_bundle.skills[0].enabled is False


def test_create_agent_session_includes_tool_prompt_from_registry(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    services = create_services(system_prompt="Base system prompt.")
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        tool_registry=registry,
        active_tool_names=["bash"],
    )

    assert "Available tools:" in session.agent.system_prompt
    assert "bash" in session.agent.system_prompt


def test_create_agent_session_synthesizes_definitions_from_legacy_tools(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolRegistry, register_builtin_tools

    services = create_services(system_prompt="Base system prompt.")
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        tools=registry.list_enabled_tools(),
    )

    assert session.get_active_tool_names() == ["read", "bash", "edit", "write"]
    assert [definition.name for definition in session.get_all_tools()] == [
        "bash",
        "read",
        "ls",
        "find",
        "grep",
        "write",
        "edit",
    ]
    assert "Available tools:" in session.agent.system_prompt


def test_create_agent_session_defaults_custom_tools_active_without_defaulting_all_builtins(tmp_path) -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import (
        ToolDefinition,
        ToolRegistry,
        register_builtin_tools,
    )

    async def execute_custom_tool(tool_call_id: str, params: dict[str, object], signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[], details={})

    services = create_services(system_prompt="Base system prompt.")
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)
    registry.register_tool(
        ToolDefinition(
            name="custom_tool",
            label="Custom Tool",
            description="custom tool",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            execute=execute_custom_tool,
        )
    )

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        tool_registry=registry,
    )

    assert session.get_active_tool_names() == ["read", "bash", "edit", "write", "custom_tool"]
    assert [definition.name for definition in session.get_all_tools()] == [
        "bash",
        "read",
        "ls",
        "find",
        "grep",
        "write",
        "edit",
        "custom_tool",
    ]
    assert "- custom_tool:" not in session.agent.system_prompt
    assert "- grep:" not in session.agent.system_prompt


def test_create_agent_session_marks_failing_builtin_tool_result_as_error(tmp_path) -> None:
    import asyncio

    from loushang.coding import SessionManager, ToolRegistry, register_builtin_tools
    from loushang.coding.bootstrap import create_agent_session

    async def stream_fn(model, context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message(tool_name="read", arguments={"path": "missing.txt"})
        )

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        model=_model(),
        stream_fn=stream_fn,
        tool_registry=registry,
        active_tool_names=["read"],
    )

    async def scenario() -> None:
        await session.prompt("read the missing file")

    asyncio.run(scenario())

    tool_results = [
        message
        for message in session.get_session_context().messages
        if getattr(message, "role", None) == "toolResult"
    ]

    assert len(tool_results) == 1
    assert tool_results[0].tool_name == "read"
    assert tool_results[0].is_error is True
    assert "missing.txt" in tool_results[0].content[0].text


def test_create_agent_session_records_auth_resolution_failure_for_default_model(tmp_path) -> None:
    from loushang.ai.model.domain import Auth, Endpoint
    from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import AuthManager
    from loushang.coding.session import ModelSelection
    from loushang.coding.store import SessionManager

    ai_registry = AiModelRegistry()
    ai_registry.register_endpoint(
        "demo",
        Endpoint(
            id="responses",
            api="responses",
            provider="demo",
            auth=Auth(api_key_env="LOUSHANG_TEST_DEMO_KEY"),
        ),
    )
    ai_registry.register_model(
        Model(
            id="secured",
            name="Secured",
            provider="demo",
            endpoint="responses",
            capabilities=Capabilities(reasoning=True, input=("text",), context_window=128000, max_tokens=4096),
        )
    )
    services = create_services(
        ai_model_registry=ai_registry,
        auth_manager=AuthManager(ai_registry=ai_registry, env={}),
    )
    services.settings_manager.set_default_model(ModelSelection(provider="demo", model_id="secured"))

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    session = create_agent_session(session_manager=manager, services=services)

    diagnostics = [record for record in session.get_last_diagnostics() if record.code == "model_auth_unresolved"]

    assert session.get_model_selection() == ModelSelection(provider="demo", model_id="secured")
    assert len(diagnostics) == 1
    assert diagnostics[0].type == "warning"
    assert diagnostics[0].source == "model"
    assert "LOUSHANG_TEST_DEMO_KEY" in diagnostics[0].message


def test_create_agent_session_uses_stored_oauth_credentials_for_auth_bridge(tmp_path, monkeypatch) -> None:
    import asyncio

    from loushang.ai.auth.types import OAuthCredentials
    from loushang.ai.model.domain import Auth, Endpoint
    from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import AuthManager
    from loushang.coding.session import ModelSelection
    from loushang.coding.store import SessionManager

    ai_registry = AiModelRegistry()
    ai_registry.register_endpoint(
        "demo",
        Endpoint(
            id="responses",
            api="responses",
            provider="demo",
            auth=Auth(api_key_env="LOUSHANG_TEST_DEMO_KEY"),
        ),
    )
    ai_registry.register_model(
        Model(
            id="secured",
            name="Secured",
            provider="demo",
            endpoint="responses",
            capabilities=Capabilities(reasoning=True, input=("text",), context_window=128000, max_tokens=4096),
        )
    )

    monkeypatch.setattr(
        "loushang.ai.auth.storage.load_credentials",
        lambda: {"demo": OAuthCredentials(provider="demo", access_token="oauth-token")},
    )
    monkeypatch.setattr(
        "loushang.ai.auth.oauth.get_oauth_api_key",
        lambda provider, credentials: {"apiKey": f"{provider}-oauth-key"},
    )

    services = create_services(
        ai_model_registry=ai_registry,
        auth_manager=AuthManager(ai_registry=ai_registry, env={}),
    )
    services.settings_manager.set_default_model(ModelSelection(provider="demo", model_id="secured"))

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    session = create_agent_session(session_manager=manager, services=services)

    api_key = session.agent.get_api_key("demo")
    if inspect.isawaitable(api_key):
        api_key = asyncio.run(api_key)

    diagnostics = [record for record in session.get_last_diagnostics() if record.code == "model_auth_unresolved"]

    assert api_key == "demo-oauth-key"
    assert diagnostics == []


def test_create_agent_session_marks_failing_mutation_builtin_tool_result_as_error(tmp_path) -> None:
    import asyncio

    from loushang.coding import SessionManager, ToolRegistry, register_builtin_tools
    from loushang.coding.bootstrap import create_agent_session

    (tmp_path / "main.py").write_text("alpha\n", encoding="utf-8")

    async def stream_fn(model, context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message(
                tool_name="edit",
                arguments={"path": "main.py", "edits": [{"oldText": "missing", "newText": "new"}]},
            )
        )

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    registry = ToolRegistry()
    register_builtin_tools(registry)

    session = create_agent_session(
        session_manager=manager,
        model=_model(),
        stream_fn=stream_fn,
        tool_registry=registry,
        active_tool_names=["edit"],
    )

    async def scenario() -> None:
        await session.prompt("edit the file")

    asyncio.run(scenario())

    tool_results = [
        message
        for message in session.get_session_context().messages
        if getattr(message, "role", None) == "toolResult"
    ]

    assert len(tool_results) == 1
    assert tool_results[0].tool_name == "edit"
    assert tool_results[0].is_error is True
    assert "missing" in tool_results[0].content[0].text


def test_create_agent_session_passes_resource_loader_into_agent_session(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import DefaultResourceLoader
    from loushang.coding.store import SessionManager

    class _RecordingLoader(DefaultResourceLoader):
        def __init__(self) -> None:
            super().__init__()
            self.discover_calls: list[str] = []

        def discover_resources(self, cwd):
            self.discover_calls.append(str(cwd))
            return super().discover_resources(cwd)

    loader = _RecordingLoader()
    services = create_services(resource_loader=loader)
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
    )

    assert session._resource_loader is loader
    assert loader.discover_calls == ["/tmp/project"]


def test_runtime_tool_failures_still_surface_as_tool_result_errors(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session
    from loushang.coding.store import SessionManager

    class RuntimeTool:
        name = "runtime_tool"
        label = "Runtime Tool"
        description = "runtime tool"
        parameters = {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        prepare_arguments = None

        async def execute(self, tool_call_id: str, params: dict[str, object], signal=None, on_update=None):
            del tool_call_id, params, signal, on_update
            raise RuntimeError("runtime tool exploded")

    async def stream_fn(model, context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_message("done"))
        return _stream_with_final_message(
            _assistant_tool_call_message(tool_name="runtime_tool", arguments={"value": 1})
        )

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    session = create_agent_session(
        session_manager=manager,
        model=_model(),
        stream_fn=stream_fn,
        tools=[RuntimeTool()],
    )

    async def scenario() -> None:
        await session.prompt("run the runtime tool")

    asyncio.run(scenario())

    tool_results = [
        message
        for message in session.get_session_context().messages
        if getattr(message, "role", None) == "toolResult"
    ]

    assert len(tool_results) == 1
    assert tool_results[0].tool_name == "runtime_tool"
    assert tool_results[0].is_error is True
    assert tool_results[0].content[0].text == "runtime tool exploded"
    diagnostics = [record for record in session.get_last_diagnostics() if record.code == "tool_execution_failed"]
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "tool_execution_failed"
    assert diagnostics[0].source == "tool"
    assert diagnostics[0].details["tool_name"] == "runtime_tool"


def test_create_agent_session_wires_coding_convert_to_llm(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session
    from loushang.coding.message import BranchSummaryMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    session = create_agent_session(
        session_manager=manager,
        model=_model(),
    )

    converted = session.agent.convert_to_llm(
        [BranchSummaryMessage(role="branchSummary", summary="done", from_id="b1", timestamp=0.0)]
    )

    assert len(converted) == 1
    assert converted[0].role == "user"


def test_create_agent_session_convert_to_llm_blocks_images_when_configured(tmp_path) -> None:
    from loushang.ai.types import ImagePart, TextPart, ToolResultMessage, UserMessage
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import ControlConfig, ImageSettings, SettingsManager
    from loushang.coding.store import SessionManager

    services = create_services(
        settings_manager=SettingsManager(ControlConfig(images=ImageSettings(block_images=True))),
    )
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    converted = session.agent.convert_to_llm(
        [
            UserMessage(
                role="user",
                content=[
                    TextPart(type="text", text="look"),
                    ImagePart(type="image", data="aGVsbG8=", mime_type="image/png"),
                ],
                timestamp=1.0,
            ),
            ToolResultMessage(
                role="toolResult",
                tool_call_id="tc1",
                tool_name="read",
                content=[
                    TextPart(type="text", text="result"),
                    ImagePart(type="image", data="aGVsbG8=", mime_type="image/png"),
                ],
                is_error=False,
                timestamp=2.0,
            ),
        ]
    )

    assert converted[0].content == [
        TextPart(type="text", text="look"),
        TextPart(type="text", text="Image reading is disabled."),
    ]
    assert converted[1].content == [
        TextPart(type="text", text="result"),
        TextPart(type="text", text="Image reading is disabled."),
    ]


def test_create_agent_session_merges_extension_resources_and_tools(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ExtensionDescriptor,
        PromptFragmentDescriptor,
        ResourceBundle,
    )
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolDefinition

    async def _execute_tool(tool_name: str, arguments: dict[str, object], context, signal):
        return {"tool_name": tool_name, "arguments": arguments}

    class _Extension:
        def resources_discover(self, bundle):
            from loushang.coding.extensions import ExtensionResourceContribution

            return ExtensionResourceContribution(
                prompt_descriptors=[
                    PromptFragmentDescriptor(
                        name="extension-rules",
                        source_path=Path("/tmp/extensions/demo"),
                        text="Extension rules",
                    )
                ]
            )

        def get_tools(self):
            return [
                ToolDefinition(
                    name="ext_tool",
                    label="Extension Tool",
                    description="Tool from extension",
                    parameters={},
                    execute=_execute_tool,
                )
            ]

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=Path(cwd),
                prompt_fragments=["Repo rules"],
                prompt_descriptors=[
                    PromptFragmentDescriptor(
                        name="AGENTS.md",
                        source_path=Path("/tmp/project/AGENTS.md"),
                        text="Repo rules",
                    )
                ],
                extensions=[
                    ExtensionDescriptor(
                        name="demo",
                        source_path=Path("/tmp/extensions/demo"),
                        metadata={"extension": _Extension()},
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    services = create_services(resource_loader=_Loader(), system_prompt="Base system prompt.")
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    assert "Base system prompt.\n\nRepo rules\n\nExtension rules" in session.agent.system_prompt
    assert session.get_active_tool_names() == ["ext_tool"]
    assert [definition.name for definition in session.get_all_tools()] == ["ext_tool"]
    assert session.getAllTools()[0]["sourceInfo"] == {
        "path": "/tmp/extensions/demo",
        "source": "filesystem",
        "scope": "project",
        "origin": "top-level",
        "baseDir": None,
    }
    assert session.resource_bundle.prompt_fragments == ["Repo rules", "Extension rules"]


def test_create_agent_session_wires_extension_tool_interception_into_agent(tmp_path) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ExtensionDescriptor,
        ResourceBundle,
    )
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolDefinition

    extension_file = tmp_path / "extensions" / "guard.py"
    extension_file.parent.mkdir(parents=True)
    extension_file.write_text(
        "\n".join(
            [
                "from loushang.agent.types import AgentToolResult",
                "from loushang.ai.types import TextPart",
                "from loushang.coding.extensions import ToolCallDecision, ToolResultDecision",
                "from loushang.coding.tools import ToolDefinition",
                "",
                "async def _ext_execute(tool_name, arguments, context, signal):",
                "    return AgentToolResult(",
                "        content=[TextPart(type='text', text=f\"ext:{arguments['y']}\")],",
                "        details={'value': arguments['y']},",
                "    )",
                "",
                "def register(api):",
                "    def _rewrite_tool_call(event, ctx):",
                "        return ToolCallDecision(tool_name='ext_tool', arguments={'y': event.args['x'] + 1})",
                "",
                "    def _rewrite_tool_result(event, ctx):",
                "        return ToolResultDecision(",
                "            result=AgentToolResult(",
                "                content=[TextPart(type='text', text='rewritten by extension')],",
                "                details={'rewritten': True},",
                "            )",
                "        )",
                "",
                "    api.on('tool_call', _rewrite_tool_call)",
                "    api.on('tool_result', _rewrite_tool_result)",
                "    api.register_tool(",
                "        ToolDefinition(",
                "            name='ext_tool',",
                "            label='Extension Tool',",
                "            description='Extension rewrite target',",
                "            parameters={",
                "                'type': 'object',",
                "                'properties': {'y': {'type': 'integer'}},",
                "                'required': ['y'],",
                "                'additionalProperties': False,",
                "            },",
                "            execute=_ext_execute,",
                "        )",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    async def _execute_tool(tool_name: str, arguments: dict[str, object], context, signal):
        from loushang.agent.types import AgentToolResult
        from loushang.ai.types import TextPart

        return AgentToolResult(
            content=[TextPart(type="text", text=f"base:{arguments['x']}")],
            details={"value": arguments["x"]},
        )

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=tmp_path,
                extensions=[
                    ExtensionDescriptor(
                        name="guard",
                        source_path=extension_file.parent,
                        entry_path=extension_file,
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    async def stream_fn(model, context, options=None):
        if any(getattr(message, "role", None) == "toolResult" for message in context.messages):
            return _stream_with_final_message(_assistant_message("done"))
        return _stream_with_final_message(_assistant_tool_call_message())

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    services = create_services(resource_loader=_Loader(), system_prompt="Base system prompt.")
    base_tool = ToolDefinition(
        name="calc",
        label="Calc",
        description="Base tool",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        },
        execute=_execute_tool,
    )

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        stream_fn=stream_fn,
        tools=[base_tool],
    )

    async def scenario() -> None:
        await session.prompt("use tool")

    asyncio.run(scenario())

    tool_results = [
        message
        for message in session.get_session_context().messages
        if getattr(message, "role", None) == "toolResult"
    ]

    assert len(tool_results) == 1
    assert tool_results[0].tool_name == "ext_tool"
    assert tool_results[0].content[0].text == "rewritten by extension"
    assert tool_results[0].details == {"rewritten": True}


def test_create_agent_session_records_nonfatal_extension_tool_conflicts(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ExtensionDescriptor,
        ResourceBundle,
    )
    from loushang.coding.store import SessionManager
    from loushang.coding.tools import ToolDefinition

    extension_file = tmp_path / "extensions" / "conflict.py"
    extension_file.parent.mkdir(parents=True)
    extension_file.write_text(
        "\n".join(
            [
                "from loushang.agent.types import AgentToolResult",
                "from loushang.ai.types import TextPart",
                "from loushang.coding.tools import ToolDefinition",
                "",
                "async def _ext_execute(tool_name, arguments, context, signal):",
                "    return AgentToolResult(",
                "        content=[TextPart(type='text', text='ext')],",
                "        details={'source': 'extension'},",
                "    )",
                "",
                "def register(api):",
                "    api.register_tool(",
                "        ToolDefinition(",
                "            name='calc',",
                "            label='Extension Calc',",
                "            description='Conflicting extension tool',",
                "            parameters={",
                "                'type': 'object',",
                "                'properties': {'x': {'type': 'integer'}},",
                "                'required': ['x'],",
                "                'additionalProperties': False,",
                "            },",
                "            execute=_ext_execute,",
                "        )",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    async def _execute_tool(tool_name: str, arguments: dict[str, object], context, signal):
        from loushang.agent.types import AgentToolResult
        from loushang.ai.types import TextPart

        return AgentToolResult(
            content=[TextPart(type="text", text=f"base:{arguments['x']}")],
            details={"value": arguments["x"]},
        )

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=tmp_path,
                extensions=[
                    ExtensionDescriptor(
                        name="conflict",
                        source_path=extension_file.parent,
                        entry_path=extension_file,
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    services = create_services(resource_loader=_Loader(), system_prompt="Base system prompt.")
    base_tool = ToolDefinition(
        name="calc",
        label="Calc",
        description="Base tool",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        },
        execute=_execute_tool,
    )

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        tools=[base_tool],
    )

    assert session.resource_bundle.extensions
    diagnostics = session.get_last_diagnostics()
    assert any(record.code == "extension_tool_conflict" for record in diagnostics)


def test_create_agent_session_passes_compaction_settings_to_session(tmp_path, monkeypatch) -> None:
    import asyncio

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.compaction import CompactionResult
    from loushang.coding.control import CompactionSettings
    from loushang.coding.store import SessionManager

    services = create_services()
    services.settings_manager.update_settings(
        compaction=CompactionSettings(enabled=True, reserve_tokens=8192, keep_recent_tokens=1)
    )

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="older context that should be compacted")],
            timestamp=0.0,
        )
    )
    assistant_id = manager.append_message(_assistant_message("recent reply"))

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    async def _fake_compact(**kwargs):
        preparation = kwargs["preparation"]
        assert preparation.first_kept_entry_id == assistant_id
        return CompactionResult(
            summary="condensed summary",
            first_kept_entry_id=assistant_id,
            tokens_before=preparation.tokens_before,
        )

    monkeypatch.setattr("loushang.coding.session.agent_session.compact", _fake_compact)

    result = asyncio.run(session.compact())

    assert result.first_kept_entry_id == assistant_id


def test_create_agent_session_passes_control_transport_and_thinking_settings(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import ControlConfig, RetrySettings, SettingsManager
    from loushang.coding.store import SessionManager

    services = create_services(
        settings_manager=SettingsManager(
            ControlConfig(
                transport="websocket",
                thinking_budgets={"low": 1024, "high": 4096},
                retry=RetrySettings(provider_max_retry_delay_ms=1234),
            )
        )
    )
    manager = SessionManager.new(session_dir=tmp_path, cwd=str(tmp_path), persist=False)

    session = create_agent_session(session_manager=manager, model=_model(), services=services)

    assert session.agent.transport == "websocket"
    assert session.agent.thinking_budgets == {"low": 1024, "high": 4096}
    assert session.agent.max_retry_delay_ms == 1234


def test_create_agent_session_applies_enabled_models_as_scoped_models(tmp_path) -> None:
    from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import ControlConfig, SettingsManager
    from loushang.coding.store import SessionManager

    first = _model()
    second = Model(
        id="alt-model",
        name="Alt",
        provider="alt",
        endpoint="responses",
        capabilities=Capabilities(
            reasoning=True,
            input=("text",),
            context_window=64000,
            max_tokens=2048,
        ),
    )
    ai_registry = AiModelRegistry()
    ai_registry.register_model(first)
    ai_registry.register_model(second)
    services = create_services(
        ai_model_registry=ai_registry,
        settings_manager=SettingsManager(ControlConfig(enabled_models=("faux-model:low", "alt-model:high", "missing"))),
    )
    manager = SessionManager.new(session_dir=tmp_path, cwd=str(tmp_path), persist=False)

    session = create_agent_session(session_manager=manager, model=first, services=services)

    assert session.scopedModels == [
        {"model": {"provider": "faux", "model_id": "faux-model"}, "thinkingLevel": "low"},
        {"model": {"provider": "alt", "model_id": "alt-model"}, "thinkingLevel": "high"},
    ]


def test_create_agent_session_records_resource_loading_diagnostics(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.loader import (
        DefaultResourceLoader,
        ResourceBundle,
        ResourceDiagnostic,
    )
    from loushang.coding.store import SessionManager

    class _Loader(DefaultResourceLoader):
        def discover_resources(self, cwd):
            bundle = ResourceBundle(
                cwd=Path(cwd),
                diagnostics=[
                    ResourceDiagnostic(
                        code="duplicate_prompt",
                        message="Duplicate prompt ignored.",
                        source_path=Path("/tmp/project/prompts/review.md"),
                    )
                ],
            )
            self._bundle = bundle
            return bundle

    services = create_services(resource_loader=_Loader())
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)

    create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    diagnostics = services.diagnostics_service.get_diagnostics(phase="resource_loading", source="loader")

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "duplicate_prompt"
    assert diagnostics[0].session_id == manager.get_header().id


def test_create_agent_session_records_startup_package_root_diagnostics(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    missing_package_root = tmp_path / "missing-package"
    project_root.mkdir()

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        f'{{"package_roots": ["{missing_package_root}"]}}',
        encoding="utf-8",
    )
    services = create_services(settings_manager=SettingsManager(global_settings_path=settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    diagnostics = services.diagnostics_service.get_diagnostics(
        phase="startup",
        source="bootstrap",
        code="package_root_unavailable",
    )

    assert [record.code for record in diagnostics] == ["package_root_unavailable"]
    assert diagnostics[0].type == "warning"
    assert diagnostics[0].session_id == manager.get_header().id
    assert diagnostics[0].details == {
        "check": "package_root",
        "ok": False,
        "package_root": str(missing_package_root),
    }


def test_create_agent_session_records_executable_source_identity_diagnostic(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    services = create_services()

    create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    diagnostics = services.diagnostics_service.get_diagnostics(
        phase="startup",
        source="bootstrap",
        code="executable_source_identity",
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].type == "info"
    assert diagnostics[0].session_id == manager.get_header().id
    assert diagnostics[0].source_path is not None
    assert diagnostics[0].details["check"] == "executable_source_identity"
    assert diagnostics[0].details["ok"] is True
    assert diagnostics[0].details["cwd"] == str(tmp_path)
    assert isinstance(diagnostics[0].details["python_executable"], str)
    assert isinstance(diagnostics[0].details["loushang_module_file"], str)
    assert isinstance(diagnostics[0].details["coding_module_file"], str)


def test_create_agent_session_records_package_lockfile_diagnostics(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.package import PackageMaterializer
    from loushang.coding.store import SessionManager

    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("not json", encoding="utf-8")
    materializer = PackageMaterializer(install_root=tmp_path / "packages", lockfile_path=lockfile)
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(tmp_path), persist=False)
    services = create_services()

    create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
        package_materializer=materializer,
    )

    diagnostics = services.diagnostics_service.get_diagnostics(
        phase="startup",
        source="bootstrap",
        code="package_lockfile_unreadable",
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].type == "warning"
    assert diagnostics[0].source_path == lockfile


def test_create_agent_session_records_invalid_plugin_source_and_continues(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session, create_services
    from loushang.coding.control import SettingsManager
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    invalid_plugin = tmp_path / "invalid-plugin"
    valid_package = tmp_path / "valid-package"
    prompts_dir = valid_package / "prompts"
    project_root.mkdir()
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "valid.md").write_text("Valid package prompt", encoding="utf-8")

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        (
            "{"
            f'"package_roots": ["{valid_package}"],'
            f'"plugin_sources": ["{invalid_plugin}"]'
            "}"
        ),
        encoding="utf-8",
    )
    services = create_services(settings_manager=SettingsManager(global_settings_path=settings_path))
    manager = SessionManager.new(session_dir=tmp_path / "sessions", cwd=str(project_root), persist=False)

    session = create_agent_session(
        session_manager=manager,
        services=services,
        model=_model(),
    )

    diagnostics = [
        record
        for record in services.diagnostics_service.get_diagnostics(phase="startup", source="bootstrap")
        if record.code == "plugin_source_unresolved"
    ]

    assert "Valid package prompt" in session.agent.system_prompt
    assert len(diagnostics) == 1
    assert diagnostics[0].type == "warning"
    assert diagnostics[0].details == {
        "plugin_source": str(invalid_plugin),
        "exception_type": "FileNotFoundError",
    }
