from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


_TOOL_SPEC_ATTR = "__loushang_tool_spec__"


@dataclass(frozen=True)
class DecoratedToolSpec:
    fn: Callable[..., object]
    name: str | None = None
    description: str | None = None
    label: str | None = None
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] | list[str] = ()
    schema_overrides: dict[str, object] | None = None

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.fn(*args, **kwargs)


@runtime_checkable
class DecoratedTool(Protocol):
    __loushang_tool_spec__: DecoratedToolSpec


def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    label: str | None = None,
    prompt_snippet: str | None = None,
    prompt_guidelines: tuple[str, ...] | list[str] = (),
    schema_overrides: dict[str, object] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = DecoratedToolSpec(
            fn=fn,
            name=name,
            description=description,
            label=label,
            prompt_snippet=prompt_snippet,
            prompt_guidelines=prompt_guidelines,
            schema_overrides=schema_overrides,
        )
        setattr(fn, _TOOL_SPEC_ATTR, spec)
        return fn

    return decorator
