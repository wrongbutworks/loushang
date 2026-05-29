from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

from loushang.agent.types import AgentToolResult, ToolExecutionMode


class PiTruncationDetails(TypedDict, total=False):
    content: str
    truncated: bool
    truncatedBy: NotRequired[Literal["lines", "bytes"] | None]
    totalLines: int
    outputLines: int
    maxLines: int
    totalBytes: int
    outputBytes: int
    maxBytes: int
    firstLineExceedsLimit: bool
    lastLinePartial: bool


def _as_tuple_of_strings(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must be a sequence of strings")
        normalized.append(item)
    return tuple(normalized)


def _validate_execution_mode(value: ToolExecutionMode, field_name: str) -> ToolExecutionMode:
    if value not in {"sequential", "parallel"}:
        raise ValueError(f"{field_name} must be 'sequential' or 'parallel'")
    return value


def _noop_invalidate() -> None:
    return None


@dataclass(frozen=True)
class ToolRenderResultOptions:
    expanded: bool = False
    is_partial: bool = False

    @property
    def isPartial(self) -> bool:
        return self.is_partial


@dataclass(frozen=True)
class ToolRenderContext:
    args: object | None = None
    tool_call_id: str = ""
    invalidate: Callable[[], None] = _noop_invalidate
    last_rendered: object | None = None
    state: dict[str, Any] = field(default_factory=dict)
    cwd: str = ""
    execution_started: bool = True
    args_complete: bool = True
    is_partial: bool = False
    expanded: bool = False
    show_images: bool = False
    is_error: bool = False

    @property
    def toolCallId(self) -> str:
        return self.tool_call_id

    @property
    def lastComponent(self) -> object | None:
        return self.last_rendered

    @property
    def executionStarted(self) -> bool:
        return self.execution_started

    @property
    def argsComplete(self) -> bool:
        return self.args_complete

    @property
    def isPartial(self) -> bool:
        return self.is_partial

    @property
    def showImages(self) -> bool:
        return self.show_images

    @property
    def isError(self) -> bool:
        return self.is_error


ToolRenderOutput = str | Mapping[str, Any] | None
ToolRenderCall = Callable[[object, Mapping[str, str], ToolRenderContext], ToolRenderOutput]
ToolRenderResult = Callable[[AgentToolResult[Any], ToolRenderResultOptions, Mapping[str, str], ToolRenderContext], ToolRenderOutput]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[
        [str, dict[str, Any], object | None, object | None],
        Awaitable[AgentToolResult[Any]],
    ]
    prepare_arguments: Callable[[object], dict[str, Any]] | None = None
    execution_mode: ToolExecutionMode = "parallel"
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] = field(default_factory=tuple)
    render_call: ToolRenderCall | None = None
    render_result: ToolRenderResult | None = None
    provider_parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prompt_guidelines",
            _as_tuple_of_strings(self.prompt_guidelines, "prompt_guidelines"),
        )
        object.__setattr__(
            self,
            "execution_mode",
            _validate_execution_mode(self.execution_mode, "execution_mode"),
        )
        if self.render_call is not None and not callable(self.render_call):
            raise TypeError("render_call must be callable")
        if self.render_result is not None and not callable(self.render_result):
            raise TypeError("render_result must be callable")
        if self.provider_parameters is not None and not isinstance(self.provider_parameters, dict):
            raise TypeError("provider_parameters must be a dict")

    @property
    def renderCall(self) -> ToolRenderCall | None:
        return self.render_call

    @property
    def renderResult(self) -> ToolRenderResult | None:
        return self.render_result
