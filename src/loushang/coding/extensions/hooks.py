from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import Enum

from loushang.agent.types import (
    AfterToolCallResult,
    AgentToolResult,
    BeforeToolCallResult,
)
from loushang.ai.types import ToolCall
from loushang.coding.extensions.types import (
    ExtensionContext,
    LoadedExtension,
    ToolCallDecision,
    ToolResultDecision,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic


class HookKind(str, Enum):
    OBSERVE = "observe"
    TRANSFORM = "transform"
    INTERCEPT = "intercept"
    AUGMENT = "augment"


ContextFactory = Callable[[LoadedExtension], ExtensionContext]
RuntimeErrorHandler = Callable[[LoadedExtension, str, Exception], None]


class HookDispatcher:
    def __init__(
        self,
        extensions: Sequence[LoadedExtension],
        *,
        context_factory: ContextFactory,
        diagnostics: list[ResourceDiagnostic],
        runtime_error_handler: RuntimeErrorHandler | None = None,
    ) -> None:
        self._extensions = list(extensions)
        self._context_factory = context_factory
        self._diagnostics = diagnostics
        self._runtime_error_handler = runtime_error_handler

    async def before_tool_call(self, event, signal: object | None = None) -> BeforeToolCallResult | None:
        del signal
        current_event = event
        changed = False
        for extension in self._extensions:
            handlers = extension.hooks.get("tool_call", [])
            if not handlers:
                continue
            context = self._context_factory(extension)
            for handler in handlers:
                try:
                    decision = handler(current_event, context)
                    if inspect.isawaitable(decision):
                        decision = await decision
                except Exception as exc:
                    self._record_hook_error(
                        extension=extension,
                        event="tool_call",
                        code="extension_tool_call_failed",
                        message=f"Extension hook 'tool_call' failed: {exc}",
                        error=exc,
                    )
                    continue
                if decision is None:
                    continue
                if not isinstance(decision, ToolCallDecision):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_call_decision",
                            message="tool_call hooks must return ToolCallDecision or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if decision.diagnostics:
                    self._diagnostics.extend(decision.diagnostics)
                rewritten_tool_name = decision.tool_name or current_event.tool_call.name
                rewritten_arguments = decision.arguments if decision.arguments is not None else current_event.args
                if rewritten_tool_name != current_event.tool_call.name or rewritten_arguments != current_event.args:
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
                if decision.block:
                    return BeforeToolCallResult(
                        block=True,
                        reason=decision.reason,
                        tool_name=current_event.tool_call.name if changed else None,
                        arguments=current_event.args if changed else None,
                    )
        if not changed:
            return None
        return BeforeToolCallResult(
            tool_name=current_event.tool_call.name,
            arguments=current_event.args,
        )

    async def after_tool_call(self, event, signal: object | None = None) -> AfterToolCallResult | None:
        del signal
        current_event = event
        changed = False
        for extension in self._extensions:
            handlers = extension.hooks.get("tool_result", [])
            if not handlers:
                continue
            context = self._context_factory(extension)
            for handler in handlers:
                try:
                    decision = handler(current_event, context)
                    if inspect.isawaitable(decision):
                        decision = await decision
                except Exception as exc:
                    self._record_hook_error(
                        extension=extension,
                        event="tool_result",
                        code="extension_tool_result_failed",
                        message=f"Extension hook 'tool_result' failed: {exc}",
                        error=exc,
                    )
                    continue
                if decision is None:
                    continue
                if not isinstance(decision, ToolResultDecision):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_result_decision",
                            message="tool_result hooks must return ToolResultDecision or None.",
                            source_path=extension.source_path,
                        )
                    )
                    continue
                if decision.diagnostics:
                    self._diagnostics.extend(decision.diagnostics)
                if decision.result is None:
                    continue
                if not isinstance(decision.result, AgentToolResult):
                    self._diagnostics.append(
                        ResourceDiagnostic(
                            code="invalid_extension_tool_result_decision",
                            message=(
                                "tool_result decisions must return AgentToolResult instances when overriding results."
                            ),
                            source_path=extension.source_path,
                        )
                    )
                    continue
                changed = True
                current_event = replace(current_event, result=decision.result)
        if not changed:
            return None
        return AfterToolCallResult(
            content=current_event.result.content,
            details=current_event.result.details,
            terminate=current_event.result.terminate,
        )

    def _record_hook_error(
        self,
        *,
        extension: LoadedExtension,
        event: str,
        code: str,
        message: str,
        error: Exception,
    ) -> None:
        self._diagnostics.append(
            ResourceDiagnostic(
                code=code,
                message=message,
                source_path=extension.source_path,
            )
        )
        if self._runtime_error_handler is not None:
            self._runtime_error_handler(extension, event, error)


__all__ = [
    "HookDispatcher",
    "HookKind",
]
