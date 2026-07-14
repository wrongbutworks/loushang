from __future__ import annotations

import pytest

from loushang.harness.capabilities.prompt import (
    PromptSection,
    PromptTemplateExpander,
    compose_prompt_sections,
    expand_prompt_template,
    parse_prompt_template_args,
    substitute_prompt_template_args,
)


def test_prompt_sections_compose_in_product_order_with_trace() -> None:
    sections = [
        PromptSection("base", "  Research assistant  ", kind="base"),
        PromptSection("workspace", "", kind="context"),
        PromptSection("method", "Check primary sources", kind="method"),
        PromptSection("footer", "As of 2026-07-14", kind="runtime"),
    ]

    prepared = compose_prompt_sections(sections)
    sections.append(PromptSection("late", "not included"))

    assert prepared.text == (
        "Research assistant\n\nCheck primary sources\n\nAs of 2026-07-14"
    )
    assert [section.section_id for section in prepared.sections] == [
        "base",
        "method",
        "footer",
    ]
    assert [entry.included for entry in prepared.trace] == [
        True,
        False,
        True,
        True,
    ]
    assert prepared.trace[1].reason == "empty"
    assert prepared.trace[2].output_index == 1


def test_prompt_section_composition_validates_inputs() -> None:
    with pytest.raises(TypeError, match="iterable"):
        compose_prompt_sections("not-sections")
    with pytest.raises(TypeError, match="PromptSection"):
        compose_prompt_sections([object()])
    with pytest.raises(ValueError, match="section id"):
        PromptSection("", "content")


def test_default_template_expansion_preserves_pi_compatible_arguments() -> None:
    args = parse_prompt_template_args('company "primary sources" valuation')

    assert args == ["company", "primary sources", "valuation"]
    assert substitute_prompt_template_args(
        "Name: $1\nRest: ${@:2}\nPair: ${@:2:1}\nAll: $ARGUMENTS",
        args,
    ) == (
        "Name: company\n"
        "Rest: primary sources valuation\n"
        "Pair: primary sources\n"
        "All: company primary sources valuation"
    )
    assert expand_prompt_template("Review $1", "annual-report") == (
        "Review annual-report"
    )
    assert expand_prompt_template("Review the company", "carefully") == (
        "Review the company\n\ncarefully"
    )


def test_template_expansion_policy_is_fully_injectable() -> None:
    calls: list[object] = []
    expander = PromptTemplateExpander(
        parse_arguments=lambda raw: calls.append(("parse", raw)) or raw.split("|"),
        has_placeholders=lambda content: calls.append(("probe", content)) or True,
        substitute=lambda content, args: (
            calls.append(("substitute", content, tuple(args)))
            or f"{content}:{','.join(args)}"
        ),
        append_arguments=lambda content, raw: (
            calls.append(("append", content, raw)) or "unused"
        ),
    )

    assert expander.expand("Investigate", "claims|sources") == (
        "Investigate:claims,sources"
    )
    assert calls == [
        ("probe", "Investigate"),
        ("parse", "claims|sources"),
        ("substitute", "Investigate", ("claims", "sources")),
    ]


def test_template_expansion_does_not_reprocess_argument_values() -> None:
    assert (
        substitute_prompt_template_args("$ARGUMENTS", ["$1", "$ARGUMENTS", "${@:2}"])
        == "$1 $ARGUMENTS ${@:2}"
    )
