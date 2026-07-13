from __future__ import annotations

import pytest

from loushang.harness.context import (
    SummaryProfile,
    SummarySection,
    build_summary_prompt,
    compose_summary_prompt,
    validate_summary,
)


def _research_profile() -> SummaryProfile:
    return SummaryProfile(
        profile_id="research.checkpoint",
        system_prompt="Summarize evidence without adding claims.",
        prompts={
            "initial": "Produce the research checkpoint.",
            "update": "Update the research checkpoint.",
        },
        sections=(
            SummarySection("Question"),
            SummarySection("Findings"),
            SummarySection("Open Evidence"),
        ),
        placeholder_markers=("[finding]", "[source]"),
        ignored_block_tags=("citations",),
    )


def test_build_summary_prompt_uses_profile_blocks_and_custom_focus() -> None:
    prompt = build_summary_prompt(
        _research_profile(),
        "[Researcher]: Revenue grew 12%.",
        mode="update",
        previous_summary="## Question\nWhy did revenue grow?",
        custom_instructions="Retain source dates",
    )

    assert prompt.profile_id == "research.checkpoint"
    assert prompt.mode == "update"
    assert prompt.system_prompt == "Summarize evidence without adding claims."
    assert prompt.user_prompt == (
        "<conversation>\n[Researcher]: Revenue grew 12%.\n</conversation>\n\n"
        "<previous-summary>\n## Question\nWhy did revenue grow?\n"
        "</previous-summary>\n\n"
        "Update the research checkpoint.\n\n"
        "Additional focus: Retain source dates"
    )


def test_compose_summary_prompt_supports_product_owned_tags() -> None:
    prompt = compose_summary_prompt(
        content="slide 3 revised",
        instructions="Summarize the revision.",
        content_tag="revision",
        previous_summary_tag="prior-state",
    )

    assert prompt == (
        "<revision>\nslide 3 revised\n</revision>\n\nSummarize the revision."
    )


def test_validate_summary_uses_profile_sections_and_ignored_blocks() -> None:
    summary = """## Question
Why did revenue grow?

## Findings

## Open Evidence
- [source]

<citations>
## Not A Summary Section
source-1
</citations>
"""

    report = validate_summary(summary, _research_profile())

    assert report.missing_sections == ()
    assert report.empty_sections == ("Findings",)
    assert report.placeholder_sections == ("Open Evidence",)
    assert not report.ok


def test_summary_profile_rejects_duplicate_sections_and_unknown_modes() -> None:
    with pytest.raises(ValueError, match="headings must be unique"):
        SummaryProfile(
            profile_id="duplicate",
            system_prompt="Summarize.",
            prompts={"initial": "Summarize."},
            sections=(SummarySection("Goal"), SummarySection(" goal ")),
        )

    with pytest.raises(KeyError, match="has no mode"):
        _research_profile().prompt("branch")
