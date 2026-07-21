from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from loushang.coding.diagnostics.serialization import serialize_diagnostic
from loushang.harness.diagnostics.export import (
    DiagnosticExportArtifact,
    export_diagnostics_archive,
)

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
    generated_at = (now or _utc_now)()
    bundle_path = _resolve_output_path(root, output, generated_at)
    diagnostics = _collect_diagnostics(diagnostics_service)

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


def _resolve_output_path(
    root: Path, output: str | Path | None, generated_at: datetime
) -> Path:
    if output is not None:
        return Path(output).expanduser().resolve()
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    return root / ".loushang" / "diagnostics" / f"loushang-diag-{timestamp}.zip"


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
            "debugLatest": _path_exists(debug_latest),
            "traceLatest": _path_exists(trace_latest),
            "sessionLatest": _path_exists(session_latest),
            "diagnostics": bool(diagnostics),
        },
    }


def _collect_diagnostics(diagnostics_service: Any | None) -> list[dict[str, object]]:
    getter = getattr(diagnostics_service, "get_last_diagnostics", None)
    if not callable(getter):
        return []
    try:
        records = getter(limit=DEFAULT_DIAGNOSTICS_LIMIT)
    except TypeError:
        records = getter(DEFAULT_DIAGNOSTICS_LIMIT)
    except Exception:
        return []
    if not isinstance(records, list | tuple):
        return []
    normalized: list[dict[str, object]] = []
    for record in records:
        try:
            normalized.append(serialize_diagnostic(record))
        except Exception:
            # Diagnostics archives are shareable artifacts. Never serialize an
            # arbitrary record representation after the product projection fails.
            continue
    return normalized


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _default_debug_latest() -> Path:
    return Path.home() / ".loushang" / "debug" / "latest"


def _default_trace_latest() -> Path:
    return Path.home() / ".loushang" / "traces" / "latest"


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
