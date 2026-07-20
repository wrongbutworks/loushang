"""Shared mode abstractions used by print / rpc mode adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    Protocol,
    TextIO,
    TypedDict,
    cast,
)

from loushang.channel.product_host import (
    ProductHostAction,
    ProductHostActionType,
    ProductHostAdapter,
    dispatch_product_host_action,
    normalize_product_host_action,
)
from loushang.coding.event import JsonEventView
from loushang.coding.work_runtime import CodingWorkRuntime
from loushang.work import EventLogBackend

ModeName = Literal["text", "print", "json", "rpc"]
ModeActionType = ProductHostActionType


class ModeState(TypedDict, total=False):
    """Shape-aligned runtime mode state projection used by CLI/RPC print surfaces."""

    model: dict[str, object] | None
    thinkingLevel: str
    isStreaming: bool
    isCompacting: bool
    steeringMode: str
    followUpMode: str
    autoCompactionEnabled: bool
    messageCount: int
    pendingMessageCount: int
    sessionId: str
    sessionName: str
    sessionFile: str


@dataclass(frozen=True)
class ModeConfig:
    """Mode-level configuration shared by CLI and embedders."""

    mode: ModeName = "text"
    event_view: JsonEventView = "full"
    event_select: Sequence[str] | str | None = None
    render_tool_events: bool = False


ModeAction = ProductHostAction


def normalize_mode_action(action: ModeAction | Mapping[str, object]) -> ModeAction:
    """Compatibility wrapper for the Channel-owned host action normalizer."""

    return normalize_product_host_action(action, action_name="Mode action")


class ModeAdapter(ProductHostAdapter, Protocol):
    """Coding compatibility view of the generic Product host contract."""

    def get_mode_state(self) -> ModeState: ...


async def dispatch_mode_action(
    adapter: ModeAdapter,
    action: ModeAction | Mapping[str, object],
) -> int | ModeState:
    """Dispatch a mode action through the stable adapter contract."""

    result = await dispatch_product_host_action(
        adapter,
        action,
        get_state=lambda current: cast(ModeAdapter, current).get_mode_state(),
    )
    return cast(int | ModeState, result)


def create_mode_adapter(
    config: ModeConfig,
    *,
    runtime: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    session: Any | None = None,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: CodingWorkRuntime | None = None,
    method_id: str | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    step_index: int | None = None,
    step_title: str | None = None,
    planned_constraint: Mapping[str, object] | None = None,
    audit_policy: Mapping[str, object] | None = None,
    plan_facts: Mapping[str, object] | None = None,
    step_facts: Mapping[str, object] | None = None,
) -> ModeAdapter:
    """Create the concrete adapter for a configured coding mode."""

    if config.mode == "rpc":
        from loushang.coding.mode.rpc_mode import RpcMode

        return RpcMode(
            runtime=runtime,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            event_view=config.event_view,
            event_select=config.event_select,
            render_tool_events=config.render_tool_events,
        )

    if session is None:
        raise ValueError(f"{config.mode} mode requires a session")

    from loushang.coding.mode.print_mode import PrintMode

    return PrintMode(
        runtime=runtime,
        session=session,
        stdout=stdout,
        stderr=stderr,
        output_mode="text" if config.mode == "print" else config.mode,
        event_view=config.event_view,
        event_select=config.event_select,
        render_tool_events=config.render_tool_events,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
        method_id=method_id,
        plan_id=plan_id,
        step_id=step_id,
        step_index=step_index,
        step_title=step_title,
        planned_constraint=planned_constraint,
        audit_policy=audit_policy,
        plan_facts=plan_facts,
        step_facts=step_facts,
    )


async def run_mode(
    config: ModeConfig,
    *,
    runtime: Any,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO | None = None,
    session: Any | None = None,
    user_input: str | None = None,
    images: list[object] | None = None,
    follow_up_messages: Sequence[str] = (),
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: CodingWorkRuntime | None = None,
    method_id: str | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    step_index: int | None = None,
    step_title: str | None = None,
    planned_constraint: Mapping[str, object] | None = None,
    audit_policy: Mapping[str, object] | None = None,
    plan_facts: Mapping[str, object] | None = None,
    step_facts: Mapping[str, object] | None = None,
    dispose: bool = True,
) -> int:
    adapter = create_mode_adapter(
        config,
        runtime=runtime,
        session=session,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
        method_id=method_id,
        plan_id=plan_id,
        step_id=step_id,
        step_index=step_index,
        step_title=step_title,
        planned_constraint=planned_constraint,
        audit_policy=audit_policy,
        plan_facts=plan_facts,
        step_facts=step_facts,
    )
    if config.mode == "rpc":
        return await adapter.start(user_input)
    return await adapter.start(
        user_input,
        images=images,
        follow_up_messages=follow_up_messages,
        dispose=dispose,
    )
