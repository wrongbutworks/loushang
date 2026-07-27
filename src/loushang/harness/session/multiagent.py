"""Session-owned adapters for the product-neutral multi-agent control plane."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

from loushang.harness.multiagent.context import SubagentContextPlan
from loushang.harness.multiagent.control import MultiAgentControl
from loushang.harness.multiagent.run_handle import (
    HandleCloseResult,
    HandleDeliveryOutcome,
    RoundMode,
    SubagentRoundDriver,
    SubagentRoundResult,
    SubagentRunHandle,
)
from loushang.harness.multiagent.types import (
    AgentCaller,
    AgentCompletionNotice,
    AgentInputMessage,
    AgentPath,
    AgentRecord,
    AgentRef,
    AgentTypeSpec,
    ControlCaller,
    HostCaller,
    MultiAgentError,
)
from loushang.harness.runtime.execution import HostRuntime
from loushang.harness.runtime.input_queue import HostInputQueue

PayloadT = TypeVar("PayloadT")
SessionT = TypeVar("SessionT")

NoticeWakePolicy = Literal["queue_only", "wake_if_idle", "discard"]
InputActivityKind = Literal["message", "completion_notice", "steered", "cleared"]


@dataclass(frozen=True, slots=True)
class AgentInputActivity:
    sequence: int
    kind: InputActivityKind
    message_id: str | None


@dataclass(frozen=True, slots=True)
class AgentInputWaitOutcome:
    activity: AgentInputActivity | None
    timed_out: bool = False


MessagePayloadBuilder = Callable[[AgentInputMessage], PayloadT]
NoticeTextComposer = Callable[[AgentCompletionNotice], str]
MailboxSubmitter = Callable[[PayloadT], object]


class AgentInputFacade(Generic[PayloadT]):
    """Add source/activity semantics without duplicating HostInputQueue."""

    def __init__(
        self,
        *,
        queue: HostInputQueue[PayloadT],
        build_payload: MessagePayloadBuilder[PayloadT],
        submit_mailbox: MailboxSubmitter[PayloadT],
        compose_notice: NoticeTextComposer | None = None,
    ) -> None:
        self._queue = queue
        self._build_payload = build_payload
        self._compose_notice = compose_notice or standard_completion_notice_text
        self._submit_mailbox = submit_mailbox
        self._sequence = 0
        self._last_activity: AgentInputActivity | None = None
        self._waiters: set[asyncio.Future[AgentInputActivity]] = set()

    @property
    def queue(self) -> HostInputQueue[PayloadT]:
        return self._queue

    @property
    def activity_sequence(self) -> int:
        return self._sequence

    def enqueue_message(self, message: AgentInputMessage) -> AgentInputActivity:
        payload = self._build_payload(message)
        if message.kind == "mailbox":
            self._enqueue_mailbox(payload)
            return self._publish_activity("completion_notice", message.message_id)
        self._queue.enqueue(message.kind, text=message.text, payload=payload)
        return self._publish_activity("message", message.message_id)

    def enqueue_notice(
        self,
        notice: AgentCompletionNotice,
    ) -> AgentInputActivity:
        message = completion_notice_to_message(
            notice,
            text=self._compose_notice(notice),
        )
        return self.enqueue_message(message)

    def clear(self) -> None:
        self._queue.clear()
        self._publish_activity("cleared", None)

    def notify_steered(self, message_id: str | None = None) -> AgentInputActivity:
        """Wake waiters when the Product's existing user-steer path is used."""

        return self._publish_activity("steered", message_id)

    def _enqueue_mailbox(self, payload: PayloadT) -> None:
        self._submit_mailbox(payload)

    async def wait_for_activity(
        self,
        *,
        after_sequence: int | None = None,
        timeout: float | None = None,
    ) -> AgentInputWaitOutcome:
        observed = self._sequence if after_sequence is None else after_sequence
        if self._last_activity is not None and self._sequence > observed:
            return AgentInputWaitOutcome(self._last_activity)

        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[AgentInputActivity] = loop.create_future()
        self._waiters.add(waiter)
        try:
            activity = await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout)
            return AgentInputWaitOutcome(activity)
        except TimeoutError:
            return AgentInputWaitOutcome(None, timed_out=True)
        finally:
            self._waiters.discard(waiter)
            if not waiter.done():
                waiter.cancel()

    def _publish_activity(
        self,
        kind: InputActivityKind,
        message_id: str | None,
    ) -> AgentInputActivity:
        self._sequence += 1
        activity = AgentInputActivity(self._sequence, kind, message_id)
        self._last_activity = activity
        for waiter in tuple(self._waiters):
            if not waiter.done():
                waiter.set_result(activity)
        return activity


