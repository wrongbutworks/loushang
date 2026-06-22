from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType
from typing import Any

from loushang.ai.diagnostics import NormalizationDiagnostic
from loushang.ai.messages import normalize_messages_result
from loushang.ai.options import PairingMode
from loushang.ai.types import (
    AssistantMessage,
    Context,
    Tool,
    ToolResultMessage,
    UserMessage,
)

NORMALIZED_CONTEXT_MARKER = "_loushang_normalized_context"
_NORMALIZED_CONTEXT_KEYS = frozenset(
    {"system_prompt", "systemPrompt", "messages", "tools", NORMALIZED_CONTEXT_MARKER}
)
NormalizationKey = tuple[str | None, str | None, str | None, str | None, PairingMode]


class _FrozenList(list[Any]):
    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("NormalizedContext values are immutable")

    def __deepcopy__(self, memo: dict[int, object]) -> "_FrozenList":
        return self

    __setitem__ = _immutable  # type: ignore[assignment]
    __delitem__ = _immutable  # type: ignore[assignment]
    __iadd__ = _immutable  # type: ignore[assignment]
    __imul__ = _immutable  # type: ignore[assignment]
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


class _FrozenDict(dict[str, Any]):
    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("NormalizedContext values are immutable")

    def __deepcopy__(self, memo: dict[int, object]) -> "_FrozenDict":
        return self

    __setitem__ = _immutable  # type: ignore[assignment]
    __delitem__ = _immutable  # type: ignore[assignment]
    __ior__ = _immutable  # type: ignore[assignment]
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable


@dataclass(frozen=True, eq=False)
class NormalizedContext(Mapping[str, Any]):
    system_prompt: str | None
    messages: tuple[object, ...] = ()
    tools: tuple[Tool, ...] | None = None
    extras: Mapping[str, Any] = field(default_factory=dict, repr=False)
    normalization_key: NormalizationKey | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "messages",
            tuple(_snapshot_value(message) for message in self.messages),
        )
        if self.tools is not None:
            object.__setattr__(
                self,
                "tools",
                tuple(_snapshot_value(tool) for tool in self.tools),
            )
        extras = {
            key: _snapshot_value(value)
            for key, value in self.extras.items()
            if key not in _NORMALIZED_CONTEXT_KEYS
        }
        object.__setattr__(self, "extras", MappingProxyType(extras))

    def __getitem__(self, key: str) -> Any:
        if key == "system_prompt":
            return self.system_prompt
        if key == "messages":
            return self.messages
        if key == "tools":
            return self.tools
        return self.extras[key]

    def __iter__(self) -> Iterator[str]:
        yield "system_prompt"
        yield "messages"
        yield "tools"
        yield from self.extras

    def __len__(self) -> int:
        return 3 + len(self.extras)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())

    __hash__ = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.items())


@dataclass(frozen=True)
class NormalizationResult:
    context: NormalizedContext
    diagnostics: tuple[NormalizationDiagnostic, ...] = ()


def normalize_context(
    context: Context | Mapping[str, Any] | NormalizedContext | None,
    *,
    model=None,
    pairing_mode: PairingMode = "strict",
) -> NormalizedContext:
    return normalize_context_result(
        context,
        model=model,
        pairing_mode=pairing_mode,
    ).context


def normalize_context_result(
    context: Context | Mapping[str, Any] | NormalizedContext | None,
    *,
    model=None,
    pairing_mode: PairingMode = "strict",
) -> NormalizationResult:
    normalization_key = _normalization_key(model, pairing_mode)
    if isinstance(context, NormalizedContext):
        if (
            context.normalization_key is not None
            and _normalization_key_matches(context.normalization_key, normalization_key)
        ):
            return NormalizationResult(context=context)
        if (
            context.normalization_key is not None
            and context.normalization_key[4] != pairing_mode
        ):
            raise ValueError(
                "Cannot re-normalize an already normalized context with a different "
                "pairing_mode. Pass the original Context or dict instead."
            )

    if context is None:
        return NormalizationResult(
            context=NormalizedContext(
                system_prompt=None,
                messages=(),
                tools=None,
                normalization_key=normalization_key,
            )
        )

    if isinstance(context, Context):
        tools = _normalize_tools(context.tools)
        message_result = normalize_messages_result(
            list(context.messages),
            tools=None if tools is None else list(tools),
            model=model,
            pairing_mode=pairing_mode,
        )
        return NormalizationResult(
            context=NormalizedContext(
                system_prompt=context.system_prompt,
                messages=tuple(
                    _validate_normalized_messages(message_result.messages)
                ),
                tools=tools,
                normalization_key=normalization_key,
            ),
            diagnostics=message_result.diagnostics,
        )

    messages = list(context.get("messages", ()))
    system_prompt = _coalesce_system_prompt(
        _optional_system_prompt(context.get("system_prompt"), "system_prompt"),
        _optional_system_prompt(context.get("systemPrompt"), "systemPrompt"),
        _extract_system_prompt(messages),
    )
    tools = _normalize_tools(context.get("tools"))
    stripped_messages, message_paths = _strip_system_messages_with_paths(messages)
    message_result = normalize_messages_result(
        stripped_messages,
        tools=None if tools is None else list(tools),
        model=model,
        pairing_mode=pairing_mode,
        message_paths=message_paths,
    )
    normalized_messages = _validate_normalized_messages(message_result.messages)
    extras = {
        key: value
        for key, value in context.items()
        if key not in _NORMALIZED_CONTEXT_KEYS
    }
    return NormalizationResult(
        context=NormalizedContext(
            system_prompt=system_prompt,
            messages=tuple(normalized_messages),
            tools=tools,
            extras=extras,
            normalization_key=normalization_key,
        ),
        diagnostics=message_result.diagnostics,
    )


