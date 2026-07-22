from __future__ import annotations

from io import StringIO

from loushang.harness.host.prompt_input import resolve_prompt_input


def test_resolve_prompt_input_combines_stdin_file_prompt_and_followups(tmp_path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("file context", encoding="utf-8")

    result = resolve_prompt_input(
        prompt="final request",
        messages=("additional",),
        message_prompts=("next", "last"),
        file_args=(f"@{notes.name}",),
        stdin=StringIO("stdin context"),
        cwd=tmp_path,
    )

    assert result.user_input is not None
    assert "stdin context" in result.user_input
    assert "file context" in result.user_input
    assert result.user_input.endswith("final requestadditional")
    assert result.images is None
    assert result.follow_up_messages == ("next", "last")


def test_resolve_prompt_input_promotes_first_followup_when_prompt_is_empty(tmp_path) -> None:
    result = resolve_prompt_input(
        prompt=None,
        messages=(),
        message_prompts=("first", "second"),
        file_args=(),
        stdin=StringIO(""),
        cwd=tmp_path,
    )

    assert result.user_input == "first"
    assert result.follow_up_messages == ("second",)
