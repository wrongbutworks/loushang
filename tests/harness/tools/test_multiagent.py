from __future__ import annotations

import asyncio

from loushang.harness.multiagent import (
    AgentCaller,
    AgentInputMessage,
    AgentPath,
    AgentTypeRegistry,
    AgentTypeSpec,
    MultiAgentControl,
    SubagentRoundResult,
)
from loushang.harness.runtime import HostInputQueue
from loushang.harness.session.multiagent import (
    AgentInputFacade,
    SessionMultiAgentRuntime,
    SessionSubagentRequest,
)
from loushang.harness.tools.multiagent import (
    MULTIAGENT_TOOL_NAMES,
    MultiAgentToolPack,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry


class _Driver:
    def __init__(self) -> None:
        self.messages: list[AgentInputMessage] = []
        self.rounds = 0

    def deliver(self, message: AgentInputMessage) -> None:
        self.messages.append(message)

    async def run_round(self, *, round_id: int, mode: str) -> SubagentRoundResult:
        del round_id, mode
        self.rounds += 1
        return SubagentRoundResult(
            status="completed",
            final_message=f"result {self.rounds}",
            summary=f"summary {self.rounds}",
        )

    def abort(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


class _Factory:
    def __init__(self) -> None:
        self.drivers: dict[AgentPath, _Driver] = {}

    async def create_driver(self, request: SessionSubagentRequest) -> _Driver:
        driver = _Driver()
        self.drivers[request.record.path] = driver
        return driver


def test_common_tool_pack_registers_and_executes_the_live_session_surface() -> None:
    async def scenario() -> None:
        control = MultiAgentControl(
            agent_types=AgentTypeRegistry(
                (
                    AgentTypeSpec(
                        name="reviewer",
                        maximum_children=2,
                    ),
                )
            )
        )
        root_input: AgentInputFacade[AgentInputMessage] = AgentInputFacade(
            queue=HostInputQueue(),
            build_payload=lambda message: message,
        )
        factory = _Factory()
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=factory,
            root_input=root_input,
        )
        pack = MultiAgentToolPack(
            runtime=runtime,
            caller=AgentCaller(control.root_ref),
            default_wait_seconds=1,
        )
        registry = pack.register(WorkspaceToolRegistry())

        assert (
            tuple(definition.name for definition in registry.list_definitions())
            == MULTIAGENT_TOOL_NAMES
        )

        definitions = {definition.name: definition for definition in pack.definitions()}
        spawned = await definitions["spawn_agent"].execute(
            "spawn-1",
            {
                "name": "reviewer-1",
                "agent_type": "reviewer",
                "prompt": "Review the design.",
            },
            None,
            None,
        )
        assert spawned.details["path"] == "/root/reviewer-1"

        waited = await definitions["wait_agent"].execute(
            "wait-1",
            {},
            None,
            None,
        )
        assert waited.details["wait_expired"] is False
        assert waited.details["activity"]["kind"] == "completion_notice"

        sent = await definitions["send_message"].execute(
            "send-1",
            {
                "target": "/root/reviewer-1",
                "message": "Check the lifecycle too.",
            },
            None,
            None,
        )
        assert sent.details["triggered_new_round"] is True
        assert sent.details["round_id"] == 2

        second_wait = await definitions["wait_agent"].execute(
            "wait-2",
            {},
            None,
            None,
        )
        assert second_wait.details["activity"]["kind"] == "completion_notice"

        listed = await definitions["list_agents"].execute(
            "list-1",
            {},
            None,
            None,
        )
        assert [item["path"] for item in listed.details["agents"]] == [
            "/root",
            "/root/reviewer-1",
        ]
        assert listed.details["agents"][1]["round_id"] == 2
        assert listed.details["agents"][1]["workspace_ref"] is None
        assert listed.details["agents"][1]["artifact_refs"] == []
        assert listed.details["agents"][1]["change_set_ref"] is None

        closed = await definitions["close_agent"].execute(
            "close-1",
            {"target": "/root/reviewer-1"},
            None,
            None,
        )
        assert closed.details["agents"][0]["status"] == "closed"

    asyncio.run(scenario())


def test_wait_expiration_is_a_normal_tool_result_not_an_execution_timeout() -> None:
    async def scenario() -> None:
        control = MultiAgentControl()
        root_input: AgentInputFacade[AgentInputMessage] = AgentInputFacade(
            queue=HostInputQueue(),
            build_payload=lambda message: message,
        )
        runtime = SessionMultiAgentRuntime(
            control=control,
            child_factory=_Factory(),
            root_input=root_input,
        )
        pack = MultiAgentToolPack(
            runtime=runtime,
            caller=AgentCaller(control.root_ref),
            default_wait_seconds=0,
        )
        wait = next(
            definition
            for definition in pack.definitions()
            if definition.name == "wait_agent"
        )

        result = await wait.execute("wait-expired", {}, None, None)

        assert result.details["wait_expired"] is True
        assert "timed_out" not in result.details
        await runtime.dispose()

    asyncio.run(scenario())
