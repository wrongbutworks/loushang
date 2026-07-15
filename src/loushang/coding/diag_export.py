from __future__ import annotations

import json
import platform
import re
import sys
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from loushang.coding.diagnostics.serialization import serialize_diagnostic

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

    debug_latest = _default_debug_latest() if debug_latest_path is None else Path(debug_latest_path).expanduser()
    trace_latest = _default_trace_latest() if trace_latest_path is None else Path(trace_latest_path).expanduser()
    session_latest = sessions / "latest.jsonl"

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = _manifest(
            project_root=root,
            session_dir=sessions,
            generated_at=generated_at,
            debug_latest=debug_latest,
            trace_latest=trace_latest,
            session_latest=session_latest,
            diagnostics=diagnostics,
        )
        archive.writestr("README.txt", _readme())
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        archive.writestr("diagnostics.json", json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _write_latest_file(archive, "debug/latest.log", debug_latest)
        _write_latest_file(archive, "traces/latest.jsonl", trace_latest)
        _write_latest_file(archive, "sessions/latest.jsonl", session_latest)
    return bundle_path


def _resolve_output_path(root: Path, output: str | Path | None, generated_at: datetime) -> Path:
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
        "generatedAt": generated_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
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
            normalized.append({"repr": repr(record)})
    return normalized


def _write_latest_file(archive: zipfile.ZipFile, arcname: str, path: Path) -> None:
    if not _path_exists(path):
        return
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    archive.writestr(arcname, _redact_text(content))


def _redact_text(content: str) -> str:
    redacted = content
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


_REDACTION_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;}\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)(\"?(?:api[_-]?key|token|secret)\"?\s*[:=]\s*\"?)[^\",\s}]+(\"?)"),
        r"\1[REDACTED]\2",
    ),
)


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
