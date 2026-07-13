from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from loushang.agent import (
    AgentToolResult,
    FunctionalToolOutputProjector,
    ToolOutputPreviewPolicy,
    ToolOutputProjectionError,
)
from loushang.ai import ImagePart, TextPart


@dataclass(frozen=True)
class _Details:
    path: Path
    lines: tuple[str, ...]


class _HostileTruthValue:
    def __bool__(self) -> bool:
        raise AssertionError("terminate truthiness must not be evaluated")


def test_functional_projector_exposes_distinct_boundary_views() -> None:
    projector = FunctionalToolOutputProjector[_Details](
        transcript=lambda details: {
            "path": str(details.path),
            "lines": list(details.lines),
        },
        event=lambda details: {
            "path": str(details.path),
            "lineCount": len(details.lines),
        },
        hook=lambda details: {"path": str(details.path)},
    )
    result = AgentToolResult(
        content=[],
        details=_Details(Path("notes.txt"), ("one", "two")),
        projector=projector,
    )

    assert result.transcript_details() == {
        "path": "notes.txt",
        "lines": ["one", "two"],
    }
    assert result.event_details() == {"path": "notes.txt", "lineCount": 2}
    assert result.hook_details() == {"path": "notes.txt"}
    assert result.for_presentation().details == result.transcript_details()


def test_default_projector_rejects_non_json_details_with_target_and_path() -> None:
    result = AgentToolResult(content=[], details={"path": Path("notes.txt")})

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        result.event_details()

    assert exc_info.value.target == "event"
    assert exc_info.value.path == "tool_output.details.path"
    assert exc_info.value.value_type == type(Path("notes.txt")).__name__


def test_functional_projector_validates_callback_output() -> None:
    result = AgentToolResult(
        content=[],
        details=_Details(Path("notes.txt"), ()),
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: {"path": details.path},
        ),
    )

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        result.transcript_details()

    assert exc_info.value.target == "transcript"
    assert exc_info.value.path == "tool_output.details.path"


def test_tool_output_preview_is_deterministic_and_bounded() -> None:
    result = AgentToolResult(
        content=[],
        details={"lines": ["first", "second", "third"]},
    )

    preview = result.log_preview(ToolOutputPreviewPolicy(max_bytes=32, max_lines=1))

    assert len(preview.encode("utf-8")) <= 32
    assert "preview truncated" in preview


def test_boundary_projection_is_snapshotted_on_first_access() -> None:
    details = {"value": 1}
    result = AgentToolResult(content=[], details=details)

    assert result.event_details() == {"value": 1}

    details["value"] = 2
    projected = result.event_details()
    assert projected == {"value": 1}

    assert isinstance(projected, dict)
    projected["value"] = 3
    assert result.event_details() == {"value": 1}


def test_custom_preview_is_validated_and_respects_small_byte_limits() -> None:
    result = AgentToolResult(
        content=[],
        details={"value": 1},
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: details,
            preview=lambda details, policy: "first\nsecond",
        ),
    )

    preview = result.log_preview(ToolOutputPreviewPolicy(max_bytes=8, max_lines=1))

    assert len(preview.encode("utf-8")) <= 8

    invalid = AgentToolResult(
        content=[],
        details={"value": 1},
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: details,
            preview=lambda details, policy: 1,  # type: ignore[arg-type,return-value]
        ),
    )
    with pytest.raises(ToolOutputProjectionError) as exc_info:
        invalid.log_preview()
    assert exc_info.value.target == "diagnostic"


def test_custom_projector_output_is_snapshotted_before_external_mutation() -> None:
    shared = {"nested": {"value": 1}}

    class SharedProjector:
        def to_transcript_details(self, details):
            del details
            return shared

        def to_event_details(self, details):
            del details
            return shared

        def to_hook_details(self, details):
            del details
            return shared

        def log_preview(self, details, policy):
            del details, policy
            return "shared"

    result = AgentToolResult(
        content=[TextPart(type="text", text="ok")],
        details=object(),
        projector=SharedProjector(),
    )

    assert result.event_details() == {"nested": {"value": 1}}
    shared["nested"]["value"] = 2
    assert result.event_details() == {"nested": {"value": 1}}

    presentation = result.for_presentation()
    presentation.content.clear()
    assert result.content == [TextPart(type="text", text="ok")]


def test_event_snapshot_keeps_safe_event_and_transcript_views_independent() -> None:
    raw_details = object()
    result = AgentToolResult(
        content=[TextPart(type="text", text="ok")],
        details=raw_details,
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: {"view": "transcript"},
            event=lambda details: {"view": "event"},
        ),
    )

    event_result = result.for_event()

    assert event_result.details == {"view": "event"}
    assert event_result.details is not raw_details
    assert event_result.event_details() == {"view": "event"}
    assert event_result.transcript_details() == {"view": "transcript"}

    assert isinstance(event_result.details, dict)
    event_result.details["view"] = "mutated"
    assert event_result.event_details() == {"view": "event"}
    assert event_result.transcript_details() == {"view": "transcript"}


def test_event_snapshot_defers_invalid_transcript_projection() -> None:
    result = AgentToolResult(
        content=[TextPart(type="text", text="partial")],
        details=object(),
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: {"path": Path("notes.txt")},
            event=lambda details: {"progress": "half"},
        ),
    )

    event_result = result.for_event()

    assert event_result.event_details() == {"progress": "half"}
    with pytest.raises(ToolOutputProjectionError) as exc_info:
        event_result.transcript_details()
    assert exc_info.value.target == "transcript"


