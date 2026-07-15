from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, cast

from loushang.agent.types import (
    AfterToolCallContext,
    AfterToolCallResult,
    AgentToolResult,
    BeforeToolCallContext,
    BeforeToolCallResult,
)
from loushang.ai.types import ToolCall
from loushang.coding.extensions.types import (
    ExtensionContext,
    LoadedExtension,
    ToolCallDecision,
    ToolResultDecision,
)
from loushang.harness.extensions.routing import (
    ExtensionRoutePlan,
    ExtensionRouter,
    ResolvedExtensionRoute,
    RouteStep,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic


class HookKind(str, Enum):
    OBSERVE = "observe"
    TRANSFORM = "transform"
    INTERCEPT = "intercept"
    AUGMENT = "augment"


ContextFactory = Callable[[LoadedExtension], ExtensionContext]
RuntimeErrorHandler = Callable[[LoadedExtension, str, Exception], None]


@dataclass(frozen=True)
class _BeforeToolState:
    event: BeforeToolCallContext
    changed: bool = False
    result: BeforeToolCallResult | None = None


@dataclass(frozen=True)
class _AfterToolState:
    event: AfterToolCallContext
    changed: bool = False


class HookDispatcher:
    def __init__(
        self,
        extensions: Sequence[LoadedExtension],
        *,
        context_factory: ContextFactory,
        diagnostics: list[ResourceDiagnostic],
        runtime_error_handler: RuntimeErrorHandler | None = None,
        route_plan: ExtensionRoutePlan | None = None,
    ) -> None:
        self._context_factory = context_factory
        self._diagnostics = diagnostics
        plan = route_plan or ExtensionRoutePlan.from_extensions(
            extensions, diagnostics=diagnostics
        )
        self._router = ExtensionRouter(
            plan,
            diagnostics=diagnostics,
            runtime_error_handler=runtime_error_handler,
            include_route_id_in_error_metadata=False,
            include_provenance_in_error_metadata=False,
        )

    async def before_tool_call(
        self,
        event: BeforeToolCallContext,
        signal: object | None = None,
    ) -> BeforeToolCallResult | None:
        del signal

        def reducer(
            state: _BeforeToolState,
            decision: object,
            route: ResolvedExtensionRoute,
        ) -> RouteStep[_BeforeToolState]:
            if not isinstance(decision, ToolCallDecision):
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_tool_call_decision",
                        message="tool_call hooks must return ToolCallDecision or None.",
                        source_path=route.extension.source_path,
                    )
                )
                return RouteStep(state)
            if decision.diagnostics:
                self._diagnostics.extend(decision.diagnostics)
            current_event = state.event
            rewritten_tool_name = decision.tool_name or current_event.tool_call.name
            rewritten_arguments = cast(
                dict[str, Any],
                decision.arguments
                if decision.arguments is not None
                else current_event.args,
            )
            changed = state.changed
            if (
                rewritten_tool_name != current_event.tool_call.name
                or rewritten_arguments != current_event.args
            ):
                changed = True
                current_event = replace(
                    current_event,
                    tool_call=ToolCall(
                        type="toolCall",
                        id=current_event.tool_call.id,
                        name=rewritten_tool_name,
                        arguments=rewritten_arguments,
                        thought_signature=current_event.tool_call.thought_signature,
                    ),
                    args=rewritten_arguments,
                )
            result = None
            if decision.block:
                result = BeforeToolCallResult(
                    block=True,
                    reason=decision.reason,
                    tool_name=current_event.tool_call.name if changed else None,
                    arguments=(
                        cast(dict[str, Any], current_event.args) if changed else None
                    ),
                )
            return RouteStep(
                _BeforeToolState(
                    event=current_event,
                    changed=changed,
                    result=result,
                ),
                stop=result is not None,
            )

        outcome = await self._router.intercept(
            "tool_call",
            _BeforeToolState(event=event),
            event_factory=lambda state, route: state.event,
            reducer=reducer,
            context_factory=self._context_factory,
        )
        state = outcome.state
        if state.result is not None:
            return state.result
        if not state.changed:
            return None
        return BeforeToolCallResult(
            tool_name=state.event.tool_call.name,
            arguments=cast(dict[str, Any], state.event.args),
        )

    async def after_tool_call(
        self,
        event: AfterToolCallContext,
        signal: object | None = None,
    ) -> AfterToolCallResult | None:
        del signal

        def reducer(
            state: _AfterToolState,
            decision: object,
            route: ResolvedExtensionRoute,
        ) -> RouteStep[_AfterToolState]:
            if not isinstance(decision, ToolResultDecision):
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_tool_result_decision",
                        message="tool_result hooks must return ToolResultDecision or None.",
                        source_path=route.extension.source_path,
                    )
                )
                return RouteStep(state)
            if decision.diagnostics:
                self._diagnostics.extend(decision.diagnostics)
            if decision.result is None:
                return RouteStep(state)
            if not isinstance(decision.result, AgentToolResult):
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_tool_result_decision",
                        message=(
                            "tool_result decisions must return AgentToolResult "
                            "instances when overriding results."
                        ),
                        source_path=route.extension.source_path,
                    )
                )
                return RouteStep(state)
            return RouteStep(
                _AfterToolState(
                    event=replace(
                        state.event,
                        result=decision.result,
                        hook_details=decision.result.hook_details(),
                    ),
                    changed=True,
                )
            )

        outcome = await self._router.reduce(
            "tool_result",
            _AfterToolState(event=event),
            event_factory=lambda state, route: state.event,
            reducer=reducer,
            context_factory=self._context_factory,
        )
        state = outcome.state
        if not state.changed:
            return None
        return AfterToolCallResult(
            content=state.event.result.content,
            details=state.event.result.details,
            terminate=state.event.result.terminate,
            projector=state.event.result.projector,
        )


__all__ = [
    "HookDispatcher",
    "HookKind",
]
