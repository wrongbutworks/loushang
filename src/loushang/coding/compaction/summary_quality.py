from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SummaryType = Literal["compaction", "branch"]

_COMPACTION_SECTIONS = (
    "Goal",
    "Constraints & Preferences",
    "Progress",
    "Key Decisions",
    "Next Steps",
    "Critical Context",
)
_BRANCH_SECTIONS = (
    "Goal",
    "Constraints & Preferences",
    "Progress",
    "Key Decisions",
    "Next Steps",
)

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FILE_OPERATION_BLOCK_RE = re.compile(r"\n*<(read-files|modified-files)>.*?</\1>\s*", re.DOTALL)
_FILE_OPERATION_CAPTURE_RE = re.compile(r"<(?P<tag>read-files|modified-files)>\s*(?P<body>.*?)\s*</(?P=tag)>", re.DOTALL)
_PLACEHOLDER_MARKERS = (
    "[what ",
    "[any ",
    '[or "(none)"',
    "[completed ",
    "[include previously ",
    "[current work",
    "[work that ",
    "[issues ",
    "[decision]",
    "[brief rationale]",
    "[ordered list",
    "[what should happen",
    "[update based",
    "[information needed",
    "[preserve ",
)


@dataclass(frozen=True)
class SummaryQualityReport:
    summary_type: SummaryType
    missing_sections: tuple[str, ...] = ()
    empty_sections: tuple[str, ...] = ()
    placeholder_sections: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_sections and not self.empty_sections and not self.placeholder_sections


@dataclass(frozen=True)
class SummaryEvaluationCase:
    name: str
    summary: str | None
    summary_type: SummaryType = "compaction"
    required_phrases: tuple[str, ...] = ()
    expected_read_files: tuple[str, ...] = ()
    expected_modified_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SummaryEvaluationResult:
    case_name: str
    quality_report: SummaryQualityReport = field(default_factory=lambda: SummaryQualityReport(summary_type="compaction"))
    missing_phrases: tuple[str, ...] = ()
    missing_read_files: tuple[str, ...] = ()
    missing_modified_files: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return (
            self.quality_report.ok
            and not self.missing_phrases
            and not self.missing_read_files
            and not self.missing_modified_files
        )


@dataclass(frozen=True)
class SummaryEvaluationSuiteResult:
    results: tuple[SummaryEvaluationResult, ...]

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.ok)

    @property
    def failed_case_names(self) -> tuple[str, ...]:
        return tuple(result.case_name for result in self.results if not result.ok)

    @property
    def ok(self) -> bool:
        return not self.failed_case_names

    def to_dict(self) -> dict[str, object]:
        return {
            "total_count": self.total_count,
            "passed_count": self.passed_count,
            "failed_case_names": list(self.failed_case_names),
        }


def validate_summary_contract(
    summary: str | None,
    *,
    summary_type: SummaryType = "compaction",
) -> SummaryQualityReport:
    required_sections = _required_sections(summary_type)
    sections = _section_contents(summary or "")

    missing = tuple(section for section in required_sections if _normalize_heading(section) not in sections)
    empty = tuple(
        section
        for section in required_sections
        if _normalize_heading(section) in sections and not sections[_normalize_heading(section)].strip()
    )
    placeholders = tuple(
        section
        for section in required_sections
        if _normalize_heading(section) in sections and _has_placeholder_content(sections[_normalize_heading(section)])
    )
    return SummaryQualityReport(
        summary_type=summary_type,
        missing_sections=missing,
        empty_sections=empty,
        placeholder_sections=placeholders,
    )


def evaluate_summary_case(case: SummaryEvaluationCase) -> SummaryEvaluationResult:
    summary = case.summary or ""
    quality_report = validate_summary_contract(summary, summary_type=case.summary_type)
    file_operations = _summary_file_operations(summary)
    return SummaryEvaluationResult(
        case_name=case.name,
        quality_report=quality_report,
        missing_phrases=_missing_phrases(summary, case.required_phrases),
        missing_read_files=_missing_files(file_operations["read-files"], case.expected_read_files),
        missing_modified_files=_missing_files(file_operations["modified-files"], case.expected_modified_files),
    )


