from __future__ import annotations


def test_format_hotkeys_documents_current_inline_bindings() -> None:
    from loushang.coding.ui.hotkeys import format_hotkeys

    text = format_hotkeys()

    assert text == (
        "Hotkeys:\n"
        "Idle Enter: submit prompt\n"
        "Running Enter: steer current run\n"
        "Running Alt+Enter: queue follow-up\n"
        "Ctrl+J: insert newline\n"
        "Esc/Ctrl-C: abort running request\n"
        "Alt-Up: edit queued messages\n"
        "/quit or /exit: quit"
    )
