from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedFrontmatter:
    frontmatter: dict[str, object]
    body: str


class FrontmatterParseError(ValueError):
    pass


def parse_frontmatter(content: str) -> ParsedFrontmatter:
    normalized = _normalize_newlines(content)
    yaml_text, body = _extract_frontmatter(normalized)
    if yaml_text is None:
        return ParsedFrontmatter({}, body)
    return ParsedFrontmatter(_parse_yaml_subset(yaml_text), body)


def strip_frontmatter(content: str) -> str:
    return parse_frontmatter(content).body


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _extract_frontmatter(content: str) -> tuple[str | None, str]:
    if not content.startswith("---"):
        return None, content
    end_index = content.find("\n---", 3)
    if end_index == -1:
        return None, content
    return content[4:end_index], content[end_index + 4 :].strip()


def _parse_yaml_subset(yaml_text: str) -> dict[str, object]:
    values: dict[str, object] = {}
    lines = yaml_text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line or line.startswith("#"):
            index += 1
            continue
        if raw_line[:1].isspace():
            raise _frontmatter_error(index, 1, raw_line, "unexpected indentation")
        if ":" not in raw_line:
            raise _frontmatter_error(index, 1, raw_line, "expected key-value pair")
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            raise _frontmatter_error(index, 1, raw_line, "expected key")
        value = raw_value.strip()
        if value in {"|", "|-", "|+"}:
            block, index = _parse_block_scalar(lines, index + 1, chomp=value)
            values[key] = block
            continue
        if not value and _next_line_is_indented(lines, index + 1):
            collection, index = _parse_collection(lines, index + 1, parent_key=key)
            values[key] = collection
            continue
        values[key] = _parse_scalar(value, line_number=index, line=raw_line, key=key)
        index += 1
    return values


def _next_line_is_indented(lines: list[str], index: int) -> bool:
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        return raw_line[:1].isspace()
    return False


def _parse_collection(lines: list[str], index: int, *, parent_key: str) -> tuple[object, int]:
    return _parse_collection_at_indent(lines, index, indent=2, parent_key=parent_key)


def _parse_collection_at_indent(
    lines: list[str],
    index: int,
    *,
    indent: int,
    parent_key: str,
) -> tuple[object, int]:
    index = _skip_ignored_lines(lines, index)
    if index >= len(lines):
        return "", index
    raw_line = lines[index]
    prefix = " " * indent
    if raw_line.startswith(f"{prefix}- "):
        return _parse_list(lines, index, indent=indent, parent_key=parent_key)
    if raw_line.startswith(prefix):
        return _parse_map(lines, index, indent=indent, parent_key=parent_key)
    return "", index


def _parse_list(lines: list[str], index: int, *, indent: int, parent_key: str) -> tuple[list[object], int]:
    values: list[object] = []
    prefix = " " * indent
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        line_indent = _indent_width(raw_line)
        if line_indent < indent:
            break
        if line_indent != indent or not raw_line.startswith(f"{prefix}- "):
            raise _frontmatter_error(index, 1, raw_line, "unexpected indentation")
        item_value = raw_line[indent + 2 :].strip()
        values.append(_parse_scalar(item_value, line_number=index, line=raw_line, key=parent_key))
        index += 1
    return values, index


def _parse_map(lines: list[str], index: int, *, indent: int, parent_key: str) -> tuple[dict[str, object], int]:
    values: dict[str, object] = {}
    prefix = " " * indent
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        line_indent = _indent_width(raw_line)
        if line_indent < indent:
            break
        if line_indent != indent or not raw_line.startswith(prefix):
            raise _frontmatter_error(index, 1, raw_line, "unexpected indentation")
        line = raw_line[indent:]
        if ":" not in line:
            raise _frontmatter_error(index, indent + 1, raw_line, "expected key-value pair")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise _frontmatter_error(index, indent + 1, raw_line, "expected key")
        value = raw_value.strip()
        if not value and _next_line_is_deeper(lines, index + 1, indent=indent):
            nested, index = _parse_collection_at_indent(
                lines,
                index + 1,
                indent=indent + 2,
                parent_key=f"{parent_key}.{key}",
            )
            values[key] = nested
            continue
        values[key] = _parse_scalar(value, line_number=index, line=raw_line, key=key)
        index += 1
    return values, index


def _skip_ignored_lines(lines: list[str], index: int) -> int:
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            return index
        index += 1
    return index


def _next_line_is_deeper(lines: list[str], index: int, *, indent: int) -> bool:
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        return _indent_width(raw_line) > indent
    return False


def _indent_width(raw_line: str) -> int:
    return len(raw_line) - len(raw_line.lstrip(" "))


def _parse_block_scalar(lines: list[str], index: int, *, chomp: str) -> tuple[str, int]:
    block_lines: list[str] = []
    while index < len(lines):
        raw_line = lines[index]
        if raw_line.strip() and not raw_line[:1].isspace():
            break
        if raw_line.startswith("  "):
            block_lines.append(raw_line[2:])
        elif raw_line.startswith("\t"):
            block_lines.append(raw_line[1:])
        else:
            block_lines.append("")
        index += 1
    value = "\n".join(block_lines)
    if chomp != "|-":
        value += "\n"
    return value, index


def _parse_scalar(value: str, *, line_number: int, line: str, key: str) -> object:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "~"}:
        return None
    if value.startswith("["):
        if not value.endswith("]"):
            column = line.index(value) + 1
            raise _frontmatter_error(line_number, column, line, f'invalid value for "{key}"')
        return _parse_inline_list(value, line_number=line_number, line=line, key=key)
    if (value.startswith('"') and not value.endswith('"')) or (value.startswith("'") and not value.endswith("'")):
        column = line.index(value) + 1
        raise _frontmatter_error(line_number, column, line, f'unterminated quoted value for "{key}"')
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_inline_list(value: str, *, line_number: int, line: str, key: str) -> list[object]:
    items = value[1:-1].strip()
    if not items:
        return []
    return [
        _parse_scalar(item.strip(), line_number=line_number, line=line, key=key)
        for item in items.split(",")
        if item.strip()
    ]


def _frontmatter_error(line_number: int, column: int, line: str, reason: str) -> FrontmatterParseError:
    return FrontmatterParseError(f"Invalid frontmatter at line {line_number + 1}, column {column}: {reason}: {line.strip()}")


__all__ = ["FrontmatterParseError", "ParsedFrontmatter", "parse_frontmatter", "strip_frontmatter"]
