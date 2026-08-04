from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from loushang.coding.lsp import (
    CodingLspBinding,
    LspCatalog,
    LspClient,
    LspInvalidInputError,
    LspProtocolError,
    LspSelector,
    LspServerDefinition,
    ProcessExit,
    ProcessLaunchRequest,
    ProcessStderrTail,
    create_inspect_symbol_tool_definition,
)
from loushang.harness.tools import ToolContext
from loushang.harness.tools.workspace.wrapper import wrap_tool_definition


def _frame(message: Mapping[str, object]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


async def _wait_for_method(
    server: FakeLspServer,
    method: str,
    *,
    count: int = 1,
) -> None:
    for _ in range(100):
        if server.methods().count(method) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"fake server did not receive {method!r}")


class _FrameReader:
    def __init__(self, queue: asyncio.Queue[bytes | None]) -> None:
        self._queue = queue
        self._buffer = bytearray()

    async def read(self) -> dict[str, object] | None:
        while b"\r\n\r\n" not in self._buffer:
            if not await self._read_chunk():
                return None
        raw_header, _, remainder = self._buffer.partition(b"\r\n\r\n")
        self._buffer = bytearray(remainder)
        length = None
        for line in raw_header.split(b"\r\n"):
            name, _, value = line.partition(b":")
            if name.lower() == b"content-length":
                length = int(value.strip())
        assert length is not None
        while len(self._buffer) < length:
            if not await self._read_chunk():
                return None
        body = bytes(self._buffer[:length])
        del self._buffer[:length]
        value = json.loads(body)
        assert isinstance(value, dict)
        return value

    async def _read_chunk(self) -> bool:
        chunk = await self._queue.get()
        if chunk is None:
            return False
        self._buffer.extend(chunk)
        return True


class FakeLspServer:
    def __init__(
        self,
        *,
        definition_result: object,
        initialize_gate: asyncio.Event | None,
        definition_gate: asyncio.Event | None,
        shutdown_gate: asyncio.Event | None,
        position_encoding: str,
        crash_on_definition: bool,
        ignore_exit: bool,
    ) -> None:
        self.stdin: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.stdout: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.definition_result = definition_result
        self.initialize_gate = initialize_gate
        self.definition_gate = definition_gate
        self.shutdown_gate = shutdown_gate
        self.position_encoding = position_encoding
        self.crash_on_definition = crash_on_definition
        self.ignore_exit = ignore_exit
        self.messages: list[dict[str, object]] = []
        self._response_tasks: set[asyncio.Task[None]] = set()
        self.task = asyncio.create_task(self._serve(), name="fake-lsp-server")

    async def _serve(self) -> None:
        reader = _FrameReader(self.stdin)
        try:
            while (message := await reader.read()) is not None:
                self.messages.append(message)
                method = message.get("method")
                request_id = message.get("id")
                if method == "initialize":
                    if self.initialize_gate is not None:
                        await self.initialize_gate.wait()
                    response = _frame(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "capabilities": {
                                    "positionEncoding": self.position_encoding
                                }
                            },
                        }
                    )
                    diagnostic = _frame(
                        {
                            "jsonrpc": "2.0",
                            "method": "textDocument/publishDiagnostics",
                            "params": {
                                "uri": "file:///discarded.py",
                                "diagnostics": [],
                            },
                        }
                    )
                    configuration_request = _frame(
                        {
                            "jsonrpc": "2.0",
                            "id": "server-config-1",
                            "method": "workspace/configuration",
                            "params": {"items": [{"section": "python"}]},
                        }
                    )
                    # Exercise a response split across chunks and a coalesced next frame.
                    await self.stdout.put(response[:11])
                    await self.stdout.put(
                        response[11:] + diagnostic + configuration_request
                    )
                elif method == "textDocument/definition":
                    if self.crash_on_definition:
                        return
                    self._schedule_response(
                        self.definition_gate,
                        _frame(
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "result": self.definition_result,
                            }
                        ),
                    )
                elif method == "shutdown":
                    self._schedule_response(
                        self.shutdown_gate,
                        _frame({"jsonrpc": "2.0", "id": request_id, "result": None}),
                    )
                elif method == "exit" and not self.ignore_exit:
                    break
        finally:
            response_tasks = tuple(self._response_tasks)
            for task in response_tasks:
                task.cancel()
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)
            await self.stdout.put(None)

    def _schedule_response(
        self,
        gate: asyncio.Event | None,
        response: bytes,
    ) -> None:
        async def send() -> None:
            if gate is not None:
                await gate.wait()
            await self.stdout.put(response)

        task = asyncio.create_task(send(), name="fake-lsp-response")
        self._response_tasks.add(task)
        task.add_done_callback(self._response_tasks.discard)

    def methods(self) -> list[str]:
        return [
            method
            for message in self.messages
            if isinstance((method := message.get("method")), str)
        ]


