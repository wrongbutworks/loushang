from __future__ import annotations


def format_hotkeys() -> str:
    return "\n".join(
        [
            "Hotkeys:",
            "Idle Enter: submit prompt",
            "Running Enter: steer current run",
            "Running Alt+Enter: queue follow-up",
            "Ctrl+J: insert newline",
            "Esc/Ctrl-C: abort running request",
            "Alt-Up: edit queued messages",
            "/quit or /exit: quit",
        ]
    )


__all__ = ["format_hotkeys"]
