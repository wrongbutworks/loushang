from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping as MappingABC

from loushang.method.types import MethodApplicability


def applicability_from_frontmatter(frontmatter: MappingABC[str, object]) -> MethodApplicability:
    domains = _string_tuple_hint(frontmatter, ("domains", "domain"))
    return MethodApplicability(
        domains=domains,
        task_types=_string_tuple_hint(frontmatter, ("task_types", "task-types", "task_type", "task-type")),
        contexts=_string_tuple_hint(frontmatter, ("contexts", "context")),
        artifact_types=_string_tuple_hint(
            frontmatter,
            ("artifact_types", "artifact-types", "artifact_type", "artifact-type"),
        ),
        modalities=_string_tuple_hint(frontmatter, ("modalities", "modality")),
        toolchains=_string_tuple_hint(frontmatter, ("toolchains", "toolchain")),
        lifecycle=_string_tuple_hint(frontmatter, ("lifecycle",)),
        capabilities=_string_tuple_hint(frontmatter, ("capabilities", "capability")),
        complexity=_string_hint(frontmatter, "complexity"),
        risk=_string_hint(frontmatter, "risk"),
        tags=_tags_hint(frontmatter.get("tags")),
    )


def primary_domain(
    frontmatter: MappingABC[str, object],
    applicability: MethodApplicability,
) -> str | None:
    return _string_hint(frontmatter, "domain") or _first(applicability.domains)


def _string_tuple_hint(frontmatter: MappingABC[str, object], keys: tuple[str, ...]) -> tuple[str, ...]:
    for key in keys:
        values = _string_tuple(frontmatter.get(key))
        if values:
            return values
    return ()


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Iterable) and not isinstance(value, MappingABC):
        values = tuple(item for item in value if isinstance(item, str) and item)
        return values
    return ()


def _string_hint(frontmatter: MappingABC[str, object], key: str) -> str | None:
    value = frontmatter.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _tags_hint(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, MappingABC):
        return {}
    tags: dict[str, tuple[str, ...]] = {}
    for key, raw_values in value.items():
        values = _string_tuple(raw_values)
        if isinstance(key, str) and key and values:
            tags[key] = values
    return tags


def _first(values: tuple[str, ...]) -> str | None:
    if values:
        return values[0]
    return None


__all__ = ["applicability_from_frontmatter", "primary_domain"]
