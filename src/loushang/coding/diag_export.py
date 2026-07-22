from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from loushang.harness.diagnostics.export import (
    DiagnosticExportArtifact,
    collect_diagnostics,
    export_diagnostics_archive,
    path_exists,
    resolve_export_output_path,
    utc_now,
)
from loushang.harness.diagnostics.serialization import serialize_diagnostic

DEFAULT_DIAGNOSTICS_LIMIT = 50


def export_diagnostics_bundle(
    *,
    project_root: str | Path,
    session_dir: str | Path,
    output: str | Path | None = None,
    diagnostics_service: Any | None = None,
    debug_latest_path: str | Path | None = None,
    trace_latest_path: str | Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> Path:
    root = Path(project_root).expanduser().resolve()
    sessions = Path(session_dir).expanduser().resolve()
    generated_at = (now or utc_now)()
    bundle_path = resolve_export_output_path(root, output, generated_at)
    diagnostics = collect_diagnostics(
        diagnostics_service,
        serializer=serialize_diagnostic,
        limit=DEFAULT_DIAGNOSTICS_LIMIT,
    )

    debug_latest = (
        _default_debug_latest()
        if debug_latest_path is None
        else Path(debug_latest_path).expanduser()
    )
    trace_latest = (
        _default_trace_latest()
        if trace_latest_path is None
        else Path(trace_latest_path).expanduser()
    )
    session_latest = sessions / "latest.jsonl"

    return export_diagnostics_archive(
        output_path=bundle_path,
        readme=_readme(),
        manifest=_manifest(
            project_root=root,
            session_dir=sessions,
            generated_at=generated_at,
            debug_latest=debug_latest,
            trace_latest=trace_latest,
            session_latest=session_latest,
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
        artifacts=(
            DiagnosticExportArtifact("debug/latest.log", debug_latest),
            DiagnosticExportArtifact("traces/latest.jsonl", trace_latest),
            DiagnosticExportArtifact("sessions/latest.jsonl", session_latest),
        ),
    )


def _manifest(
    *,
    project_root: Path,
    session_dir: Path,
    generated_at: datetime,
    debug_latest: Path,
    trace_latest: Path,
    session_latest: Path,
    diagnostics: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "cwd": str(project_root),
        "sessionDir": str(session_dir),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "loushangVersion": _package_version(),
        "included": {
            "debugLatest": path_exists(debug_latest),
            "traceLatest": path_exists(trace_latest),
            "sessionLatest": path_exists(session_latest),
            "diagnostics": bool(diagnostics),
        },
    }


def _default_debug_latest() -> Path:
    return Path.home() / ".loushang" / "debug" / "latest"


def _default_trace_latest() -> Path:
    return Path.home() / ".loushang" / "traces" / "latest"


def _package_version() -> str | None:
    try:
        return package_version("loushang")
    except PackageNotFoundError:
        return None


def _readme() -> str:
    return (
        "Loushang diagnostics bundle\n"
        "\n"
        "This archive contains recent local debugging artifacts for troubleshooting.\n"
        "It may include debug logs, structured trace events, the latest session JSONL,\n"
        "and a diagnostics summary. Common bearer tokens and API key fields are redacted\n"
        "on export, but review the archive before sharing it outside your machine.\n"
    )
