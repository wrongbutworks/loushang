from __future__ import annotations

import pytest

from loushang.harness.resources.frontmatter import (
    FrontmatterParseError,
    ParsedFrontmatter,
    parse_frontmatter,
    strip_frontmatter,
)


def test_parse_frontmatter_returns_plain_content_unchanged() -> None:
    assert parse_frontmatter("Body only") == ParsedFrontmatter({}, "Body only")


def test_parse_frontmatter_normalizes_newlines_and_block_scalars() -> None:
    result = parse_frontmatter(
        "---\r\n"
        "name: review\r\n"
        "description: |\r\n"
        "  Review pull requests\r\n"
        "  and summarize risks.\r\n"
        "enabled: true\r\n"
        "---\r\n\r\n"
        "Run the review.\r\n"
    )

    assert result.frontmatter == {
        "name": "review",
        "description": "Review pull requests\nand summarize risks.\n",
        "enabled": True,
    }
    assert result.body == "Run the review."


def test_parse_frontmatter_supports_lists_and_nested_maps() -> None:
    result = parse_frontmatter(
        "---\n"
        "domains:\n"
        "  - coding\n"
        "  - research\n"
        "steps:\n"
        "  inspect:\n"
        "    level: reasoned\n"
        "    required: true\n"
        "  verify:\n"
        "    evidence:\n"
        "      - tests\n"
        "      - logs\n"
        "---\n\n"
        "Run the review.\n"
    )

    assert result.frontmatter == {
        "domains": ["coding", "research"],
        "steps": {
            "inspect": {"level": "reasoned", "required": True},
            "verify": {"evidence": ["tests", "logs"]},
        },
    }


def test_parse_frontmatter_preserves_unterminated_document() -> None:
    content = "---\nname: review\nRun the review."

    assert parse_frontmatter(content) == ParsedFrontmatter({}, content)
    assert strip_frontmatter(content) == content


def test_strip_frontmatter_returns_body() -> None:
    assert strip_frontmatter("---\nname: review\n---\n\nRun review.") == "Run review."


def test_parse_frontmatter_reports_source_location() -> None:
    with pytest.raises(FrontmatterParseError) as error:
        parse_frontmatter("---\ndescription: [broken\n---\nBody")

    assert "line 1" in str(error.value)
    assert "description" in str(error.value)