RoundOperation = Callable[[int, RoundMode], Awaitable[SubagentRoundResult]]


class SessionSubagentDriver(Generic[PayloadT]):
    """Reuse HostRuntime and HostInputQueue behind the RunHandle driver seam."""

    def __init__(
        self,
        *,
        input_facade: AgentInputFacade[PayloadT],
        run_round: RoundOperation,
        host_runtime: HostRuntime[SubagentRoundResult],
    ) -> None:
        self._input = input_facade
        self._run_round = run_round
        self._host = host_runtime

    @property
    def input_facade(self) -> AgentInputFacade[PayloadT]:
        return self._input

    def deliver(self, message: AgentInputMessage) -> None:
        self._input.enqueue_message(message)

    async def run_round(
        self,
        *,
        round_id: int,
        mode: RoundMode,
    ) -> SubagentRoundResult:
        return await self._host.run(
            lambda: self._run_round(round_id, mode),
            run_id=f"agent-round-{round_id}",
        )

    def abort(self) -> None:
        self._host.abort()

    async def dispose(self) -> None:
        await self._host.dispose()


@dataclass(frozen=True, slots=True)
class SessionSubagentRequest:
    record: AgentRecord
    parent: AgentRecord
    agent_type: AgentTypeSpec
    context_plan: SubagentContextPlan[Any] | None = None


class SessionSubagentFactory(Protocol):
    async def create_driver(
        self,
        request: SessionSubagentRequest,
    ) -> SubagentRoundDriver: ...


