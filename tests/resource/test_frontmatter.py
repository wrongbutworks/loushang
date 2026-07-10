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


def test_legacy_frontmatter_paths_preserve_harness_owner_identity() -> None:
    from loushang.coding.frontmatter import (
        FrontmatterParseError as CodingFrontmatterParseError,
    )
    from loushang.coding.frontmatter import (
        ParsedFrontmatter as CodingParsedFrontmatter,
    )
    from loushang.coding.frontmatter import (
        parse_frontmatter as coding_parse_frontmatter,
    )
    from loushang.coding.frontmatter import (
        strip_frontmatter as coding_strip_frontmatter,
    )
    from loushang.harness.resources.frontmatter import (
        FrontmatterParseError as HarnessFrontmatterParseError,
    )
    from loushang.harness.resources.frontmatter import (
        ParsedFrontmatter as HarnessParsedFrontmatter,
    )
    from loushang.harness.resources.frontmatter import (
        parse_frontmatter as harness_parse_frontmatter,
    )
    from loushang.harness.resources.frontmatter import (
        strip_frontmatter as harness_strip_frontmatter,
    )
    from loushang.resource.frontmatter import (
        FrontmatterParseError,
        ParsedFrontmatter,
        parse_frontmatter,
        strip_frontmatter,
    )

    assert FrontmatterParseError is CodingFrontmatterParseError is HarnessFrontmatterParseError
    assert ParsedFrontmatter is CodingParsedFrontmatter is HarnessParsedFrontmatter
    assert parse_frontmatter is coding_parse_frontmatter is harness_parse_frontmatter
    assert strip_frontmatter is coding_strip_frontmatter is harness_strip_frontmatter
    assert ParsedFrontmatter.__module__ == "loushang.harness.resources.frontmatter"
    assert FrontmatterParseError.__module__ == "loushang.harness.resources.frontmatter"