class FakeProcessHandle:
    def __init__(self, server: FakeLspServer) -> None:
        self.server = server
        self.close_calls = 0
        self.terminate_calls = 0
        self.wait_calls = 0

    async def read_stdout(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        chunk = await self.server.stdout.get()
        return b"" if chunk is None else chunk

    async def write_stdin(self, data: bytes) -> None:
        await self.server.stdin.put(data)

    async def close_stdin(self) -> None:
        await self.server.stdin.put(None)

    async def wait(self) -> ProcessExit:
        self.wait_calls += 1
        await self.server.task
        return ProcessExit(return_code=0)

    async def terminate(self) -> ProcessExit:
        self.terminate_calls += 1
        if not self.server.task.done():
            await self.server.stdin.put(None)
        await self.server.task
        return ProcessExit(return_code=-15)

    async def close(self) -> None:
        self.close_calls += 1
        if not self.server.task.done():
            await self.server.stdin.put(None)
        await self.server.task

    def stderr_tail(self) -> ProcessStderrTail:
        return ProcessStderrTail()


class FakeLauncher:
    def __init__(
        self,
        *,
        definition_result: object,
        initialize_gate: asyncio.Event | None = None,
        definition_gate: asyncio.Event | None = None,
        shutdown_gate: asyncio.Event | None = None,
        position_encoding: str = "utf-16",
        crash_first_definition: bool = False,
        ignore_exit: bool = False,
    ) -> None:
        self.definition_result = definition_result
        self.initialize_gate = initialize_gate
        self.definition_gate = definition_gate
        self.shutdown_gate = shutdown_gate
        self.position_encoding = position_encoding
        self.crash_first_definition = crash_first_definition
        self.ignore_exit = ignore_exit
        self.requests: list[ProcessLaunchRequest] = []
        self.correlation_ids: list[str] = []
        self.handles: list[FakeProcessHandle] = []

    async def start(
        self,
        request: ProcessLaunchRequest,
        *,
        correlation_id: str,
        signal: object | None = None,
    ) -> FakeProcessHandle:
        del signal
        self.requests.append(request)
        self.correlation_ids.append(correlation_id)
        server = FakeLspServer(
            definition_result=self.definition_result,
            initialize_gate=self.initialize_gate,
            definition_gate=self.definition_gate,
            shutdown_gate=self.shutdown_gate,
            position_encoding=self.position_encoding,
            crash_on_definition=self.crash_first_definition and not self.handles,
            ignore_exit=self.ignore_exit,
        )
        handle = FakeProcessHandle(server)
        self.handles.append(handle)
        return handle


def _definition(
    *,
    language_extensions: Mapping[str, tuple[str, ...]] | None = None,
    request_timeout_seconds: float = 1,
    shutdown_timeout_seconds: float = 1,
) -> LspServerDefinition:
    return LspServerDefinition(
        id="fake-python",
        command=("fake-language-server", "--stdio"),
        language_extensions=language_extensions or {"python": ("py",)},
        root_markers=("pyproject.toml",),
        priority=100,
        environment={"LSP_MODE": "test"},
        settings={"python": {"analysis": "strict"}},
        startup_timeout_seconds=1,
        request_timeout_seconds=request_timeout_seconds,
        shutdown_timeout_seconds=shutdown_timeout_seconds,
    )


def _binding(
    workspace: Path,
    launcher: FakeLauncher,
    files: dict[Path, str],
    definition: LspServerDefinition | None = None,
) -> CodingLspBinding:
    return CodingLspBinding(
        workspace_root=workspace,
        definitions=(definition or _definition(),),
        launcher=launcher,
        read_text=lambda path: files[path],
        baseline_environment={"PATH": "/admitted/bin", "LANG": "C.UTF-8"},
    )


def test_fake_launcher_drives_tool_to_definition_and_ordered_sync(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        (project / "pyproject.toml").touch()
        source = project / "main.py"
        source.touch()
        files = {source.resolve(): "😀target = 1\nprint(target)\n"}
        launcher = FakeLauncher(
            definition_result={
                "uri": source.resolve().as_uri(),
                "range": {
                    "start": {"line": 0, "character": 2},
                    "end": {"line": 0, "character": 8},
                },
            }
        )
        binding = _binding(tmp_path, launcher, files)
        definition = create_inspect_symbol_tool_definition(binding)
        tool = wrap_tool_definition(
            definition,
            context_provider=lambda *, tool_call_id: ToolContext(
                tool_call_id=tool_call_id,
                cwd=str(tmp_path),
            ),
        )

        first = await tool.execute(
            "lsp-call-1",
            {"path": "project/main.py", "line": 2, "character": 7},
        )
        second = await tool.execute(
            "lsp-call-2",
            {"path": "project/main.py", "line": 2, "character": 7},
        )

        assert first.details["items"] == (
            {
                "path": "project/main.py",
                "uri": source.resolve().as_uri(),
                "range": {
                    "start": {"line": 1, "character": 2},
                    "end": {"line": 1, "character": 8},
                },
                "external": False,
                "readable": True,
            },
        )
        assert first.details["document_version"] == 1
        assert second.details["document_version"] == 1
        assert len(launcher.requests) == 1
        assert launcher.correlation_ids == ["lsp-call-1"]
        request = launcher.requests[0]
        assert request.command == ("fake-language-server", "--stdio")
        assert request.cwd == str(project.resolve())
        assert dict(request.effective_environment) == {
            "PATH": "/admitted/bin",
            "LANG": "C.UTF-8",
            "LSP_MODE": "test",
        }
        assert request.effective_environment == (
            ("LANG", "C.UTF-8"),
            ("LSP_MODE", "test"),
            ("PATH", "/admitted/bin"),
        )

        server = launcher.handles[0].server
        assert server.methods().count("initialize") == 1
        assert server.methods().count("textDocument/didOpen") == 1
        assert "textDocument/didChange" not in server.methods()
        configuration_responses = [
            message
            for message in server.messages
            if message.get("id") == "server-config-1" and "result" in message
        ]
        assert configuration_responses == [
            {
                "jsonrpc": "2.0",
                "id": "server-config-1",
                "result": [{"python": {"analysis": "strict"}}],
            }
        ]
        definition_calls = [
            message
            for message in server.messages
            if message.get("method") == "textDocument/definition"
        ]
        assert definition_calls[0]["params"]["position"] == {
            "line": 1,
            "character": 6,
        }
        assert definition.execution_mode == "parallel"
        assert definition.parameters["properties"]["query"]["enum"] == ["definition"]
        assert "include_declaration" not in definition.parameters["properties"]

        files[source.resolve()] = "😀target = 2\nprint(target)\n"
        changed = await binding.inspect_symbol(
            path="project/main.py",
            line=2,
            character=7,
            correlation_id="lsp-call-3",
        )
        assert changed.document_version == 2
        assert server.methods().count("textDocument/didChange") == 1

        await binding.dispose()
        assert launcher.handles[0].close_calls == 1
        assert server.methods()[-2:] == ["shutdown", "exit"]

    asyncio.run(scenario())


def test_concurrent_first_queries_single_flight_launch_and_document_open(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        files = {source.resolve(): "value = 1\nprint(value)\n"}
        gate = asyncio.Event()
        launcher = FakeLauncher(
            definition_result=None,
            initialize_gate=gate,
        )
        binding = _binding(tmp_path, launcher, files)

        first = asyncio.create_task(
            binding.inspect_symbol(
                path="main.py",
                line=2,
                character=7,
                correlation_id="first",
            )
        )
        second = asyncio.create_task(
            binding.inspect_symbol(
                path="main.py",
                line=2,
                character=7,
                correlation_id="second",
            )
        )
        for _ in range(20):
            if launcher.requests:
                break
            await asyncio.sleep(0)
        assert len(launcher.requests) == 1
        gate.set()
        results = await asyncio.gather(first, second)

        assert [result.count for result in results] == [0, 0]
        assert launcher.handles[0].server.methods().count("textDocument/didOpen") == 1
        await binding.dispose()

    asyncio.run(scenario())


def test_initialize_failure_closes_fake_process_and_publishes_no_runtime(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        launcher = FakeLauncher(
            definition_result=None,
            position_encoding="utf-8",
        )
        binding = _binding(tmp_path, launcher, {source.resolve(): "value = 1\n"})

        with pytest.raises(LspProtocolError, match="position encoding"):
            await binding.inspect_symbol(
                path="main.py",
                line=1,
                character=1,
                correlation_id="bad-init",
            )

        assert len(launcher.handles) == 1
        assert launcher.handles[0].close_calls == 1
        await binding.dispose()

    asyncio.run(scenario())


def test_query_rejects_workspace_escape_and_bounds_definition_results(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        location = {
            "uri": source.resolve().as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 5},
            },
        }
        launcher = FakeLauncher(definition_result=[location, location, location])
        binding = _binding(tmp_path, launcher, {source.resolve(): "value = 1\n"})

        with pytest.raises(LspInvalidInputError, match="within the Coding workspace"):
            await binding.inspect_symbol(
                path="../outside.py",
                line=1,
                character=1,
                correlation_id="escaped",
            )
        assert launcher.requests == []

        result = await binding.inspect_symbol(
            path="main.py",
            line=1,
            character=1,
            limit=2,
            correlation_id="bounded",
        )
        assert result.count == 3
        assert len(result.items) == 2
        assert result.truncated is True
        await binding.dispose()

    asyncio.run(scenario())


def test_caller_cancellation_sends_protocol_cancel_and_keeps_runtime(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        gate = asyncio.Event()
        launcher = FakeLauncher(definition_result=None, definition_gate=gate)
        binding = _binding(tmp_path, launcher, {source.resolve(): "value = 1\n"})

        query = asyncio.create_task(
            binding.inspect_symbol(
                path="main.py",
                line=1,
                character=1,
                correlation_id="cancelled-query",
            )
        )
        for _ in range(100):
            if launcher.handles:
                server = launcher.handles[0].server
                if "textDocument/definition" in server.methods():
                    break
            await asyncio.sleep(0)
        else:
            raise AssertionError("definition request was not issued")

        query.cancel()
        with pytest.raises(asyncio.CancelledError):
            await query
        await _wait_for_method(server, "$/cancelRequest")

        gate.set()
        result = await binding.inspect_symbol(
            path="main.py",
            line=1,
            character=1,
            correlation_id="next-query",
        )
        assert result.count == 0
        assert len(launcher.requests) == 1
        await binding.dispose()

    asyncio.run(scenario())


def test_request_timeout_sends_protocol_cancel_and_keeps_runtime(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        gate = asyncio.Event()
        launcher = FakeLauncher(definition_result=None, definition_gate=gate)
        definition = _definition(request_timeout_seconds=0.01)
        binding = _binding(
            tmp_path,
            launcher,
            {source.resolve(): "value = 1\n"},
            definition,
        )

        with pytest.raises(LspProtocolError, match="timed out"):
            await binding.inspect_symbol(
                path="main.py",
                line=1,
                character=1,
                correlation_id="timed-out-query",
            )
        server = launcher.handles[0].server
        await _wait_for_method(server, "$/cancelRequest")

        gate.set()
        result = await binding.inspect_symbol(
            path="main.py",
            line=1,
            character=1,
            correlation_id="after-timeout",
        )
        assert result.count == 0
        assert len(launcher.requests) == 1
        await binding.dispose()

    asyncio.run(scenario())


def test_shutdown_rejects_new_requests_and_waits_for_graceful_exit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        definition_gate = asyncio.Event()
        shutdown_gate = asyncio.Event()
        launcher = FakeLauncher(
            definition_result=None,
            definition_gate=definition_gate,
            shutdown_gate=shutdown_gate,
        )
        handle = await launcher.start(
            ProcessLaunchRequest(
                command=("fake-language-server",),
                cwd=str(tmp_path.resolve()),
            ),
            correlation_id="client-test",
        )
        client = LspClient(
            handle,
            request_timeout_seconds=1,
            shutdown_timeout_seconds=1,
        )
        await client.initialize(
            root_uri=tmp_path.resolve().as_uri(),
            initialization_options={},
            timeout_seconds=1,
        )

        pending = asyncio.create_task(client.request("textDocument/definition", {}))
        await _wait_for_method(handle.server, "textDocument/definition")
        closing = asyncio.create_task(client.shutdown())
        await _wait_for_method(handle.server, "$/cancelRequest")
        await _wait_for_method(handle.server, "shutdown")
        with pytest.raises(LspProtocolError, match="closing"):
            await pending
        with pytest.raises(LspProtocolError, match="closed"):
            await client.request("textDocument/definition", {})
        shutdown_gate.set()
        await closing

        assert handle.wait_calls == 1
        assert handle.terminate_calls == 0
        assert handle.close_calls == 1
        assert handle.server.methods()[-2:] == ["shutdown", "exit"]

    asyncio.run(scenario())


def test_shutdown_timeout_uses_terminate_fallback(tmp_path: Path) -> None:
    async def scenario() -> None:
        launcher = FakeLauncher(definition_result=None, ignore_exit=True)
        handle = await launcher.start(
            ProcessLaunchRequest(
                command=("fake-language-server",),
                cwd=str(tmp_path.resolve()),
            ),
            correlation_id="client-test",
        )
        client = LspClient(
            handle,
            request_timeout_seconds=1,
            shutdown_timeout_seconds=0.01,
        )
        await client.initialize(
            root_uri=tmp_path.resolve().as_uri(),
            initialization_options={},
            timeout_seconds=1,
        )

        await client.shutdown()

        assert handle.wait_calls == 1
        assert handle.terminate_calls == 1
        assert handle.close_calls == 1

    asyncio.run(scenario())


def test_cancelled_binding_dispose_keeps_one_shared_close_running(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        shutdown_gate = asyncio.Event()
        launcher = FakeLauncher(
            definition_result=None,
            shutdown_gate=shutdown_gate,
        )
        binding = _binding(tmp_path, launcher, {source.resolve(): "value = 1\n"})
        await binding.inspect_symbol(
            path="main.py",
            line=1,
            character=1,
            correlation_id="open-runtime",
        )

        first = asyncio.create_task(binding.dispose())
        await _wait_for_method(launcher.handles[0].server, "shutdown")
        second = asyncio.create_task(binding.dispose())
        await asyncio.sleep(0)
        assert not first.done()
        assert not second.done()

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not second.done()

        shutdown_gate.set()
        await second
        assert launcher.handles[0].close_calls == 1

    asyncio.run(scenario())


def test_server_crash_restarts_on_demand_and_reopens_document(tmp_path: Path) -> None:
    async def scenario() -> None:
        (tmp_path / "pyproject.toml").touch()
        source = tmp_path / "main.py"
        source.touch()
        launcher = FakeLauncher(
            definition_result=None,
            crash_first_definition=True,
        )
        binding = _binding(tmp_path, launcher, {source.resolve(): "value = 1\n"})

        with pytest.raises(LspProtocolError, match="reader failed"):
            await binding.inspect_symbol(
                path="main.py",
                line=1,
                character=1,
                correlation_id="crashed-query",
            )
        result = await binding.inspect_symbol(
            path="main.py",
            line=1,
            character=1,
            correlation_id="replacement-query",
        )

        assert result.count == 0
        assert len(launcher.requests) == 2
        assert [
            handle.server.methods().count("textDocument/didOpen")
            for handle in launcher.handles
        ] == [1, 1]
        await binding.dispose()

    asyncio.run(scenario())


def test_language_mapping_catalog_freeze_and_literal_root_markers(
    tmp_path: Path,
) -> None:
    settings = {"nested": {"modes": ["strict"]}}
    definition = LspServerDefinition(
        id="typescript-family",
        command=["typescript-language-server", "--stdio"],
        language_extensions={
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx"],
        },
        settings=settings,
    )
    settings["nested"]["modes"].append("loose")
    (tmp_path / "sample.js").touch()
    selector = LspSelector(
        workspace_root=tmp_path,
        catalog=LspCatalog((definition,)),
    )

    assert definition.command == ("typescript-language-server", "--stdio")
    assert definition.settings["nested"]["modes"] == ("strict",)
    assert selector.select("sample.js").language_id == "javascript"

    with pytest.raises(ValueError, match="literal relative"):
        LspServerDefinition(
            id="glob-root",
            command=("server",),
            language_extensions={"python": (".py",)},
            root_markers=("**/pyproject.toml",),
        )
    with pytest.raises(ValueError, match="belongs to both"):
        LspServerDefinition(
            id="ambiguous-extension",
            command=("server",),
            language_extensions={
                "typescript": (".ts",),
                "other": (".ts",),
            },
        )
