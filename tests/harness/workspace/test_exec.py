from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loushang.agent import AbortController
from loushang.harness.workspace.exec import (
    ExecOutputChunk,
    ExecRequest,
    ExecResult,
    ExecService,
    materialize_exec_request,
)


def test_exec_records_normalize_sequences_and_validate_rolling_limit() -> None:
    request = ExecRequest(
        command=["git", "status"],
        env=[["A", "1"], ("B", "2")],
    )
    result = ExecResult(
        exit_code=0,
        stdout_chunks=["out\n"],
        output_chunks=[ExecOutputChunk(stream="stdout", text="out\n")],
    )

    assert request.command == ("git", "status")
    assert request.env == (("A", "1"), ("B", "2"))
    assert result.stdout_chunks == ("out\n",)
    assert result.output_chunks == (ExecOutputChunk(stream="stdout", text="out\n"),)

    with pytest.raises(ValueError, match="rolling_max_bytes must be >= 1"):
        ExecRequest(command=["true"], rolling_max_bytes=0)


def test_exec_request_materialization_preserves_abi_and_freezes_process_state(
    tmp_path: Path,
) -> None:
    request = ExecRequest(
        ("printf", "ok"),
        None,
        (("B", "override"),),
        5,
    )
    inherited = {"A": "one", "B": "base"}

    materialized = materialize_exec_request(
        request,
        environ=inherited,
        cwd=str(tmp_path),
    )
    inherited["A"] = "changed"

    assert request.timeout_seconds == 5
    assert request.env == (("B", "override"),)
    assert request.effective_environment is None
    assert materialized.cwd == str(tmp_path)
    assert materialized.env == (("B", "override"),)
    assert dict(materialized.effective_environment or ()) == {
        "A": "one",
        "B": "override",
    }
    assert (
        materialize_exec_request(materialized, environ={"A": "later"}) is materialized
    )


def test_exec_request_materialization_preserves_explicit_empty_cwd() -> None:
    materialized = materialize_exec_request(
        ExecRequest(command=("true",), cwd=""),
        environ={},
    )

    assert materialized.cwd == ""


def test_exec_service_delegates_to_custom_backend_and_streams_updates(
    tmp_path: Path,
) -> None:
    seen: list[tuple[tuple[str, ...], str | None, object | None]] = []
    updates: list[ExecOutputChunk] = []

    async def backend(request, *, signal=None, on_update=None):
        seen.append((request.command, request.cwd, signal))
        chunk = ExecOutputChunk(stream="stdout", text="remote\n")
        if on_update is not None:
            await on_update(chunk)
        return ExecResult(exit_code=0, stdout="remote\n", output_chunks=(chunk,))

    async def scenario() -> None:
        signal = object()
        service = ExecService(backend=backend)

        async def on_update(chunk: ExecOutputChunk) -> None:
            updates.append(chunk)

        result = await service.execute(
            ExecRequest(command=["deploy"], cwd=str(tmp_path)),
            signal=signal,
            on_update=on_update,
        )

        assert result.stdout == "remote\n"
        assert seen == [(("deploy",), str(tmp_path), signal)]

    asyncio.run(scenario())
    assert updates == [ExecOutputChunk(stream="stdout", text="remote\n")]


def test_exec_service_custom_backend_receives_one_frozen_process_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[ExecRequest] = []
    original_cwd = tmp_path / "original"
    changed_cwd = tmp_path / "changed"
    original_cwd.mkdir()
    changed_cwd.mkdir()
    monkeypatch.chdir(original_cwd)
    monkeypatch.setenv("HARNESS_EXEC_SNAPSHOT", "original")

    async def backend(request, **kwargs):
        del kwargs
        captured.append(request)
        monkeypatch.chdir(changed_cwd)
        monkeypatch.setenv("HARNESS_EXEC_SNAPSHOT", "changed")
        await asyncio.sleep(0)
        return ExecResult(exit_code=0)

    asyncio.run(
        ExecService(backend=backend).execute(
            ExecRequest(
                command=["remote"],
                env=(("HARNESS_EXEC_OVERRIDE", "caller"),),
            )
        )
    )

    request = captured[0]
    assert request.cwd == str(original_cwd)
    assert request.env == (("HARNESS_EXEC_OVERRIDE", "caller"),)
    assert (
        dict(request.effective_environment or ())["HARNESS_EXEC_SNAPSHOT"] == "original"
    )
    assert (
        dict(request.effective_environment or ())["HARNESS_EXEC_OVERRIDE"] == "caller"
    )


def test_exec_service_rejects_invalid_backend_result() -> None:
    async def backend(request, *, signal=None, on_update=None):
        del request, signal, on_update
        return object()

    async def scenario() -> None:
        with pytest.raises(TypeError, match="exec backend must return ExecResult"):
            await ExecService(backend=backend).execute(ExecRequest(command=["invalid"]))

    asyncio.run(scenario())


