from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from inspect import signature
from typing import (
    Annotated,
    Any,
    NotRequired,
    Required,
    get_args,
    get_origin,
    get_type_hints,
)

from loushang.agent.types import AgentToolResult, TextPart
from loushang.ai.types import ToolCall
from loushang.harness.tools.execution import (
    AuthorizedExecution,
    AuthorizedToolAction,
    AuthorizedToolContext,
    DirectExecution,
    DirectToolContext,
    ToolActionAdapter,
)

from .authoring import _TOOL_SPEC_ATTR, DecoratedTool, DecoratedToolSpec
from .context import ToolContext
from .schema import apply_schema_overrides, infer_schema_from_signature
from .types import ToolDefinition


def _titleize_tool_name(name: str) -> str:
    return name.replace("_", " ").title()


def _unwrap_annotation(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(get_args(annotation)[0])
    if origin in (Required, NotRequired):
        return _unwrap_annotation(get_args(annotation)[0])
    return annotation


def _resolve_context_parameter_name(fn: Callable[..., object]) -> str | None:
    hints = get_type_hints(fn, include_extras=True)
    context_parameter_name: str | None = None
    for parameter_name in signature(fn).parameters:
        annotation = hints.get(parameter_name)
        if annotation is None:
            continue
        if _unwrap_annotation(annotation) is ToolContext:
            if context_parameter_name is not None:
                raise TypeError(
                    "tool functions may declare at most one ToolContext parameter"
                )
            context_parameter_name = parameter_name
    return context_parameter_name


def _normalize_plain_return_value(value: object) -> AgentToolResult[Any]:
    if value is None:
        return AgentToolResult(content=[], details={})
    if isinstance(value, AgentToolResult):
        return value
    if isinstance(value, str):
        return AgentToolResult(
            content=[TextPart(type="text", text=value)], details=value
        )
    if isinstance(value, (dict, list, int, float, bool)):
        text = json.dumps(value, ensure_ascii=False)
        return AgentToolResult(
            content=[TextPart(type="text", text=text)], details=value
        )
    raise TypeError(
        f"unsupported plain return type for decorated tool: {type(value).__name__}"
    )


@dataclass(frozen=True)
class _DecoratedDirectHandler:
    spec: DecoratedToolSpec
    context_parameter_name: str | None = None

    async def __call__(
        self,
        call: ToolCall,
        context: DirectToolContext,
    ) -> AgentToolResult[Any]:
        tool_context = ToolContext(
            tool_call_id=context.tool_call_id,
            cwd=context.cwd,
            diagnostics=context.diagnostics,
            signal=context.signal,
            model=context.model,
        )
        return await _invoke_decorated_tool(
            self.spec,
            call.arguments,
            context_parameter_name=self.context_parameter_name,
            context=tool_context,
        )


@dataclass(frozen=True)
class _DecoratedAuthorizedHandler:
    spec: DecoratedToolSpec
    context_parameter_name: str | None = None

    async def __call__(
        self,
        action: AuthorizedToolAction,
        context: AuthorizedToolContext,
    ) -> AgentToolResult[Any]:
        tool_context = ToolContext(
            tool_call_id=context.tool_call_id,
            cwd=context.cwd,
            diagnostics=context.diagnostics,
            signal=context.signal,
            model=context.model,
            event_sink=context.event_sink,
            exec_service=context.exec_service,
        )
        return await _invoke_decorated_tool(
            self.spec,
            action.execution_arguments,
            context_parameter_name=self.context_parameter_name,
            context=tool_context,
        )


async def _invoke_decorated_tool(
    spec: DecoratedToolSpec,
    params: Mapping[str, Any],
    *,
    context_parameter_name: str | None,
    context: ToolContext,
) -> AgentToolResult[Any]:
    call_params = {
        str(name): _thaw_execution_value(value)
        for name, value in params.items()
    }
    if context_parameter_name is not None:
        call_params[context_parameter_name] = context
    bound = signature(spec.fn).bind_partial(**call_params)
    result = spec.fn(*bound.args, **bound.kwargs)
    if inspect.isawaitable(result):
        result = await result
    return _normalize_plain_return_value(result)


def _thaw_execution_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(name): _thaw_execution_value(item)
            for name, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_execution_value(item) for item in value]
    return value


def _resolve_decorated_spec(obj: object) -> DecoratedToolSpec:
    if isinstance(obj, DecoratedToolSpec):
        return obj

    if isinstance(obj, DecoratedTool):
        return obj.__loushang_tool_spec__

    spec = getattr(obj, _TOOL_SPEC_ATTR, None)
    if isinstance(spec, DecoratedToolSpec):
        return spec

    raise TypeError("tool_to_definition expects a ToolDefinition or decorated tool")


def tool_to_definition(
    obj: ToolDefinition,
) -> ToolDefinition:
    if isinstance(obj, ToolDefinition):
        return obj
    raise TypeError(
        "decorated tools require an explicit direct_tool(...) or "
        "authorized_tool(...) binding"
    )


def direct_tool(
    obj: DecoratedToolSpec | DecoratedTool | object,
) -> ToolDefinition:
    spec = _resolve_decorated_spec(obj)
    context_parameter_name = _resolve_context_parameter_name(spec.fn)
    return _build_decorated_definition(
        spec,
        execution=DirectExecution(
            _DecoratedDirectHandler(
                spec,
                context_parameter_name=context_parameter_name,
            )
        ),
        context_parameter_name=context_parameter_name,
    )


def authorized_tool(
    obj: DecoratedToolSpec | DecoratedTool | object,
    *,
    action: ToolActionAdapter,
) -> ToolDefinition:
    spec = _resolve_decorated_spec(obj)
    context_parameter_name = _resolve_context_parameter_name(spec.fn)
    return _build_decorated_definition(
        spec,
        execution=AuthorizedExecution(
            action_adapter=action,
            handler=_DecoratedAuthorizedHandler(
                spec,
                context_parameter_name=context_parameter_name,
            ),
        ),
        context_parameter_name=context_parameter_name,
    )


def _build_decorated_definition(
    obj: DecoratedToolSpec,
    *,
    execution: DirectExecution | AuthorizedExecution,
    context_parameter_name: str | None,
) -> ToolDefinition:

    name = obj.name if obj.name is not None else obj.fn.__name__
    description = (
        obj.description
        if obj.description is not None
        else (obj.fn.__doc__.strip() if obj.fn.__doc__ else "")
    )
    label = obj.label if obj.label is not None else _titleize_tool_name(name)
    context_parameter_name = _resolve_context_parameter_name(obj.fn)
    parameters = apply_schema_overrides(
        infer_schema_from_signature(
            obj.fn,
            exclude_names={context_parameter_name} if context_parameter_name else None,
        ),
        obj.schema_overrides,
    )
    return ToolDefinition(
        name=name,
        label=label,
        description=description,
        parameters=parameters,
        execution=execution,
        prompt_snippet=obj.prompt_snippet,
        prompt_guidelines=obj.prompt_guidelines,
    )
