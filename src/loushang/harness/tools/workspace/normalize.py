from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
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

from .authoring import _TOOL_SPEC_ATTR, DecoratedTool, DecoratedToolSpec
from .context import ToolContext, ToolContextProvider
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
class _DecoratedToolExecute:
    spec: DecoratedToolSpec
    context_provider: ToolContextProvider | None = None
    context_parameter_name: str | None = None

    def bind_context_provider(
        self, context_provider: ToolContextProvider | None
    ) -> _DecoratedToolExecute:
        return _DecoratedToolExecute(
            spec=self.spec,
            context_provider=context_provider,
            context_parameter_name=self.context_parameter_name,
        )

    async def __call__(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: object | None = None,
    ) -> AgentToolResult[Any]:
        del on_update

        call_params = dict(params)
        if self.context_parameter_name is not None:
            call_params[self.context_parameter_name] = self._build_context(
                tool_call_id=tool_call_id,
                signal=signal,
            )

        bound = signature(self.spec.fn).bind_partial(**call_params)
        result = self.spec.fn(*bound.args, **bound.kwargs)
        if inspect.isawaitable(result):
            result = await result
        return _normalize_plain_return_value(result)

    def _build_context(
        self, *, tool_call_id: str, signal: object | None
    ) -> ToolContext:
        if self.context_provider is None:
            return ToolContext(tool_call_id=tool_call_id, signal=signal)
        context = self.context_provider(tool_call_id=tool_call_id)
        if context.signal is signal:
            return context
        return replace(context, signal=signal)


def build_decorated_execute(
    spec: DecoratedToolSpec,
    *,
    context_provider: ToolContextProvider | None = None,
    context_parameter_name: str | None = None,
) -> _DecoratedToolExecute:
    return _DecoratedToolExecute(
        spec=spec,
        context_provider=context_provider,
        context_parameter_name=(
            context_parameter_name
            if context_parameter_name is not None
            else _resolve_context_parameter_name(spec.fn)
        ),
    )


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
    obj: ToolDefinition | DecoratedToolSpec | DecoratedTool | object,
) -> ToolDefinition:
    if isinstance(obj, ToolDefinition):
        return obj
    obj = _resolve_decorated_spec(obj)

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
        execute=build_decorated_execute(
            obj, context_parameter_name=context_parameter_name
        ),
        prompt_snippet=obj.prompt_snippet,
        prompt_guidelines=obj.prompt_guidelines,
    )