class RootAgentInput(Protocol):
    def enqueue_message(self, message: AgentInputMessage) -> object: ...

    def enqueue_notice(
        self,
        notice: AgentCompletionNotice,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class SessionTreeCloseResult:
    closed: tuple[AgentRecord, ...]
    dispose_errors: tuple[tuple[AgentRef, Exception], ...] = ()


class SessionMultiAgentRuntime:
    """Own live handles for exactly one Product session."""

    def __init__(
        self,
        *,
        control: MultiAgentControl,
        child_factory: SessionSubagentFactory,
        root_input: RootAgentInput | None = None,
        root_is_active: Callable[[], bool] | None = None,
        root_notice_wake: Callable[[], Awaitable[object] | object] | None = None,
        notice_wake_policy: NoticeWakePolicy = "queue_only",
    ) -> None:
        if notice_wake_policy not in {"queue_only", "wake_if_idle", "discard"}:
            raise ValueError(f"unsupported notice wake policy: {notice_wake_policy}")
        self.control = control
        self._child_factory = child_factory
        self._root_input = root_input
        self._root_is_active = root_is_active
        self._root_notice_wake = root_notice_wake
        self._notice_wake_policy = notice_wake_policy
        self._handles: dict[AgentRef, SubagentRunHandle] = {}
        self._inputs: dict[AgentRef, AgentInputFacade[Any]] = {}
        if isinstance(root_input, AgentInputFacade):
            self._inputs[control.root_ref] = root_input
        self._operation_lock = asyncio.Lock()
        self._notice_tasks: set[asyncio.Task[object]] = set()
        self._closed = False
        self._unsubscribe_notices = control.subscribe_notices(self._on_notice)

    async def spawn_child(
        self,
        *,
        caller: ControlCaller,
        parent_path: AgentPath,
        name: str,
        agent_type: str,
        initial_prompt: str,
        context_plan: SubagentContextPlan[Any] | None = None,
    ) -> AgentRecord:
        if not initial_prompt.strip():
            raise ValueError("initial child prompt must be non-empty")
        async with self._operation_lock:
            self._require_open_runtime()
            record = self.control.spawn(
                caller=caller,
                parent_path=parent_path,
                name=name,
                agent_type=agent_type,
            )
            if record.parent_ref is None:
                self.control.commit_closed(record.ref)
                raise RuntimeError("a child spawn must have a parent")
            parent = self.control.registry.get(record.parent_ref)
            spec = self.control.agent_type(agent_type)
            if parent is None or spec is None:
                self.control.commit_closed(record.ref)
                raise RuntimeError("spawn admission lost its parent or agent type")
            driver: SubagentRoundDriver | None = None
            try:
                driver = await self._child_factory.create_driver(
                    SessionSubagentRequest(
                        record=record,
                        parent=parent,
                        agent_type=spec,
                        context_plan=context_plan,
                    )
                )
                handle = SubagentRunHandle(
                    ref=record.ref,
                    control=self.control,
                    driver=driver,
                )
                self._handles[record.ref] = handle
                workspace_ref = getattr(driver, "workspace_ref", None)
                if isinstance(workspace_ref, str) and workspace_ref:
                    self.control.bind_workspace(
                        record.ref,
                        workspace_ref=workspace_ref,
                    )
                input_facade = getattr(driver, "input_facade", None)
                if isinstance(input_facade, AgentInputFacade):
                    self._inputs[record.ref] = input_facade
                intent = self.control.route_message(
                    caller=caller,
                    target=record.path,
                    text=initial_prompt,
                )
                await handle.deliver(intent.message)
                current = self.control.registry.get(record.ref)
                assert current is not None
                return current
            except BaseException:
                handle = self._handles.pop(record.ref, None)
                if handle is not None:
                    await handle.close()
                else:
                    if driver is not None:
                        await driver.dispose()
                    self.control.commit_closed(record.ref)
                raise

    async def send_message(
        self,
        *,
        caller: ControlCaller,
        target: str | AgentPath,
        text: str,
        kind: Literal["follow_up", "steering"] = "follow_up",
        references: tuple[str, ...] = (),
    ) -> HandleDeliveryOutcome:
        self._require_open_runtime()
        intent = self.control.route_message(
            caller=caller,
            target=target,
            text=text,
            kind=kind,
            references=references,
        )
        if intent.message.recipient_ref == self.control.root_ref:
            if self._root_input is None:
                raise MultiAgentError(
                    "agent_endpoint_unavailable",
                    "the root session input is not bound",
                )
            self._root_input.enqueue_message(intent.message)
            return HandleDeliveryOutcome(
                recipient_ref=self.control.root_ref,
                round_id=0,
                triggered_new_round=False,
            )
        return await self._require_handle(intent.message.recipient_ref).deliver(
            intent.message
        )

    async def await_terminal(
        self,
        *,
        caller: ControlCaller,
        target: AgentPath,
        timeout: float | None = None,
    ) -> AgentRecord:
        record = self.control.authorize_control(caller=caller, target=target)
        return await self._require_handle(record.ref).await_terminal(timeout=timeout)

    async def await_completion(
        self,
        *,
        caller: ControlCaller,
        target: AgentPath,
        timeout: float | None = None,
    ) -> AgentCompletionNotice:
        """Await one child round and expose its terminal payload to the Host."""

        record = await self.await_terminal(
            caller=caller,
            target=target,
            timeout=timeout,
        )
        notice = self.control.completion_notice(
            record.ref,
            round_id=record.round_id,
        )
        if notice is None:
            raise RuntimeError(
                f"agent {record.ref} reached {record.status} without a completion notice"
            )
        return notice

    async def wait_for_input(
        self,
        *,
        caller: AgentCaller,
        after_sequence: int,
        timeout: float | None = None,
    ) -> AgentInputWaitOutcome:
        record = self.control.authorize_control(
            caller=caller,
            target=caller.ref.path,
        )
        input_facade = self._inputs.get(record.ref)
        if input_facade is None:
            raise MultiAgentError(
                "agent_input_unavailable",
                f"agent has no observable input facade: {record.path}",
            )
        return await input_facade.wait_for_activity(
            after_sequence=after_sequence,
            timeout=timeout,
        )

    async def interrupt_agent(
        self,
        *,
        caller: ControlCaller,
        target: AgentPath,
    ) -> AgentRecord:
        record = self.control.authorize_control(caller=caller, target=target)
        if record.path == AgentPath.root():
            raise MultiAgentError(
                "root_lifecycle_owned",
                "the root agent is interrupted by its Product session",
            )
        return await self._require_handle(record.ref).interrupt()

    def list_agents(
        self,
        *,
        caller: ControlCaller,
    ) -> tuple[AgentRecord, ...]:
        return self.control.list_agents(caller=caller)

    async def close_agent(
        self,
        *,
        caller: ControlCaller,
        target: AgentPath,
    ) -> SessionTreeCloseResult:
        if target == AgentPath.root():
            raise MultiAgentError(
                "root_lifecycle_owned",
                "the root agent is closed by its Product session",
            )
        async with self._operation_lock:
            plan = self.control.plan_close_tree(caller=caller, target=target)
            return await self._close_plan(plan)

    async def close_owned_children(self) -> SessionTreeCloseResult:
        """Release every child before /new, /resume, or session disposal."""

        async with self._operation_lock:
            plan = tuple(
                record
                for record in self.control.plan_close_tree(
                    caller=HostCaller(),
                    target=AgentPath.root(),
                )
                if record.path != AgentPath.root()
            )
            result = await self._close_plan(plan)
            await self.drain_notice_deliveries()
            return result

    async def dispose(self) -> SessionTreeCloseResult:
        if self._closed:
            return SessionTreeCloseResult(())
        result = await self.close_owned_children()
        self._closed = True
        self._unsubscribe_notices()
        await self.drain_notice_deliveries()
        return result

    async def drain_notice_deliveries(self) -> None:
        while self._notice_tasks:
            tasks = tuple(self._notice_tasks)
            await asyncio.gather(
                *(asyncio.shield(task) for task in tasks),
                return_exceptions=True,
            )
            # A gather over already-finished tasks may return without yielding
            # long enough for their done callbacks to run. Remove the observed
            # snapshot directly so draining cannot spin on completed tasks.
            self._notice_tasks.difference_update(tasks)

    async def _close_plan(
        self,
        plan: tuple[AgentRecord, ...],
    ) -> SessionTreeCloseResult:
        closed: list[AgentRecord] = []
        errors: list[tuple[AgentRef, Exception]] = []
        for planned in plan:
            handle = self._handles.pop(planned.ref, None)
            self._inputs.pop(planned.ref, None)
            if handle is None:
                transition = self.control.commit_closed(planned.ref)
                if transition.record is not None:
                    closed.append(transition.record)
                continue
            result: HandleCloseResult = await handle.close()
            closed.append(result.record)
            if result.dispose_error is not None:
                errors.append((planned.ref, result.dispose_error))
        return SessionTreeCloseResult(tuple(closed), tuple(errors))

    def _on_notice(self, notice: AgentCompletionNotice) -> None:
        if self._closed or self._notice_wake_policy == "discard":
            return
        if notice.recipient_ref == self.control.root_ref:
            if self._root_input is not None:
                root_active = (
                    self._root_is_active is not None and self._root_is_active()
                )
                self._root_input.enqueue_notice(notice)
                if (
                    self._notice_wake_policy == "wake_if_idle"
                    and self._root_notice_wake is not None
                    and not root_active
                ):
                    result = self._root_notice_wake()
                    if inspect.isawaitable(result):
                        self._schedule_notice_operation(
                            result,
                            name=f"subagent:root:notice-{notice.notice_id}",
                        )
            return
        handle = self._handles.get(notice.recipient_ref)
        if handle is None:
            return
        message = completion_notice_to_message(notice)
        operation = (
            handle.deliver(message)
            if self._notice_wake_policy == "wake_if_idle"
            else handle.enqueue(message)
        )
        self._schedule_notice_operation(
            operation,
            name=f"subagent:{notice.recipient_ref}:notice-{notice.notice_id}",
        )

    def _schedule_notice_operation(
        self,
        operation: Awaitable[object],
        *,
        name: str,
    ) -> None:
        task = asyncio.create_task(
            operation,
            name=name,
        )
        self._notice_tasks.add(task)
        task.add_done_callback(self._notice_delivery_done)

    def _notice_delivery_done(
        self,
        task: asyncio.Task[object],
    ) -> None:
        self._notice_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _require_handle(self, ref: AgentRef) -> SubagentRunHandle:
        handle = self._handles.get(ref)
        if handle is None:
            raise MultiAgentError(
                "agent_endpoint_unavailable",
                f"agent has no live session handle: {ref}",
            )
        return handle

    def _require_open_runtime(self) -> None:
        if self._closed:
            raise RuntimeError("session multi-agent runtime is disposed")


def completion_notice_to_message(
    notice: AgentCompletionNotice,
    *,
    text: str | None = None,
) -> AgentInputMessage:
    references = tuple(
        value
        for value in (
            notice.workspace_ref,
            notice.change_set_ref,
            *notice.artifact_refs,
        )
        if value is not None
    )
    return AgentInputMessage(
        message_id=f"completion:{notice.notice_id}",
        sender=AgentCaller(notice.sender_ref),
        recipient_ref=notice.recipient_ref,
        kind="mailbox",
        text=text or standard_completion_notice_text(notice),
        references=references,
    )


def standard_completion_notice_text(notice: AgentCompletionNotice) -> str:
    headline = (
        f"{notice.sender_ref.path} {notice.terminal.status} (round {notice.round_id})."
    )
    detail = notice.summary or notice.terminal.final_message
    return f"{headline}\n{detail}" if detail else headline


BeforeReleaseHook = Callable[
    [SessionT, SessionT | None, object],
    Awaitable[None] | None,
]
RuntimeResolver = Callable[[SessionT], SessionMultiAgentRuntime | None]


def compose_multiagent_before_release(
    *,
    resolve_runtime: RuntimeResolver[SessionT],
    existing: BeforeReleaseHook[SessionT] | None = None,
) -> BeforeReleaseHook[SessionT]:
    """Chain child-tree release into the existing lifecycle hook seam."""

    async def before_release(
        session: SessionT,
        target_session: SessionT | None,
        transition: object,
    ) -> None:
        runtime = resolve_runtime(session)
        if runtime is not None:
            await runtime.dispose()
        if existing is not None:
            result = existing(session, target_session, transition)
            if result is not None:
                await result

    return before_release


__all__ = [
    "AgentInputActivity",
    "AgentInputFacade",
    "AgentInputWaitOutcome",
    "NoticeWakePolicy",
    "RootAgentInput",
    "SessionMultiAgentRuntime",
    "SessionSubagentDriver",
    "SessionSubagentFactory",
    "SessionSubagentRequest",
    "SessionTreeCloseResult",
    "completion_notice_to_message",
    "compose_multiagent_before_release",
    "standard_completion_notice_text",
]
