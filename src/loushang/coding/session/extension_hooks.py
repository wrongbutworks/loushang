from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace

from loushang.agent import Agent
from loushang.agent.types import AfterToolCallResult, BeforeToolCallResult
from loushang.ai.types import ToolCall
from loushang.coding.extensions import ExtensionRunner


CwdProvider = Callable[[], str]


@dataclass
class ExtensionHooks:
    agent: Agent
    extension_runner: ExtensionRunner
    get_cwd: CwdProvider

    def install(self) -> None:
        existing_transform = self.agent.transform_context
        existing_before = self.agent.before_tool_call
        existing_after = self.agent.after_tool_call
        existing_on_payload = self.agent.on_payload
        existing_on_response = getattr(self.agent, "on_response", None)

        async def _transform_context(messages, signal):
            current_messages = messages
            if existing_transform is not None:
                current_messages = await existing_transform(current_messages, signal)
            return await self.extension_runner.emit_context(
                current_messages,
                signal,
                cwd=self.get_cwd(),
            )

        async def _before_tool_call(context, signal):
            return await compose_before_tool_call_hooks(
                context,
                signal,
                [hook for hook in (existing_before, self.extension_runner.before_tool_call) if hook is not None],
            )

        async def _after_tool_call(context, signal):
            return await compose_after_tool_call_hooks(
                context,
                signal,
                [hook for hook in (existing_after, self.extension_runner.after_tool_call) if hook is not None],
            )

        async def _on_payload(payload, model):
            current_payload = payload
            if callable(existing_on_payload):
                next_payload = existing_on_payload(current_payload, model)
                if inspect.isawaitable(next_payload):
                    next_payload = await next_payload
                if next_payload is not None:
                    current_payload = next_payload
            if self.extension_runner.has_handlers("before_provider_request"):
                current_payload = await self.extension_runner.emit_before_provider_request(
                    current_payload,
                    cwd=self.get_cwd(),
                )
            return current_payload

        async def _on_response(response, model):
            if callable(existing_on_response):
                result = existing_on_response(response, model)
                if inspect.isawaitable(result):
                    await result
            if self.extension_runner.has_handlers("after_provider_response"):
                await self.extension_runner.emit_after_provider_response(
                    response,
                    cwd=self.get_cwd(),
                )

        self.agent.transform_context = _transform_context
        self.agent.before_tool_call = _before_tool_call
        self.agent.after_tool_call = _after_tool_call
        self.agent.on_payload = _on_payload
        self.agent.on_response = _on_response


async def compose_before_tool_call_hooks(context, signal, hooks):
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


def _apply_before_tool_call_result(context, result: BeforeToolCallResult):
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


async def compose_after_tool_call_hooks(context, signal, hooks):
    current_context = context
    changed = False

    for hook in hooks:
        result = await hook(current_context, signal)
        if result is None:
            continue
        next_result = current_context.result
        if result.content is not None or result.details is not None or result.terminate is not None:
            changed = True
            next_result = replace(
                current_context.result,
                content=result.content if result.content is not None else current_context.result.content,
                details=result.details if result.details is not None else current_context.result.details,
                terminate=result.terminate if result.terminate is not None else current_context.result.terminate,
            )
        next_is_error = result.is_error if result.is_error is not None else current_context.is_error
        if next_is_error != current_context.is_error:
            changed = True
        current_context = replace(
            current_context,
            result=next_result,
            is_error=next_is_error,
        )

    if not changed:
        return None
    return AfterToolCallResult(
        content=current_context.result.content,
        details=current_context.result.details,
        is_error=current_context.is_error,
        terminate=current_context.result.terminate,
    )
