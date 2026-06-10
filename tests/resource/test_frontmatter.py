from __future__ import annotations


def test_frontmatter_parser_has_product_neutral_entrypoint() -> None:
    from loushang.resource.frontmatter import parse_frontmatter

    result = parse_frontmatter("---\nname: review\n---\n\nRun review.")

    assert result.frontmatter == {"name": "review"}
    assert result.body == "Run review."


def test_coding_frontmatter_entrypoint_remains_compatible() -> None:
    from loushang.coding.frontmatter import (
        parse_frontmatter as coding_parse_frontmatter,
    )
    from loushang.resource.frontmatter import parse_frontmatter

    assert coding_parse_frontmatter is parse_frontmatter