def ensure_normalized_context(
    context: Context | Mapping[str, Any] | NormalizedContext | None,
    *,
    model=None,
    pairing_mode: PairingMode = "strict",
) -> NormalizedContext:
    return normalize_context(context, model=model, pairing_mode=pairing_mode)


def is_normalized_context(context: object) -> bool:
    return isinstance(context, NormalizedContext)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _optional_system_prompt(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError(f"Unsupported {field_name} type: {type(value)!r}")


def _snapshot_value(value: Any) -> Any:
    try:
        value = deepcopy(value)
    except Exception as exc:
        raise TypeError(
            f"NormalizedContext value could not be snapshotted: {type(value)!r}"
        ) from exc
    return _freeze_value(value)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict(
            {key: _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return _FrozenList(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            object.__setattr__(
                value,
                item.name,
                _freeze_value(getattr(value, item.name)),
            )
        return value
    return value


def _normalization_key(model: object, pairing_mode: PairingMode) -> NormalizationKey:
    if model is None:
        return (None, None, None, None, pairing_mode)
    return (
        _optional_str(getattr(model, "api", None)),
        _optional_str(getattr(model, "provider_id", None)),
        _optional_str(getattr(model, "endpoint_id", None)),
        _optional_str(getattr(model, "id", None)),
        pairing_mode,
    )


def _normalization_key_matches(
    existing: NormalizationKey,
    requested: NormalizationKey,
) -> bool:
    if existing[4] != requested[4]:
        return False
    for existing_part, requested_part in zip(existing[:4], requested[:4], strict=True):
        if requested_part is not None and existing_part != requested_part:
            return False
    return True


def _coalesce_system_prompt(*parts: str | None) -> str | None:
    resolved = [part for part in parts if part]
    if not resolved:
        return None
    return "\n".join(resolved)


def _extract_system_prompt(messages: Iterable[object]) -> str | None:
    parts: list[str] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") in {"system", "developer"}:
            content = message.get("content")
            if isinstance(content, str) and content:
                parts.append(content)
    if not parts:
        return None
    return "\n".join(parts)


def _strip_system_messages(messages: Iterable[object]) -> list[object]:
    stripped, _paths = _strip_system_messages_with_paths(messages)
    return stripped


def _strip_system_messages_with_paths(
    messages: Iterable[object],
) -> tuple[list[object], list[str]]:
    normalized: list[object] = []
    paths: list[str] = []
    for index, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") in {"system", "developer"}:
            continue
        normalized.append(message)
        paths.append(f"messages[{index}]")
    return normalized, paths


def _validate_normalized_messages(messages: list[object]) -> list[object]:
    for message in messages:
        if isinstance(message, (AssistantMessage, ToolResultMessage, UserMessage)):
            continue
        if isinstance(message, Mapping):
            continue
        raise TypeError(
            f"Unsupported message type after normalization: {type(message)!r}"
        )
    return messages


def _normalize_tools(tools: Any) -> tuple[Tool, ...] | None:
    if tools is None:
        return None
    normalized: list[Tool] = []
    for tool in tools:
        if isinstance(tool, Tool):
            normalized.append(
                Tool(
                    name=_normalize_tool_name(tool.name),
                    description=tool.description,
                    parameters=_normalize_tool_parameters(tool.parameters),
                )
            )
            continue
        if isinstance(tool, dict):
            normalized.append(
                Tool(
                    name=_normalize_tool_name(tool.get("name")),
                    description=tool.get("description", ""),
                    parameters=_normalize_tool_parameters(
                        tool.get("parameters", {"type": "object"})
                    ),
                )
            )
            continue
        raise TypeError(f"Unsupported tool type: {type(tool)!r}")
    return tuple(normalized)


def _normalize_tool_name(name: object) -> str:
    if isinstance(name, str) and name:
        return name
    raise TypeError(f"Unsupported tool name type: {type(name)!r}")


def _normalize_tool_parameters(parameters: object) -> dict[str, Any]:
    if isinstance(parameters, dict):
        return parameters
    raise TypeError(f"Unsupported tool parameters type: {type(parameters)!r}")
