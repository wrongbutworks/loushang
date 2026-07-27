"""Coding's managed Git-worktree implementation of workspace leases."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from loushang.harness.multiagent import (
    WorkspaceLease,
    WorkspaceLeasePort,
    WorkspaceLeaseRequest,
    WorkspaceLeaseSnapshot,
)
from loushang.harness.workspace.exec import ExecRequest, ExecService
from loushang.harness.workspace.git import find_git_paths

_UuidFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class _GitWorktreeState:
    repo_dir: Path
    path: Path
    branch: str


class CodingGitWorktreeLeasePort(WorkspaceLeasePort):
    """Allocate isolated Coding children from the current committed HEAD."""

    def __init__(
        self,
        *,
        cwd: str | Path,
        exec_service: ExecService | None = None,
        lease_root: str | Path | None = None,
        uuid_factory: _UuidFactory | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        resolved_cwd = Path(cwd).expanduser().resolve()
        if not resolved_cwd.is_dir():
            raise NotADirectoryError(20, "Not a directory", str(resolved_cwd))
        if timeout_seconds <= 0:
            raise ValueError("worktree timeout_seconds must be positive")
        self._cwd = resolved_cwd
        self._exec = exec_service or ExecService()
        self._lease_root = (
            Path(lease_root).expanduser().resolve()
            if lease_root is not None
            else resolved_cwd / ".loushang" / "worktrees"
        )
        self._uuid_factory = uuid_factory or (lambda: uuid4().hex[:10])
        self._timeout_seconds = timeout_seconds
        self._states: dict[str, _GitWorktreeState] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, request: WorkspaceLeaseRequest) -> WorkspaceLease:
        if request.mode != "isolated":
            raise ValueError("Coding worktree leases require isolated mode")
        git_paths = find_git_paths(self._cwd)
        if git_paths is None:
            raise RuntimeError(
                f"isolated Coding agents require a Git repository: {self._cwd}"
            )
        slug = _lease_slug(request, self._uuid_factory())
        branch = f"loushang-agent/{slug}"
        path = (self._lease_root / slug).resolve()
        try:
            path.relative_to(self._lease_root.resolve())
        except ValueError as error:  # pragma: no cover - slug validation is structural
            raise RuntimeError("allocated worktree escaped its managed root") from error
        workspace_ref = f"coding-worktree:{branch}"
        state = _GitWorktreeState(
            repo_dir=git_paths.repo_dir,
            path=path,
            branch=branch,
        )
        async with self._lock:
            if workspace_ref in self._states:
                raise RuntimeError(f"duplicate worktree lease: {workspace_ref}")
            self._lease_root.mkdir(parents=True, exist_ok=True)
            result = await self._git(
                state.repo_dir,
                "worktree",
                "add",
                "-b",
                state.branch,
                str(state.path),
                "HEAD",
            )
            if result.exit_code != 0:
                await self._cleanup_failed_acquire(state)
                raise RuntimeError(
                    "failed to create Coding worktree: "
                    + _command_error_text(result.stderr, result.stdout)
                )
            self._states[workspace_ref] = state
        return WorkspaceLease(
            workspace_ref=workspace_ref,
            execution_ref=str(path),
        )

    async def snapshot(self, lease: WorkspaceLease) -> WorkspaceLeaseSnapshot:
        async with self._lock:
            state = self._require_state(lease)
            result = await self._git(
                state.path,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            if result.exit_code != 0:
                raise RuntimeError(
                    "failed to inspect Coding worktree: "
                    + _command_error_text(result.stderr, result.stdout)
                )
            changed = bool(result.stdout.strip())
            return WorkspaceLeaseSnapshot(
                workspace_ref=lease.workspace_ref,
                change_set_ref=(f"git-branch:{state.branch}" if changed else None),
                changed=changed,
            )

    async def release(self, lease: WorkspaceLease) -> WorkspaceLeaseSnapshot:
        async with self._lock:
            state = self._require_state(lease)
            status = await self._git(
                state.path,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            if status.exit_code != 0:
                raise RuntimeError(
                    "failed to inspect Coding worktree before release: "
                    + _command_error_text(status.stderr, status.stdout)
                )
            changed = bool(status.stdout.strip())
            if changed:
                self._states.pop(lease.workspace_ref, None)
                return WorkspaceLeaseSnapshot(
                    workspace_ref=lease.workspace_ref,
                    change_set_ref=f"git-branch:{state.branch}",
                    changed=True,
                    retained=True,
                )
            removed = await self._git(
                state.repo_dir,
                "worktree",
                "remove",
                "--force",
                str(state.path),
            )
            if removed.exit_code != 0:
                raise RuntimeError(
                    "failed to release unchanged Coding worktree: "
                    + _command_error_text(removed.stderr, removed.stdout)
                )
            deleted = await self._git(
                state.repo_dir,
                "branch",
                "-D",
                state.branch,
            )
            if deleted.exit_code != 0:
                raise RuntimeError(
                    "released worktree but failed to delete its temporary branch: "
                    + _command_error_text(deleted.stderr, deleted.stdout)
                )
            self._states.pop(lease.workspace_ref, None)
            return WorkspaceLeaseSnapshot(workspace_ref=None)

    def _require_state(self, lease: WorkspaceLease) -> _GitWorktreeState:
        state = self._states.get(lease.workspace_ref)
        if state is None or str(state.path) != lease.execution_ref:
            raise RuntimeError(
                f"unknown or released worktree lease: {lease.workspace_ref}"
            )
        return state

    async def _cleanup_failed_acquire(self, state: _GitWorktreeState) -> None:
        await self._git(
            state.repo_dir,
            "worktree",
            "remove",
            "--force",
            str(state.path),
        )
        await self._git(state.repo_dir, "branch", "-D", state.branch)

    async def _git(self, cwd: Path, *args: str):
        return await self._exec.execute(
            ExecRequest(
                command=("git", "--no-optional-locks", *args),
                cwd=str(cwd),
                timeout_seconds=self._timeout_seconds,
            )
        )


def _lease_slug(request: WorkspaceLeaseRequest, nonce: str) -> str:
    normalized_nonce = "".join(
        character for character in nonce.lower() if character.isalnum()
    )
    if not normalized_nonce:
        raise ValueError("worktree nonce must contain letters or digits")
    path = "-".join(request.agent_ref.path.parts)
    return f"{path}-{request.agent_ref.incarnation}-{normalized_nonce}"[:100]


def _command_error_text(stderr: str, stdout: str) -> str:
    return stderr.strip() or stdout.strip() or "Git command failed"


__all__ = ["CodingGitWorktreeLeasePort"]
