from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loushang.coding.worktree import CodingGitWorktreeLeasePort
from loushang.harness.multiagent import (
    AgentPath,
    AgentRef,
    WorkspaceLeaseRequest,
)
from loushang.harness.workspace.exec import ExecRequest, ExecResult, ExecService


class _GitBackend:
    def __init__(self, *, status: str = "") -> None:
        self.status = status
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, request, **_kwargs) -> ExecResult:
        self.commands.append(request.command)
        if "status" in request.command:
            return ExecResult(exit_code=0, stdout=self.status)
        return ExecResult(exit_code=0)


def _git_repo(path: Path) -> None:
    git_dir = path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")


def _request() -> WorkspaceLeaseRequest:
    return WorkspaceLeaseRequest(
        agent_ref=AgentRef(AgentPath.root().child("worker"), 1),
        agent_type="implementation_worker",
        mode="isolated",
    )


def test_unchanged_worktree_is_removed_with_its_temporary_branch(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_repo(repo)
    backend = _GitBackend()
    port = CodingGitWorktreeLeasePort(
        cwd=repo,
        exec_service=ExecService(backend=backend),
        uuid_factory=lambda: "lease-123",
    )

    async def scenario() -> None:
        lease = await port.acquire(_request())
        snapshot = await port.snapshot(lease)
        released = await port.release(lease)

        assert lease.workspace_ref == (
            "coding-worktree:loushang-agent/root-worker-1-lease123"
        )
        assert lease.execution_ref.endswith(
            ".loushang/worktrees/root-worker-1-lease123"
        )
        assert snapshot.changed is False
        assert released.workspace_ref is None
        with pytest.raises(RuntimeError, match="unknown or released"):
            await port.release(lease)

    asyncio.run(scenario())

    assert [command[2] for command in backend.commands] == [
        "worktree",
        "status",
        "status",
        "worktree",
        "branch",
    ]
    assert backend.commands[-1][-2:] == (
        "-D",
        "loushang-agent/root-worker-1-lease123",
    )


def test_changed_worktree_is_retained_and_reported(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_repo(repo)
    backend = _GitBackend(status=" M src/example.py\n")
    port = CodingGitWorktreeLeasePort(
        cwd=repo,
        exec_service=ExecService(backend=backend),
        uuid_factory=lambda: "changed",
    )

    async def scenario() -> None:
        lease = await port.acquire(_request())
        snapshot = await port.snapshot(lease)
        released = await port.release(lease)

        assert snapshot.changed is True
        assert snapshot.change_set_ref == (
            "git-branch:loushang-agent/root-worker-1-changed"
        )
        assert released.retained is True
        assert released.workspace_ref == lease.workspace_ref

    asyncio.run(scenario())

    assert all(command[2] != "branch" for command in backend.commands)


def test_real_git_worktree_round_trip_releases_an_unchanged_lease(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        service = ExecService()

        async def git(*args: str) -> ExecResult:
            result = await service.execute(
                ExecRequest(command=("git", *args), cwd=str(repo))
            )
            assert result.exit_code == 0, result.stderr
            return result

        await git("init")
        await git("config", "user.email", "multiagent@example.invalid")
        await git("config", "user.name", "Multi Agent Test")
        (repo / "README.md").write_text("test\n", encoding="utf-8")
        await git("add", "README.md")
        await git("commit", "-m", "initial")

        port = CodingGitWorktreeLeasePort(
            cwd=repo,
            exec_service=service,
            uuid_factory=lambda: "actual",
        )
        lease = await port.acquire(_request())
        worktree = Path(lease.execution_ref)
        assert worktree.is_dir()
        assert (worktree / "README.md").read_text(encoding="utf-8") == "test\n"

        released = await port.release(lease)
        assert released.workspace_ref is None
        assert worktree.exists() is False
        branches = await git(
            "branch",
            "--list",
            "loushang-agent/root-worker-1-actual",
        )
        assert branches.stdout.strip() == ""

    asyncio.run(scenario())


def test_real_git_worktree_retains_a_changed_lease_and_branch(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        service = ExecService()

        async def git(*args: str) -> ExecResult:
            result = await service.execute(
                ExecRequest(command=("git", *args), cwd=str(repo))
            )
            assert result.exit_code == 0, result.stderr
            return result

        await git("init")
        await git("config", "user.email", "multiagent@example.invalid")
        await git("config", "user.name", "Multi Agent Test")
        (repo / "README.md").write_text("test\n", encoding="utf-8")
        await git("add", "README.md")
        await git("commit", "-m", "initial")

        port = CodingGitWorktreeLeasePort(
            cwd=repo,
            exec_service=service,
            uuid_factory=lambda: "retained",
        )
        lease = await port.acquire(_request())
        worktree = Path(lease.execution_ref)
        (worktree / "result.txt").write_text("agent output\n", encoding="utf-8")

        snapshot = await port.snapshot(lease)
        released = await port.release(lease)

        assert snapshot.changed is True
        assert released.retained is True
        assert released.workspace_ref == lease.workspace_ref
        assert released.change_set_ref == (
            "git-branch:loushang-agent/root-worker-1-retained"
        )
        assert worktree.is_dir()
        branches = await git(
            "branch",
            "--list",
            "loushang-agent/root-worker-1-retained",
        )
        assert "loushang-agent/root-worker-1-retained" in branches.stdout

        await git("worktree", "remove", "--force", str(worktree))
        await git("branch", "-D", "loushang-agent/root-worker-1-retained")

    asyncio.run(scenario())
