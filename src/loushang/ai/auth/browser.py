from __future__ import annotations

import asyncio
import contextlib
import html
import webbrowser
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse


def open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=1, autoraise=True))
    except Exception:
        return False


async def wait_for_callback_url(
    redirect_uri: str,
    *,
    timeout: float = 300.0,
    signal: object | None = None,
    response_html: str | None = None,
) -> str | None:
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    path = parsed.path or "/"
    scheme = parsed.scheme or "http"
    if port is None:
        raise ValueError(f"redirect_uri must include an explicit port: {redirect_uri}")

    loop = asyncio.get_running_loop()
    result: asyncio.Future[str] = loop.create_future()
    page = response_html or (
        "<html><body><h1>Login received</h1>"
        "<p>You can return to the terminal.</p></body></html>"
    )

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        request_line = ""
        try:
            request_line = (
                (await reader.readline()).decode("utf-8", errors="replace").strip()
            )
            while True:
                line = await reader.readline()
                if not line or line in {b"\r\n", b"\n"}:
                    break
        except Exception:
            request_line = ""

        request_target = ""
        parts = request_line.split(" ")
        if len(parts) >= 2:
            request_target = parts[1]

        status = "200 OK"
        body = page
        if request_target and request_target.startswith(path):
            callback_url = f"{scheme}://{host}:{port}{request_target}"
            if not result.done():
                result.set_result(callback_url)
        else:
            status = "404 Not Found"
            body = (
                "<html><body><h1>Unexpected callback</h1>"
                f"<p>{html.escape(request_target or '/')}</p></body></html>"
            )

        payload = body.encode("utf-8")
        writer.write(
            (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("utf-8")
        )
        writer.write(payload)
        with contextlib.suppress(Exception):
            await writer.drain()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, host="127.0.0.1", port=port)
    try:
        if signal is not None and getattr(signal, "cancelled", False):
            return None
        try:
            return await asyncio.wait_for(result, timeout=timeout)
        except TimeoutError:
            return None
    finally:
        server.close()
        await server.wait_closed()


CallbackWaiter = Callable[..., Awaitable[str | None]]