def test_exec_service_runs_subprocess_and_preserves_per_stream_order(
    tmp_path: Path,
) -> None:
    updates: list[tuple[str, str]] = []

    async def scenario() -> None:
        async def on_update(chunk: ExecOutputChunk) -> None:
            updates.append((chunk.stream, chunk.text))

        result = await ExecService().execute(
            ExecRequest(
                command=[
                    "/usr/bin/env",
                    "python3",
                    "-c",
                    (
                        "import sys, time; "
                        "sys.stdout.write('out1\\n'); sys.stdout.flush(); "
                        "time.sleep(0.05); "
                        "sys.stderr.write('err1\\n'); sys.stderr.flush(); "
                        "time.sleep(0.05); "
                        "sys.stdout.write('out2\\n'); sys.stdout.flush()"
                    ),
                ],
                cwd=str(tmp_path),
            ),
            on_update=on_update,
        )

        assert result.exit_code == 0
        assert result.stdout == "out1\nout2\n"
        assert result.stderr == "err1\n"
        observed = tuple(
            (chunk.stream, chunk.text) for chunk in result.output_chunks
        )
        # stdout and stderr are independent pipes. Preserve the order within each
        # stream, while treating their merged order as the host's observation order.
        assert tuple(text for stream, text in observed if stream == "stdout") == (
            "out1\n",
            "out2\n",
        )
        assert tuple(text for stream, text in observed if stream == "stderr") == (
            "err1\n",
        )
        assert updates == list(observed)

    asyncio.run(scenario())


def test_exec_service_accepts_a_process_that_exits_without_reading_stdin(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        result = await ExecService().execute(
            ExecRequest(
                command=["/bin/true"],
                cwd=str(tmp_path),
                stdin="ignored\n" * 131_072,
            )
        )

        assert result.exit_code == 0

    asyncio.run(scenario())


def test_exec_service_builds_tail_preview_and_full_output_artifact(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        result = await ExecService().execute(
            ExecRequest(
                command=[
                    "/usr/bin/env",
                    "python3",
                    "-c",
                    "print('a'); print('b'); print('c'); print('d')",
                ],
                cwd=str(tmp_path),
                preview_max_lines=2,
                preview_max_bytes=1024,
                artifact_dir=str(tmp_path),
            )
        )

        assert result.stdout_preview == "c\nd\n"
        assert result.stdout_truncated is True
        assert result.stdout_truncated_by == "lines"
        assert result.stdout_artifact_path is not None
        assert (
            Path(result.stdout_artifact_path).read_text(encoding="utf-8")
            == "a\nb\nc\nd\n"
        )

    asyncio.run(scenario())


def test_exec_service_rolls_capture_without_losing_artifact(tmp_path: Path) -> None:
    full_output = "".join(f"line-{index:04d}\n" for index in range(400))

    async def scenario() -> None:
        result = await ExecService().execute(
            ExecRequest(
                command=[
                    "/usr/bin/env",
                    "python3",
                    "-c",
                    "for i in range(400): print(f'line-{i:04d}')",
                ],
                cwd=str(tmp_path),
                preview_max_lines=2,
                preview_max_bytes=1024,
                artifact_dir=str(tmp_path),
                capture_full_output=False,
                rolling_max_bytes=512,
            )
        )

        assert result.stdout != full_output
        assert len(result.stdout.encode("utf-8")) <= 512
        assert result.stdout_preview == "line-0398\nline-0399\n"
        assert result.stdout_artifact_path is not None
        assert (
            Path(result.stdout_artifact_path).read_text(encoding="utf-8") == full_output
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("capture_full_output", [True, False])
def test_exec_service_discards_unretained_output_artifacts(
    tmp_path: Path,
    capture_full_output: bool,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()

    async def scenario() -> None:
        result = await ExecService().execute(
            ExecRequest(
                command=[
                    "/usr/bin/env",
                    "python3",
                    "-c",
                    "for i in range(400): print(f'line-{i:04d}')",
                ],
                cwd=str(tmp_path),
                preview_max_lines=2,
                preview_max_bytes=1024,
                artifact_dir=str(artifact_dir),
                capture_full_output=capture_full_output,
                retain_output_artifacts=False,
                rolling_max_bytes=512,
            )
        )

        assert result.stdout_preview == "line-0398\nline-0399\n"
        assert result.stdout_truncated is True
        assert result.stdout_artifact_path is None
        assert result.stderr_artifact_path is None
        assert list(artifact_dir.iterdir()) == []

    asyncio.run(scenario())


def test_exec_service_marks_timeout_and_cancellation(tmp_path: Path) -> None:
    async def scenario() -> None:
        timed_out = await ExecService().execute(
            ExecRequest(
                command=["/bin/sh", "-c", "printf timeout; sleep 1"],
                cwd=str(tmp_path),
                timeout_seconds=0.05,
            )
        )
        assert timed_out.timed_out is True
        assert timed_out.cancelled is False
        assert timed_out.stdout == "timeout"

        controller = AbortController()

        async def abort_soon() -> None:
            await asyncio.sleep(0.05)
            controller.abort()

        asyncio.create_task(abort_soon())
        cancelled = await ExecService().execute(
            ExecRequest(
                command=["/bin/sh", "-c", "printf cancelled; sleep 1"],
                cwd=str(tmp_path),
            ),
            signal=controller.signal,
        )
        assert cancelled.cancelled is True
        assert cancelled.timed_out is False
        assert cancelled.stdout == "cancelled"

    asyncio.run(scenario())