def evaluate_summary_cases(cases: list[SummaryEvaluationCase] | tuple[SummaryEvaluationCase, ...]) -> SummaryEvaluationSuiteResult:
    return SummaryEvaluationSuiteResult(results=tuple(evaluate_summary_case(case) for case in cases))


def load_summary_evaluation_cases(path: str | Path) -> tuple[SummaryEvaluationCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, Mapping) else payload
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, str):
        raise TypeError("summary evaluation fixture must contain a sequence of cases")
    return tuple(_summary_evaluation_case_from_mapping(raw_case) for raw_case in raw_cases)


def evaluate_summary_fixture(path: str | Path) -> SummaryEvaluationSuiteResult:
    return evaluate_summary_cases(load_summary_evaluation_cases(path))


def _summary_evaluation_case_from_mapping(value: object) -> SummaryEvaluationCase:
    if not isinstance(value, Mapping):
        raise TypeError("summary evaluation cases must be JSON objects")
    name = value.get("name")
    if not isinstance(name, str) or not name:
        raise TypeError("summary evaluation case requires a non-empty name")
    summary = value.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise TypeError("summary evaluation case summary must be a string or null")
    return SummaryEvaluationCase(
        name=name,
        summary=summary,
        summary_type=_summary_type(value.get("summary_type", "compaction")),
        required_phrases=_string_tuple(value.get("required_phrases", ()), "required_phrases"),
        expected_read_files=_string_tuple(value.get("expected_read_files", ()), "expected_read_files"),
        expected_modified_files=_string_tuple(value.get("expected_modified_files", ()), "expected_modified_files"),
    )


def _required_sections(summary_type: SummaryType) -> tuple[str, ...]:
    if summary_type == "compaction":
        return _COMPACTION_SECTIONS
    if summary_type == "branch":
        return _BRANCH_SECTIONS
    raise ValueError(f"Unsupported summary type: {summary_type}")


def _section_contents(summary: str) -> dict[str, str]:
    text = _strip_file_operation_blocks(summary)
    matches = list(_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = _normalize_heading(match.group(1))
        sections.setdefault(heading, text[start:end].strip())
    return sections


def _strip_file_operation_blocks(summary: str) -> str:
    return _FILE_OPERATION_BLOCK_RE.sub("\n", summary)


def _normalize_heading(heading: str) -> str:
    return " ".join(heading.strip().lower().split())


def _has_placeholder_content(content: str) -> bool:
    lower = content.lower()
    return any(marker in lower for marker in _PLACEHOLDER_MARKERS)


def _summary_file_operations(summary: str) -> dict[str, tuple[str, ...]]:
    operations: dict[str, list[str]] = {"read-files": [], "modified-files": []}
    seen: dict[str, set[str]] = {"read-files": set(), "modified-files": set()}
    for match in _FILE_OPERATION_CAPTURE_RE.finditer(summary):
        tag = match.group("tag")
        for line in match.group("body").splitlines():
            path = line.strip()
            if not path or path in seen[tag]:
                continue
            operations[tag].append(path)
            seen[tag].add(path)
    return {tag: tuple(paths) for tag, paths in operations.items()}


def _missing_phrases(summary: str, required_phrases: tuple[str, ...]) -> tuple[str, ...]:
    normalized_summary = summary.lower()
    return tuple(phrase for phrase in required_phrases if phrase.lower() not in normalized_summary)


def _missing_files(actual_files: tuple[str, ...], expected_files: tuple[str, ...]) -> tuple[str, ...]:
    actual = set(actual_files)
    return tuple(path for path in expected_files if path not in actual)


def _summary_type(value: object) -> SummaryType:
    if value in {"compaction", "branch"}:
        return value
    raise ValueError("summary_type must be 'compaction' or 'branch'")


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain strings")
        result.append(item)
    return tuple(result)
