from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass

RuntimeHostProvider = Callable[[], object | None]


@dataclass
class ExtensionReplacementController:
    get_runtime_host: RuntimeHostProvider

    def create_context(self, session: object) -> object:
        runner = getattr(session, "extension_runner", None)
        if runner is None:
            return session
        session_manager = getattr(session, "session_manager", None)
        fallback_cwd = session_manager.get_cwd() if session_manager is not None else ""
        context = runner.create_command_context(fallback_cwd=fallback_cwd)
        send_message = getattr(session, "_send_message_from_extension", None)
        send_user_message = getattr(session, "_send_user_message_from_extension_async", None)
        if not callable(send_message) or not callable(send_user_message):
            raise RuntimeError("Session replacement callback requires a valid AgentSession instance.")

        def _assert_context_active() -> None:
            getattr(context, "cwd")

        async def _send_message(message: object, options: object | None = None) -> None:
            _assert_context_active()
            await send_message(message, options)

        async def _send_user_message(content: object, options: object | None = None) -> None:
            _assert_context_active()
            await send_user_message(content, options)

        context.send_message = _send_message
        context.send_user_message = _send_user_message
        return context

    async def fork(self, entry_id: str, options: object | None = None) -> dict[str, object]:
        runtime_host = self.get_runtime_host()
        fork_session_with_result = (
            getattr(runtime_host, "fork_session_with_result", None) if runtime_host is not None else None
        )
        fork_session = getattr(runtime_host, "fork_session", None) if runtime_host is not None else None
        if not callable(fork_session_with_result) and not callable(fork_session):
            return {"cancelled": True}
        opts = options if isinstance(options, dict) else {}
        position = opts.get("position", "before")
        if position not in {"at", "before"}:
            raise ValueError(f"Unsupported fork position: {position}")
        before = getattr(runtime_host, "get_current_session", lambda: None)()
        selected_text = None
        if callable(fork_session_with_result):
            _session, selected_text = await fork_session_with_result(entry_id, position=position)
        elif callable(fork_session):
            await fork_session(entry_id)
        after = getattr(runtime_host, "get_current_session", lambda: None)()
        if before is not after:
            await self.run_replaced_session_callbacks(after, options)
        result: dict[str, object] = {"cancelled": before is after}
        if selected_text is not None:
            result["selected_text"] = selected_text
            result["selectedText"] = selected_text
        return result

    async def new_session(self, options: object | None = None) -> dict[str, object]:
        runtime_host = self.get_runtime_host()
        new_session = getattr(runtime_host, "new_session", None) if runtime_host is not None else None
        if not callable(new_session):
            return {"cancelled": True}
        opts = options if isinstance(options, dict) else {}
        before = getattr(runtime_host, "get_current_session", lambda: None)()
        await new_session(parent_session=_optional_string(opts.get("parentSession", opts.get("parent_session"))))
        after = getattr(runtime_host, "get_current_session", lambda: None)()
        if before is not after:
            await self.run_replaced_session_callbacks(after, options, include_setup=True)
        return {"cancelled": before is after}

    async def switch_session(self, session_path: str, options: object | None = None) -> dict[str, object]:
        runtime_host = self.get_runtime_host()
        switch_session = getattr(runtime_host, "switch_session", None) if runtime_host is not None else None
        if not callable(switch_session):
            return {"cancelled": True}
        before = getattr(runtime_host, "get_current_session", lambda: None)()
        await switch_session(session_path)
        after = getattr(runtime_host, "get_current_session", lambda: None)()
        if before is not after:
            await self.run_replaced_session_callbacks(after, options)
        return {"cancelled": before is after}

    async def run_replaced_session_callbacks(
        self,
        session: object | None,
        options: object | None,
        *,
        include_setup: bool = False,
    ) -> None:
        if session is None or not isinstance(options, dict):
            return
        if include_setup:
            setup = options.get("setup")
            if callable(setup):
                await _await_replacement_callback(
                    setup,
                    getattr(session, "session_manager", None),
                    name="setup",
                )
        with_session = options.get("withSession") or options.get("with_session")
        if not callable(with_session):
            return
        await _await_replacement_callback(with_session, _replacement_context(session), name="withSession")


def _replacement_context(session: object) -> object:
    create_context = getattr(session, "create_replaced_session_context", None)
    if callable(create_context):
        return create_context()
    runner = getattr(session, "extension_runner", None)
    session_manager = getattr(session, "session_manager", None)
    if runner is not None:
        cwd = session_manager.get_cwd() if session_manager is not None else ""
        return runner.create_command_context(fallback_cwd=cwd)
    return session


async def _await_replacement_callback(callback: object, *args: object, name: str) -> None:
    if not _is_async_callable(callback):
        raise TypeError(f"{name} callback must be an async callable.")
    await callback(*args)


def _is_async_callable(value: object) -> bool:
    if inspect.iscoroutinefunction(value):
        return True
    call = getattr(value, "__call__", None)
    return inspect.iscoroutinefunction(call)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
