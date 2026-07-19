def test_coding_transcript_style_is_shared_function_alias() -> None:
    from loushang.coding.ui.transcript_style import apply_coding_transcript_style
    from loushang.harnesstui.conversation.transcript_style import (
        apply_transcript_style,
    )

    assert apply_coding_transcript_style is apply_transcript_style
