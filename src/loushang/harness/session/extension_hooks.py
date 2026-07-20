"""Composition of Agent hooks contributed by a Product extension runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from loushang.agent import AbortSignal
from loushang.agent.tool_output import STRICT_JSON_TOOL_OUTPUT_PROJECTOR
from loushang.agent.types import AfterToolCallResult, BeforeToolCallResult
from loushang.ai.types import ToolCall

CwdProvider = Callable[[], str]
BeforeToolCallHook = Callable[
    [Any, AbortSignal], Awaitable[BeforeToolCallResult | None]
]
AfterToolCallHook = Callable[[Any, AbortSignal], Awaitable[AfterToolCallResult | None]]
ContextTransformHook = Callable[[list[object], AbortSignal], Awaitable[list[object]]]


class ExtensionAgentHookPort(Protocol):
    """Extension callbacks that can participate in an Agent loop."""

    async def emit_context(
        self,
        messages: list[object],
        signal: AbortSignal,
        *,
        cwd: str = "",
    ) -> list[object]: ...

    async def before_tool_call(
        self,
        context: object,
        signal: AbortSignal,
    ) -> BeforeToolCallResult | None: ...

    async def after_tool_call(
        self,
        context: object,
        signal: AbortSignal,
    ) -> AfterToolCallResult | None: ...


class ExtensionHookAgentPort(Protocol):
    """Mutable Agent hook slots used by the extension hook runtime."""

    transform_context: ContextTransformHook | None
    before_tool_call: BeforeToolCallHook | None
    after_tool_call: AfterToolCallHook | None


@dataclass
class ExtensionAgentHookRuntime:
    """Install extension context and tool hooks without Product imports."""

    agent: ExtensionHookAgentPort
    extension_runtime: ExtensionAgentHookPort
    get_cwd: CwdProvider

    def install(self) -> None:
        existing_transform = self.agent.transform_context
        existing_before = self.agent.before_tool_call
        existing_after = self.agent.after_tool_call

        async def _transform_context(messages, signal):
            current_messages = messages
            if existing_transform is not None:
                current_messages = await existing_transform(current_messages, signal)
            return await self.extension_runtime.emit_context(
                current_messages,
                signal,
                cwd=self.get_cwd(),
            )

        async def _before_tool_call(context, signal):
            return await compose_before_tool_call_hooks(
                context,
                signal,
                [
                    hook
                    for hook in (
                        existing_before,
                        self.extension_runtime.before_tool_call,
                    )
                    if hook is not None
                ],
            )

        async def _after_tool_call(context, signal):
            return await compose_after_tool_call_hooks(
                context,
                signal,
                [
                    hook
                    for hook in (
                        existing_after,
                        self.extension_runtime.after_tool_call,
                    )
                    if hook is not None
                ],
            )

        self.agent.transform_context = _transform_context
        self.agent.before_tool_call = _before_tool_call
        self.agent.after_tool_call = _after_tool_call


async def compose_before_tool_call_hooks(
    context: Any,
    signal: AbortSignal,
    hooks: Sequence[BeforeToolCallHook],
) -> BeforeToolCallResult | None:
    """Run before hooks in order while preserving prior modifications."""

    current_context = context
    changed = False

    for hook in hooks:
        result = await hook(current_context, signal)
        if result is None:
            continue
        if result.tool_name is not None or result.arguments is not None:
            changed = True
            current_context = _apply_before_tool_call_result(current_context, result)
        if result.block:
            return BeforeToolCallResult(
                block=True,
                reason=result.reason,
                tool_name=current_context.tool_call.name if changed else None,
                arguments=current_context.args if changed else None,
            )

    if not changed:
        return None
    return BeforeToolCallResult(
        tool_name=current_context.tool_call.name,
        arguments=current_context.args,
    )


def _apply_before_tool_call_result(context: Any, result: BeforeToolCallResult):
    tool_name = result.tool_name or context.tool_call.name
    arguments = result.arguments if result.arguments is not None else context.args
    return replace(
        context,
        tool_call=ToolCall(
            type="toolCall",
            id=context.tool_call.id,
            name=tool_name,
            arguments=arguments,
            thought_signature=context.tool_call.thought_signature,
        ),
        args=arguments,
    )


async def compose_after_tool_call_hooks(
    context: Any,
    signal: AbortSignal,
    hooks: Sequence[AfterToolCallHook],
) -> AfterToolCallResult | None:
    """Run after hooks in order while preserving result projection semantics."""

    current_context = context
    changed = False

    for hook in hooks:
        result = await hook(current_context, signal)
        if result is None:
            continue
        next_result = current_context.result
        details_provided = result.details_provided
        projection_changed = details_provided or result.projector is not None
        if (
            result.content is not None
            or details_provided
            or result.terminate is not None
            or result.projector is not None
        ):
            changed = True
            next_result = replace(
                current_context.result,
                content=result.content
                if result.content is not None
                else current_context.result.content,
                details=result.details
                if details_provided
                else current_context.result.details,
                terminate=result.terminate
                if result.terminate is not None
                else current_context.result.terminate,
                projector=(
                    result.projector
                    if result.projector is not None
                    else (
                        current_context.result.projector
                        if not details_provided
                        else STRICT_JSON_TOOL_OUTPUT_PROJECTOR
                    )
                ),
            )
        next_is_error = (
            result.is_error if result.is_error is not None else current_context.is_error
        )
        if next_is_error != current_context.is_error:
            changed = True
        current_context = replace(
            current_context,
            result=next_result,
            is_error=next_is_error,
            hook_details=(
                next_result.hook_details()
                if projection_changed
                else current_context.hook_details
            ),
        )

    if not changed:
        return None
    return AfterToolCallResult(
        content=current_context.result.content,
        details=current_context.result.details,
        is_error=current_context.is_error,
        terminate=current_context.result.terminate,
        projector=current_context.result.projector,
    )


__all__ = [
    "ExtensionAgentHookRuntime",
    "ExtensionAgentHookPort",
    "compose_after_tool_call_hooks",
    "compose_before_tool_call_hooks",
]
