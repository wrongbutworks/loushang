from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from typing import Literal, TypedDict


LineEnding = Literal["\r\n", "\n"]


class EditEntry(TypedDict):
    oldText: str
    newText: str


@dataclass(frozen=True)
class BomText:
    bom: str
    text: str


@dataclass(frozen=True)
class FuzzyMatchResult:
    found: bool
    index: int
    match_length: int
    used_fuzzy_match: bool
    content_for_replacement: str


@dataclass(frozen=True)
class AppliedEditsResult:
    base_content: str
    new_content: str


@dataclass(frozen=True)
class DiffStringResult:
    diff: str
    first_changed_line: int | None


_SMART_QUOTE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
)


def detect_line_ending(content: str) -> LineEnding:
    crlf_index = content.find("\r\n")
    lf_index = content.find("\n")
    if lf_index == -1 or crlf_index == -1:
        return "\n"
    return "\r\n" if crlf_index <= lf_index else "\n"


def normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(text: str, ending: LineEnding) -> str:
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


def normalize_for_fuzzy_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    stripped_trailing_whitespace = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return stripped_trailing_whitespace.translate(_SMART_QUOTE_TRANSLATION)


def fuzzy_find_text(content: str, old_text: str) -> FuzzyMatchResult:
    exact_index = content.find(old_text)
    if exact_index != -1:
        return FuzzyMatchResult(
            found=True,
            index=exact_index,
            match_length=len(old_text),
            used_fuzzy_match=False,
            content_for_replacement=content,
        )

    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old_text = normalize_for_fuzzy_match(old_text)
    fuzzy_index = fuzzy_content.find(fuzzy_old_text)
    if fuzzy_index == -1:
        return FuzzyMatchResult(
            found=False,
            index=-1,
            match_length=0,
            used_fuzzy_match=False,
            content_for_replacement=content,
        )

    return FuzzyMatchResult(
        found=True,
        index=fuzzy_index,
        match_length=len(fuzzy_old_text),
        used_fuzzy_match=True,
        content_for_replacement=fuzzy_content,
    )


def strip_bom(content: str) -> BomText:
    if content.startswith("\ufeff"):
        return BomText(bom="\ufeff", text=content[1:])
    return BomText(bom="", text=content)


def apply_text_edits(content: str, edits: list[EditEntry], *, path: str) -> str:
    stripped = strip_bom(content)
    line_ending = detect_line_ending(stripped.text)
    normalized_body = normalize_to_lf(stripped.text)
    applied = apply_edits_to_normalized_content(normalized_body, edits, path=path)
    return stripped.bom + restore_line_endings(applied.new_content, line_ending)


def apply_edits_to_normalized_content(
    normalized_content: str,
    edits: list[EditEntry],
    *,
    path: str,
) -> AppliedEditsResult:
    normalized_edits = [
        {
            "oldText": normalize_to_lf(edit["oldText"]),
            "newText": normalize_to_lf(edit["newText"]),
        }
        for edit in edits
    ]

    for index, edit in enumerate(normalized_edits):
        if not edit["oldText"]:
            raise ValueError(f"edits[{index}].oldText must not be empty in {path}.")

    initial_matches = [fuzzy_find_text(normalized_content, edit["oldText"]) for edit in normalized_edits]
    base_content = (
        normalize_for_fuzzy_match(normalized_content)
        if any(match.used_fuzzy_match for match in initial_matches)
        else normalized_content
    )

    planned: list[tuple[int, int, int, str]] = []
    for index, edit in enumerate(normalized_edits):
        old_text = edit["oldText"]
        match = fuzzy_find_text(base_content, old_text)
        if not match.found:
            raise ValueError(f"edits[{index}] in {path} did not match any content: {old_text!r}")
        if _count_occurrences(base_content, old_text) > 1:
            raise ValueError(f"edits[{index}] in {path} matched more than once: {old_text!r}")
        planned.append((match.index, match.index + match.match_length, index, edit["newText"]))

    planned.sort(key=lambda item: item[0])
    for previous, current in zip(planned, planned[1:]):
        if current[0] < previous[1]:
            raise ValueError(
                f"edits[{previous[2]}] and edits[{current[2]}] overlap in {path}. "
                "Merge them into one edit or target disjoint regions."
            )

    new_content = base_content
    for start, end, _, new_text in reversed(planned):
        new_content = new_content[:start] + new_text + new_content[end:]

    if new_content == base_content:
        raise ValueError(f"No changes made to {path}. The replacement produced identical content.")
    return AppliedEditsResult(base_content=base_content, new_content=new_content)


def build_unified_diff(path: str, original: str, updated: str) -> str:
    return "".join(
        unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def first_changed_line(original: str, updated: str) -> int | None:
    original_lines = original.splitlines()
    updated_lines = updated.splitlines()
    for index in range(max(len(original_lines), len(updated_lines))):
        old_line = original_lines[index] if index < len(original_lines) else None
        new_line = updated_lines[index] if index < len(updated_lines) else None
        if old_line != new_line:
            return index + 1
    return None


def generate_diff_string(old_content: str, new_content: str, context_lines: int = 4) -> DiffStringResult:
    old_lines = old_content.split("\n")
    new_lines = new_content.split("\n")
    if old_lines and old_lines[-1] == "":
        old_lines = old_lines[:-1]
    if new_lines and new_lines[-1] == "":
        new_lines = new_lines[:-1]

    width = len(str(max(len(old_lines), len(new_lines), 1)))
    output: list[str] = []
    first_changed: int | None = None
    matcher = SequenceMatcher(a=old_lines, b=new_lines)
    grouped = matcher.get_grouped_opcodes(context_lines)

    for group_index, group in enumerate(grouped):
        if group_index > 0:
            output.append(f" {'':>{width}} ...")
        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                for offset, line in enumerate(old_lines[old_start:old_end]):
                    output.append(f" {old_start + offset + 1:>{width}} {line}")
                continue
            if first_changed is None:
                first_changed = new_start + 1
            if tag in {"replace", "delete"}:
                for offset, line in enumerate(old_lines[old_start:old_end]):
                    output.append(f"-{old_start + offset + 1:>{width}} {line}")
            if tag in {"replace", "insert"}:
                for offset, line in enumerate(new_lines[new_start:new_end]):
                    output.append(f"+{new_start + offset + 1:>{width}} {line}")

    return DiffStringResult(diff="\n".join(output), first_changed_line=first_changed)


def compute_edits_diff_for_content(path: str, content: str, edits: list[EditEntry]) -> DiffStringResult:
    stripped = strip_bom(content)
    normalized_content = normalize_to_lf(stripped.text)
    applied = apply_edits_to_normalized_content(normalized_content, edits, path=path)
    return generate_diff_string(applied.base_content, applied.new_content)


def _count_occurrences(content: str, old_text: str) -> int:
    needle = normalize_for_fuzzy_match(old_text)
    if not needle:
        return 0
    haystack = normalize_for_fuzzy_match(content)
    count = 0
    cursor = 0
    while True:
        start = haystack.find(needle, cursor)
        if start == -1:
            return count
        count += 1
        cursor = start + len(needle)
