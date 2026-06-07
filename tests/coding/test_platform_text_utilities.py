from __future__ import annotations

from pathlib import Path

from loushang.coding.control.config_value import (
    ConfigCommandResult,
    ConfigValueResolver,
)
from loushang.coding.platform.changelog import format_changelog_entries, parse_changelog
from loushang.coding.platform.clipboard import ClipboardCopyResult, copy_to_clipboard


def test_config_value_resolver_prefers_env_then_literal_and_caches_command_results() -> None:
    calls: list[str] = []

    def runner(command: str, *, timeout_seconds: float) -> ConfigCommandResult:
        calls.append(f"{command}:{timeout_seconds:g}")
        return ConfigCommandResult(ok=True, stdout=" token-from-command \n")

    resolver = ConfigValueResolver(env={"API_KEY": "env-token"}, runner=runner)

    assert resolver.resolve("API_KEY") == "env-token"
    assert resolver.resolve("literal-token") == "literal-token"
    assert resolver.resolve("!printf token") == "token-from-command"
    assert resolver.resolve("!printf token") == "token-from-command"
    assert calls == ["printf token:10"]


def test_copy_to_clipboard_uses_platform_command_with_text_stdin() -> None:
    calls: list[tuple[str, tuple[str, ...], str]] = []

    def runner(command: str, args: tuple[str, ...], *, input_text: str, timeout_seconds: float) -> ClipboardCopyResult:
        del timeout_seconds
        calls.append((command, args, input_text))
        return ClipboardCopyResult(ok=True, command=command)

    result = copy_to_clipboard(
        "hello",
        env={"WAYLAND_DISPLAY": "wayland-1"},
        runner=runner,
    )

    assert result.ok is True
    assert result.command == "wl-copy"
    assert calls == [("wl-copy", tuple(), "hello")]


def test_parse_changelog_extracts_markdown_entries(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [1.2.0] - 2026-05-01\n\n"
        "- Added builtin commands.\n"
        "- Fixed config resolution.\n\n"
        "## Unreleased\n\n"
        "- Work in progress.\n",
        encoding="utf-8",
    )

    entries = parse_changelog(changelog)

    assert [(entry.version, entry.date, entry.body) for entry in entries] == [
        ("1.2.0", "2026-05-01", "- Added builtin commands.\n- Fixed config resolution."),
        ("Unreleased", None, "- Work in progress."),
    ]
    assert format_changelog_entries(entries, limit=1) == (
        "## [1.2.0] - 2026-05-01\n\n"
        "- Added builtin commands.\n"
        "- Fixed config resolution."
    )
