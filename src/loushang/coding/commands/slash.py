from __future__ import annotations

from dataclasses import dataclass

from loushang.coding.commands.types import SessionCommandDescriptor


@dataclass(frozen=True)
class ParsedSlashCommand:
    name: str
    args: str
    is_mcp: bool = False


def parse_slash_command(text: str) -> ParsedSlashCommand | None:
    if not text.startswith("/"):
        return None
    without_slash = text[1:].strip()
    parts = without_slash.split()
    if not parts:
        return None

    command_name = parts[0]
    is_mcp = len(parts) > 1 and parts[1] == "(MCP)"
    args_start = 2 if is_mcp else 1
    if is_mcp:
        command_name = f"{command_name} (MCP)"
    return ParsedSlashCommand(
        name=command_name,
        args=" ".join(parts[args_start:]),
        is_mcp=is_mcp,
    )


def split_slash_command(text: str) -> tuple[str, str] | None:
    parsed = parse_slash_command(text)
    if parsed is None:
        return None
    return parsed.name, parsed.args


def complete_slash_commands(prefix: str, commands: list[SessionCommandDescriptor]) -> list[dict[str, object]]:
    normalized_prefix = prefix[1:] if prefix.startswith("/") else prefix
    completions: list[dict[str, object]] = []
    for command in commands:
        if normalized_prefix and not command.name.startswith(normalized_prefix):
            continue
        completion: dict[str, object] = {
            "value": f"/{command.name}",
            "label": f"/{command.name}",
            "description": command.description,
            "source": command.source,
            "kind": "command",
        }
        if command.conflict_group:
            completion["conflictGroup"] = command.conflict_group
        if command.argument_hint:
            completion["argumentHint"] = command.argument_hint
        completions.append(completion)
    return completions
