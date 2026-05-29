from __future__ import annotations

import shlex
from pathlib import Path

from loushang.observability import ProblemRecord, get_problem_store


def debug_status_text(debug_path: Path, *, scopes: tuple[str, ...] = ("all",), cwd: str | None = None) -> str:
    lines = [
        "Debug logging enabled:",
        str(debug_path),
        str(debug_path.parent / "latest"),
        f"Scopes: {','.join(scopes)}",
    ]
    if cwd:
        lines.extend(["", "Diagnostics bundle:", debug_export_command(cwd=cwd, debug_path=debug_path)])
    recent = recent_debug_problem_lines(debug_path)
    if recent:
        lines.append("")
        lines.append("Recent debug problems:")
        lines.extend(recent)
    return "\n".join(lines)


def debug_export_command(*, cwd: str, debug_path: Path) -> str:
    root = Path(cwd).expanduser().resolve(strict=False)
    output_path = root / ".loushang" / "diagnostics" / "loushang-diag.zip"
    parts = [
        "loushang",
        "diag",
        "export",
        "--cwd",
        str(root),
        "--output",
        str(output_path),
        "--debug-file",
        str(debug_path),
    ]
    return " ".join(shlex.quote(part) for part in parts)


def recent_debug_problem_lines(debug_path: Path, *, limit: int = 8) -> list[str]:
    problem_lines = _recent_problem_store_lines(limit=limit)
    if problem_lines:
        return problem_lines
    try:
        lines = debug_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    summaries = [line for line in lines if _is_debug_problem_line(line)]
    return summaries[-limit:]


def _recent_problem_store_lines(*, limit: int) -> list[str]:
    try:
        records = get_problem_store().all()
    except Exception:
        return []
    return [_format_problem_summary(record) for record in records[-limit:]]


def _format_problem_summary(record: ProblemRecord) -> str:
    parts = [
        "PROBLEM",
        record.severity,
        record.code,
        f"source={record.source}" if record.source else "",
        record.message,
    ]
    return " ".join(part for part in parts if part)


def _is_debug_problem_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    tokens = stripped.split()
    return (
        " PROBLEM " in f" {stripped} "
        or "WARNING" in tokens
        or "ERROR" in tokens
    )


__all__ = ["debug_export_command", "debug_status_text", "recent_debug_problem_lines"]
