from __future__ import annotations

from dataclasses import dataclass, field


def _as_tuple_of_strings(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    return tuple(value)


@dataclass(frozen=True)
class PromptAssembly:
    system_prompt: str
    tool_prompt: str
    resource_fragments: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_fragments", _as_tuple_of_strings(self.resource_fragments, "resource_fragments"))