def test_custom_projector_invalid_output_keeps_target_and_nested_path() -> None:
    class InvalidProjector:
        def to_transcript_details(self, details):
            return details

        def to_event_details(self, details):
            return details

        def to_hook_details(self, details):
            return details

        def log_preview(self, details, policy):
            return "invalid"

    result = AgentToolResult(
        content=[],
        details={"nested": {"path": Path("notes.txt")}},
        projector=InvalidProjector(),
    )

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        result.event_details()

    assert exc_info.value.target == "event"
    assert exc_info.value.path == "tool_output.details.nested.path"
    assert exc_info.value.value_type == type(Path("notes.txt")).__name__


def test_functional_projector_preview_failures_use_diagnostic_target() -> None:
    invalid_unicode = AgentToolResult(
        content=[],
        details={"value": 1},
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: details,
            preview=lambda details, policy: "\ud800",
        ),
    )
    broken_fallback = AgentToolResult(
        content=[],
        details={"value": 1},
        projector=FunctionalToolOutputProjector(
            transcript=lambda details: details,
            event=lambda details: (_ for _ in ()).throw(RuntimeError("boom")),
        ),
    )

    with pytest.raises(ToolOutputProjectionError) as unicode_error:
        invalid_unicode.log_preview()
    with pytest.raises(ToolOutputProjectionError) as fallback_error:
        broken_fallback.log_preview()

    assert unicode_error.value.target == "diagnostic"
    assert unicode_error.value.path == "tool_output.preview"
    assert fallback_error.value.target == "diagnostic"


def test_functional_projector_honors_falsey_explicit_callbacks() -> None:
    class FalseyCallback:
        def __init__(self, view: str) -> None:
            self.view = view

        def __bool__(self) -> bool:
            return False

        def __call__(self, details):
            del details
            return {"view": self.view}

    result = AgentToolResult(
        content=[],
        details=object(),
        projector=FunctionalToolOutputProjector(
            transcript=FalseyCallback("transcript"),
            event=FalseyCallback("event"),
            hook=FalseyCallback("hook"),
        ),
    )

    assert result.event_details() == {"view": "event"}
    assert result.hook_details() == {"view": "hook"}


@pytest.mark.parametrize(
    ("part", "path", "value_type"),
    [
        (TextPart(type="image", text="ok"), "tool_output.content[0].type", "str"),  # type: ignore[arg-type]
        (TextPart(type="text", text=1), "tool_output.content[0].text", "int"),  # type: ignore[arg-type]
        (
            TextPart(type="text", text="ok", text_signature=[]),  # type: ignore[arg-type]
            "tool_output.content[0].textSignature",
            "list",
        ),
        (
            ImagePart(type="text", data="aW1n", mime_type="image/png"),  # type: ignore[arg-type]
            "tool_output.content[0].type",
            "str",
        ),
        (
            ImagePart(type="image", data=1, mime_type="image/png"),  # type: ignore[arg-type]
            "tool_output.content[0].data",
            "int",
        ),
        (
            ImagePart(type="image", data="aW1n", mime_type=None),  # type: ignore[arg-type]
            "tool_output.content[0].mimeType",
            "NoneType",
        ),
    ],
)
def test_content_snapshot_rejects_malformed_part_fields(
    part: object,
    path: str,
    value_type: str,
) -> None:
    result = AgentToolResult(content=[part], details={})  # type: ignore[list-item]

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        result.for_presentation()

    assert exc_info.value.target == "transcript"
    assert exc_info.value.path == path
    assert exc_info.value.value_type == value_type


@pytest.mark.parametrize(
    "terminate",
    [1, object(), _HostileTruthValue()],
    ids=["int", "object", "hostile-bool"],
)
@pytest.mark.parametrize(
    ("project", "target"),
    [
        (AgentToolResult.for_presentation, "transcript"),
        (AgentToolResult.for_event, "event"),
    ],
)
def test_tool_output_projection_requires_exact_boolean_terminate(
    terminate: object,
    project,
    target: str,
) -> None:
    result = AgentToolResult(
        content=[TextPart(type="text", text="ok")],
        details={},
        terminate=terminate,  # type: ignore[arg-type]
    )

    with pytest.raises(ToolOutputProjectionError) as exc_info:
        project(result)

    assert exc_info.value.target == target
    assert exc_info.value.path == "tool_output.terminate"
    assert exc_info.value.value_type == type(terminate).__name__


def test_projection_error_metadata_is_safe_and_bounded() -> None:
    poisoned = ToolOutputProjectionError(
        "\ud800",  # type: ignore[arg-type]
        "\ud800",  # type: ignore[arg-type]
        path="\ud800",  # type: ignore[arg-type]
        value_type="\ud800",  # type: ignore[arg-type]
    )
    controlled = ToolOutputProjectionError(
        "event",
        "line one\nline two",
        path="tool_output.details\nforged",
        value_type="bad\x00type",
    )

    assert poisoned.target == "unknown"
    assert str(poisoned) == "Tool output projection failed"
    assert poisoned.path == "tool_output.details"
    assert poisoned.value_type == "unknown"
    assert str(controlled) == "line one\\u000aline two"
    assert controlled.path == "tool_output.details\\u000aforged"
    assert controlled.value_type == "bad\\u0000type"

    oversized = ToolOutputProjectionError(
        "event",
        "message",
        path="x" * 10_000,
        value_type="y" * 10_000,
    )
    assert len(oversized.path.encode("utf-8")) <= 512
    assert len(oversized.value_type.encode("utf-8")) <= 128
