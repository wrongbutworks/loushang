from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from loushang.harness.capabilities.commands import CommandDescriptor
from loushang.harness.resources.source import SourceInfo

SlashCommandSource = Literal["builtin", "extension", "prompt", "skill"]


CommandSourceInfo = SourceInfo


@dataclass(frozen=True)
class SessionCommandDescriptor(CommandDescriptor[SourceInfo[str]]):
    source: SlashCommandSource
    source_info: SourceInfo[str] = field()


@dataclass(frozen=True)
class SlashCommandInfo:
    name: str
    description: str | None
    source: SlashCommandSource
    source_info: SourceInfo[str]


@dataclass(frozen=True)
class BuiltinSlashCommand:
    name: str
    description: str


BUILTIN_SLASH_COMMANDS: tuple[BuiltinSlashCommand, ...] = (
    BuiltinSlashCommand(name="settings", description="Open settings menu"),
    BuiltinSlashCommand(name="model", description="Select model (opens selector UI)"),
    BuiltinSlashCommand(name="scoped-models", description="Enable/disable models for Ctrl+P cycling"),
    BuiltinSlashCommand(name="export", description="Export session (HTML default, or specify path: .html/.jsonl)"),
    BuiltinSlashCommand(name="import", description="Import and resume a session from a JSONL file"),
    BuiltinSlashCommand(name="share", description="Share session as a secret GitHub gist"),
    BuiltinSlashCommand(name="copy", description="Copy an assistant message to clipboard"),
    BuiltinSlashCommand(name="name", description="Set session display name"),
    BuiltinSlashCommand(name="session", description="Show session info and stats"),
    BuiltinSlashCommand(name="terminal", description="Show terminal capabilities and protocol diagnostics"),
    BuiltinSlashCommand(name="tools", description="Show or update active tools for this session"),
    BuiltinSlashCommand(name="extensions", description="Show loaded extensions and diagnostics"),
    BuiltinSlashCommand(name="changelog", description="Show changelog entries"),
    BuiltinSlashCommand(name="hotkeys", description="Show all keyboard shortcuts"),
    BuiltinSlashCommand(name="fork", description="Create a new fork from a previous user message"),
    BuiltinSlashCommand(name="clone", description="Duplicate the current session at the current position"),
    BuiltinSlashCommand(name="tree", description="Navigate session tree (switch branches)"),
    BuiltinSlashCommand(name="login", description="Configure provider authentication"),
    BuiltinSlashCommand(name="logout", description="Remove provider authentication"),
    BuiltinSlashCommand(name="new", description="Start a new session"),
    BuiltinSlashCommand(name="compact", description="Manually compact the session context"),
    BuiltinSlashCommand(name="resume", description="Resume a different session"),
    BuiltinSlashCommand(name="reload", description="Reload keybindings, extensions, skills, prompts, and themes"),
    BuiltinSlashCommand(name="quit", description="Quit loushang"),
)
