from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loushang.ai.messages import normalize_messages
from loushang.ai.options import PairingMode
from loushang.ai.types import Context, Tool

NORMALIZED_CONTEXT_MARKER = "_loushang_normalized_context"


def normalize_context(
    context: Context | dict[str, Any] | None,
    *,
    model=None,
    pairing_mode: PairingMode = "repair",
) -> dict[str, Any]:
    if context is None:
        return _mark_normalized_context(
            {"system_prompt": None, "messages": [], "tools": None}
        )

    if isinstance(context, Context):
        tools = None if context.tools is None else list(context.tools)
        return _mark_normalized_context(
            {
                "system_prompt": context.system_prompt,
                "messages": normalize_messages(
                    list(context.messages),
                    tools=tools,
                    model=model,
                    pairing_mode=pairing_mode,
                ),
                "tools": tools,
            }
        )

    messages = list(context.get("messages", []))
    system_prompt = _coalesce_system_prompt(
        context.get("system_prompt"),
        context.get("systemPrompt"),
        _extract_system_prompt(messages),
    )
    tools = _normalize_tools(context.get("tools"))
    normalized_messages = normalize_messages(
        _strip_system_messages(messages),
        tools=tools,
        model=model,
        pairing_mode=pairing_mode,
    )

    normalized = dict(context)
    normalized["system_prompt"] = system_prompt
    normalized.pop("systemPrompt", None)
    normalized["messages"] = normalized_messages
    normalized["tools"] = tools
    return _mark_normalized_context(normalized)


def ensure_normalized_context(
    context: Context | dict[str, Any] | None,
    *,
    model=None,
    pairing_mode: PairingMode = "repair",
) -> dict[str, Any]:
    if is_normalized_context(context):
        assert isinstance(context, dict)
        return dict(context)
    return normalize_context(context, model=model, pairing_mode=pairing_mode)


def is_normalized_context(context: object) -> bool:
    if not isinstance(context, dict):
        return False
    return bool(context.get(NORMALIZED_CONTEXT_MARKER) is True)


def _mark_normalized_context(context: dict[str, Any]) -> dict[str, Any]:
    marked = dict(context)
    marked[NORMALIZED_CONTEXT_MARKER] = True
    return marked


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
    normalized: list[object] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") in {"system", "developer"}:
            continue
        normalized.append(message)
    return normalized


def _normalize_tools(tools: Any) -> list[Tool] | None:
    if tools is None:
        return None
    normalized: list[Tool] = []
    for tool in tools:
        if isinstance(tool, Tool):
            normalized.append(tool)
            continue
        if isinstance(tool, dict):
            normalized.append(
                Tool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {"type": "object"}),
                )
            )
            continue
        raise TypeError(f"Unsupported tool type: {type(tool)!r}")
    return normalized
