#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

PLAN_PATH = Path("docs/internals/plans/2026-06-20-loushang-ai-quality-hardening-execution-plan.md")
PLAN_ID_RE = re.compile(r"^Plan-ID:\s*(AIQ-\d{3})\s*$", re.MULTILINE)

Status = Literal["complete", "pending"]


@dataclass(frozen=True)
class PlanItem:
    plan_id: str
    commit_message: str
    description: str
    status: Status
    commit: str | None = None
    actual_subject: str | None = None
    subject_matches_plan: bool = False


@dataclass(frozen=True)
class PlanStatus:
    plan_file: str
    total: int
    complete: int
    pending: int
    items: list[PlanItem]


def repo_root() -> Path:
    output = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    )
    return Path(output.strip())


def load_plan_items(plan_file: Path) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    for line in plan_file.read_text(encoding="utf-8").splitlines():
        columns = split_markdown_table_row(line)
        if len(columns) < 3 or not re.fullmatch(r"AIQ-\d{3}", columns[0]):
            continue
        plan_id = columns[0]
        commit_message = columns[1].strip()
        if commit_message.startswith("`") and commit_message.endswith("`"):
            commit_message = commit_message[1:-1]
        items.append((plan_id, commit_message, columns[2].strip()))
    return items


def split_markdown_table_row(line: str) -> list[str]:
    if not line.startswith("|"):
        return []
    columns: list[str] = []
    current: list[str] = []
    in_code = False
    for char in line.strip():
        if char == "`":
            in_code = not in_code
            current.append(char)
            continue
        if char == "|" and not in_code:
            columns.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    columns.append("".join(current).strip())
    return [column for column in columns if column]


@dataclass(frozen=True)
class CommitMatch:
    commit: str
    subject: str


def committed_plan_ids(root: Path) -> dict[str, CommitMatch]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "log", "--format=%H%x00%s%x00%B%x1e"],
        text=True,
    )
    commits: dict[str, CommitMatch] = {}
    for record in output.split("\x1e"):
        if not record.strip():
            continue
        commit, subject, body = record.split("\x00", 2)
        commit = commit.strip()
        for plan_id in PLAN_ID_RE.findall(body):
            commits.setdefault(plan_id, CommitMatch(commit=commit, subject=subject.strip()))
    return commits


def collect_status(root: Path | None = None, plan_path: Path = PLAN_PATH) -> PlanStatus:
    root = root or repo_root()
    plan_file = plan_path if plan_path.is_absolute() else root / plan_path
    plan_items = load_plan_items(plan_file)
    commits = committed_plan_ids(root)
    items: list[PlanItem] = []
    for plan_id, commit_message, description in plan_items:
        match = commits.get(plan_id)
        items.append(
            PlanItem(
                plan_id=plan_id,
                commit_message=commit_message,
                description=description,
                status="complete" if match is not None else "pending",
                commit=match.commit if match is not None else None,
                actual_subject=match.subject if match is not None else None,
                subject_matches_plan=(
                    match.subject == commit_message if match is not None else False
                ),
            )
        )
    complete = sum(1 for item in items if item.status == "complete")
    return PlanStatus(
        plan_file=str(plan_file.relative_to(root)),
        total=len(items),
        complete=complete,
        pending=len(items) - complete,
        items=items,
    )


def format_text(status: PlanStatus) -> str:
    lines = [
        f"Plan file: {status.plan_file}",
        f"Total: {status.total}",
        f"Complete: {status.complete}",
        f"Pending: {status.pending}",
        "",
        "Completed items:",
    ]
    completed = [item for item in status.items if item.status == "complete"]
    if completed:
        lines.extend(
            f"- {item.plan_id} {item.commit[:12] if item.commit else ''} "
            f"{item.actual_subject or item.commit_message}"
            for item in completed
        )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Next pending:")
    next_pending = next((item for item in status.items if item.status == "pending"), None)
    if next_pending is None:
        lines.append("- none")
    else:
        lines.append(f"- {next_pending.plan_id} {next_pending.commit_message}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report AIQ plan progress from local commits.")
    parser.add_argument(
        "--plan-file",
        default=str(PLAN_PATH),
        help="Path to the AIQ execution plan, relative to the git root by default.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    root = repo_root()
    status = collect_status(root=root, plan_path=Path(args.plan_file))
    if args.json:
        print(json.dumps(asdict(status), indent=2, sort_keys=True))
    else:
        print(format_text(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
