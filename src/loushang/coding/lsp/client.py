"""Minimal, bounded JSON-RPC/LSP client over an injected process handle."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import suppress

from loushang.coding.lsp.model import LspProtocolError
from loushang.coding.lsp.ports import ProcessHandle

_MAX_HEADER_BYTES = 16 * 1024
_MAX_MESSAGE_BYTES = 4 * 1024 * 1024
_MAX_PENDING_REQUESTS = 128
_MAX_CONFIGURATION_ITEMS = 64


class LspClient:
    """Own exactly one reader, one serialized writer, and one LSP connection."""

    def __init__(
        self,
        handle: ProcessHandle,
        *,
        request_timeout_seconds: float,
        shutdown_timeout_seconds: float,
        settings: Mapping[str, object] | None = None,
    ) -> None:
        self._handle = handle
        self._request_timeout_seconds = request_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._settings = dict(settings or {})
        self._buffer = bytearray()
        self._write_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[object]] = {}
        self._next_request_id = 1
        self._reader_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._state = "open"
        self._position_encoding = "utf-16"
        self._discarded_diagnostic_publications = 0

    @property
    def position_encoding(self) -> str:
        return self._position_encoding

    @property
    def is_closed(self) -> bool:
        return self._state == "closed" or (
            self._reader_task is not None and self._reader_task.done()
        )

    @property
    def discarded_diagnostic_publications(self) -> int:
        return self._discarded_diagnostic_publications

    async def initialize(
        self,
        *,
        root_uri: str,
        initialization_options: Mapping[str, object],
        timeout_seconds: float,
    ) -> None:
        async with self._lifecycle_lock:
            if self._initialized:
                return
            if self.is_closed:
                raise LspProtocolError("cannot initialize a closed LSP connection")
            self._reader_task = asyncio.create_task(
                self._reader_loop(),
                name="coding-lsp-reader",
            )
            result = await self.request(
                "initialize",
                {
                    "processId": None,
                    "clientInfo": {"name": "loushang", "version": "0.1"},
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": "workspace"}],
                    "capabilities": {
                        "general": {"positionEncodings": ["utf-16"]},
                        "textDocument": {
                            "synchronization": {
                                "dynamicRegistration": False,
                                "didSave": False,
                            },
                            "definition": {"dynamicRegistration": False},
                        },
                        "workspace": {
                            "configuration": True,
                            "applyEdit": False,
                        },
                    },
                    "initializationOptions": dict(initialization_options),
                },
                timeout_seconds=timeout_seconds,
            )
            if not isinstance(result, Mapping):
                raise LspProtocolError("initialize response must be an object")
            capabilities = result.get("capabilities", {})
            if not isinstance(capabilities, Mapping):
                raise LspProtocolError("initialize capabilities must be an object")
            encoding = capabilities.get("positionEncoding", "utf-16")
            if encoding != "utf-16":
                raise LspProtocolError(
                    f"unsupported LSP position encoding: {encoding!r}"
                )
            self._position_encoding = encoding
            await self.notify("initialized", {})
            self._initialized = True

    async def request(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        return await self._request(
            method,
            params,
            timeout_seconds=timeout_seconds,
            allow_closing=False,
        )

    async def _request(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        timeout_seconds: float | None,
        allow_closing: bool,
    ) -> object:
        if self.is_closed or (self._state == "closing" and not allow_closing):
            raise LspProtocolError("LSP connection is closed")
        if len(self._pending) >= _MAX_PENDING_REQUESTS:
            raise LspProtocolError("too many pending LSP requests")
        request_id = self._next_request_id
        self._next_request_id += 1
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": dict(params),
                }
            )
            timeout = timeout_seconds or self._request_timeout_seconds
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout)
            except TimeoutError:
                future.cancel()
                with suppress(LspProtocolError):
                    await self._notify(
                        "$/cancelRequest",
                        {"id": request_id},
                        allow_closing=allow_closing,
                    )
                raise LspProtocolError(
                    f"LSP request {method!r} timed out after {timeout:g}s"
                ) from None
            except asyncio.CancelledError:
                future.cancel()
                with suppress(LspProtocolError):
                    await self._notify(
                        "$/cancelRequest",
                        {"id": request_id},
                        allow_closing=allow_closing,
                    )
                raise
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: Mapping[str, object]) -> None:
        await self._notify(method, params, allow_closing=False)

    async def _notify(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        allow_closing: bool,
    ) -> None:
        if self.is_closed or (self._state == "closing" and not allow_closing):
            raise LspProtocolError("LSP connection is closed")
        await self._write_message(
            {"jsonrpc": "2.0", "method": method, "params": dict(params)}
        )

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            if self._state == "closed":
                return
            if self._state == "closing":
                return
            self._state = "closing"
            try:
                await self._cancel_pending_for_close()
                if self._initialized and not self.is_closed:
                    with suppress(LspProtocolError):
                        await self._request(
                            "shutdown",
                            {},
                            timeout_seconds=self._shutdown_timeout_seconds,
                            allow_closing=True,
                        )
                    if not self.is_closed:
                        with suppress(LspProtocolError):
                            await self._notify("exit", {}, allow_closing=True)
                        with suppress(LspProtocolError):
                            await self._wait_for_exit()
            finally:
                try:
                    await self._handle.close()
                finally:
                    await self._settle_reader()
                    self._state = "closed"
                    self._fail_pending(LspProtocolError("LSP connection was closed"))

    async def abort(self) -> None:
        async with self._lifecycle_lock:
            if self._state == "closed":
                return
            self._state = "closing"
            self._fail_pending(LspProtocolError("LSP connection was aborted"))
            try:
                await self._handle.close()
            finally:
                await self._settle_reader()
                self._state = "closed"
                self._fail_pending(LspProtocolError("LSP connection was aborted"))

    async def _wait_for_exit(self) -> None:
        waiter = asyncio.create_task(
            self._handle.wait(),
            name="coding-lsp-process-exit",
        )
        try:
            try:
                await asyncio.wait_for(
                    asyncio.shield(waiter),
                    self._shutdown_timeout_seconds,
                )
            except TimeoutError:
                await self._handle.terminate()
                await waiter
        except BaseException as exc:
            if not waiter.done():
                waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await waiter
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise LspProtocolError(
                f"waiting for language server exit failed: {exc}"
            ) from exc

    async def _cancel_pending_for_close(self) -> None:
        request_ids = tuple(self._pending)
        self._fail_pending(LspProtocolError("LSP connection is closing"))
        for request_id in request_ids:
            with suppress(LspProtocolError):
                await self._notify(
                    "$/cancelRequest",
                    {"id": request_id},
                    allow_closing=True,
                )

    async def _settle_reader(self) -> None:
        task = self._reader_task
        if task is None or task is asyncio.current_task():
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, LspProtocolError):
            await task

    async def _write_message(self, message: Mapping[str, object]) -> None:
        body = json.dumps(
            _thaw_json(message),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > _MAX_MESSAGE_BYTES:
            raise LspProtocolError("outbound LSP message exceeds the size limit")
        payload = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        async with self._write_lock:
            await self._handle.write_stdin(payload)

    async def _reader_loop(self) -> None:
        error: BaseException | None = None
        try:
            while True:
                message = await self._read_message()
                await self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            error = exc
        finally:
            if self._state == "open":
                self._state = "closed"
                if error is None:
                    error = LspProtocolError("language server closed stdout")
                elif not isinstance(error, LspProtocolError):
                    error = LspProtocolError(f"LSP reader failed: {error}")
                self._fail_pending(error)

    async def _read_message(self) -> Mapping[str, object]:
        while b"\r\n\r\n" not in self._buffer:
            if len(self._buffer) > _MAX_HEADER_BYTES:
                raise LspProtocolError("LSP header exceeds the size limit")
            await self._read_chunk()
        raw_header, _, remainder = self._buffer.partition(b"\r\n\r\n")
        self._buffer = bytearray(remainder)
        content_length: int | None = None
        for line in raw_header.split(b"\r\n"):
            name, separator, value = line.partition(b":")
            if not separator:
                raise LspProtocolError("malformed LSP header")
            if name.strip().lower() == b"content-length":
                try:
                    content_length = int(value.strip())
                except ValueError as exc:
                    raise LspProtocolError("invalid LSP Content-Length") from exc
        if content_length is None or not 0 <= content_length <= _MAX_MESSAGE_BYTES:
            raise LspProtocolError("invalid or missing LSP Content-Length")
        while len(self._buffer) < content_length:
            await self._read_chunk()
        body = bytes(self._buffer[:content_length])
        del self._buffer[:content_length]
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LspProtocolError("invalid LSP JSON payload") from exc
        if not isinstance(value, Mapping):
            raise LspProtocolError("LSP message must be an object")
        return value

    async def _read_chunk(self) -> None:
        chunk = await self._handle.read_stdout()
        if not chunk:
            if self._buffer:
                raise LspProtocolError("language server closed stdout mid-frame")
            raise EOFError
        self._buffer.extend(chunk)

    async def _dispatch(self, message: Mapping[str, object]) -> None:
        if "method" in message:
            method = message.get("method")
            if not isinstance(method, str):
                raise LspProtocolError("LSP method must be a string")
            if "id" in message:
                await self._handle_server_request(message, method)
            elif method == "textDocument/publishDiagnostics":
                self._discarded_diagnostic_publications += 1
            return

        response_id = message.get("id")
        if not isinstance(response_id, int) or isinstance(response_id, bool):
            raise LspProtocolError("LSP response id must be an integer")
        future = self._pending.get(response_id)
        if future is None or future.done():
            return
        error = message.get("error")
        if error is not None:
            future.set_exception(LspProtocolError(f"LSP response error: {error!r}"))
        else:
            future.set_result(message.get("result"))

    async def _handle_server_request(
        self,
        message: Mapping[str, object],
        method: str,
    ) -> None:
        request_id = message.get("id")
        response: dict[str, object] = {"jsonrpc": "2.0", "id": request_id}
        if method == "workspace/configuration":
            params = message.get("params", {})
            items = params.get("items", []) if isinstance(params, Mapping) else []
            count = (
                min(len(items), _MAX_CONFIGURATION_ITEMS)
                if isinstance(items, list)
                else 0
            )
            response["result"] = [dict(self._settings) for _ in range(count)]
        elif method == "workspace/applyEdit":
            response["result"] = {"applied": False, "failureReason": "unsupported"}
        elif method == "window/showMessageRequest":
            response["result"] = None
        else:
            response["error"] = {"code": -32601, "message": "Method not found"}
        await self._write_message(response)

    def _fail_pending(self, error: BaseException) -> None:
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(name): _thaw_json(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


__all__ = ["LspClient"]
