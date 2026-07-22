"""Product-neutral session action coordination for conversation hosts."""

from __future__ import annotations

import asyncio
import inspect
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from loushang.harness.commands import CommandEffectKind
from loushang.harness.host.types import HostActionResult

CommandCatalogFactory = Callable[[Any], Any]
ImageParts = tuple[object, ...] | list[object] | None


class _TextIntent(Protocol):
    @property
    def text(self) -> str: ...


class _BashIntent(Protocol):
    @property
    def command(self) -> str: ...


@dataclass
class ConversationUiController:
    """Coordinate conversation actions against an injected session surface.

    The controller owns action sequencing and failure conversion only. Products
    may inject a command-catalog factory to bind their local command profile;
    command definitions and command result wording remain outside this module.
    """

    session: Any
    runtime: Any | None = None
    verbose: bool = False
    command_catalog_factory: CommandCatalogFactory | None = None
    command_route: str = "dispatch"
    command_sources: frozenset[str] = frozenset({"builtin", "extension"})
    prompt_intent_type: type[object] | None = None
    bash_intent_type: type[object] | None = None
    follow_up_intent_type: type[object] | None = None
    abort_intent_type: type[object] | None = None
    quit_intent_type: type[object] | None = None
    problem_code_prefix: str = "conversation_ui"
    problem_logger: Any | None = None
    bash_options: Callable[[], Mapping[str, object]] = lambda: {
        "exclude_from_context": True
    }

    async def dispatch(self, intent: object | None) -> HostActionResult:
        if intent is None:
            return HostActionResult(handled=False)
        try:
            if self.prompt_intent_type is not None and isinstance(
                intent, self.prompt_intent_type
            ):
                prompt_intent = cast(_TextIntent, intent)
                command_result = await self._dispatch_session_command(intent)
                if command_result is not None:
                    return command_result
                await self._prompt(
                    prompt_intent.text,
                    images=getattr(prompt_intent, "images", None),
                )
                return HostActionResult()
            if self.bash_intent_type is not None and isinstance(
                intent, self.bash_intent_type
            ):
                await self._bash(cast(_BashIntent, intent).command)
                return HostActionResult()
            if self.follow_up_intent_type is not None and isinstance(
                intent, self.follow_up_intent_type
            ):
                return await self.follow_up(cast(_TextIntent, intent).text)
            if self.abort_intent_type is not None and isinstance(
                intent, self.abort_intent_type
            ):
                await self._abort()
                return HostActionResult()
            if self.quit_intent_type is not None and isinstance(
                intent, self.quit_intent_type
            ):
                return HostActionResult(exit_code=0)
        except asyncio.CancelledError as error:
            self._record_problem(
                f"{self.problem_code_prefix}_request_cancelled",
                message="Request cancelled.",
                exc=error,
                intent=type(intent).__name__,
            )
            return HostActionResult(
                error_message="Request cancelled.",
                traceback_text=traceback.format_exc() if self.verbose else None,
            )
        except Exception as error:
            self._record_problem(
                f"{self.problem_code_prefix}_dispatch_failed",
                intent=type(intent).__name__,
                message=str(error) or error.__class__.__name__,
                exc=error,
            )
            return HostActionResult(
                error_message=str(error) or error.__class__.__name__,
                traceback_text=traceback.format_exc() if self.verbose else None,
            )
        return HostActionResult(handled=False)

    async def steer(
        self,
        text: str,
        images: ImageParts = None,
    ) -> HostActionResult:
        return await self._dispatch_text_action(
            "steer",
            text,
            images=images,
            unavailable="Steering is unavailable for this session.",
            failure_code="conversation_ui_steer_failed",
        )

    async def follow_up(
        self,
        text: str,
        images: ImageParts = None,
    ) -> HostActionResult:
        return await self._dispatch_text_action(
            "follow_up",
            text,
            images=images,
            unavailable="Follow-up is unavailable for this session.",
            failure_code="conversation_ui_follow_up_failed",
        )

    async def wait_for_idle(self) -> None:
        await _call_if_available(self.session, "wait_for_idle")

    async def _dispatch_text_action(
        self,
        action: str,
        text: str,
        *,
        images: ImageParts,
        unavailable: str,
        failure_code: str,
    ) -> HostActionResult:
        try:
            method = _streaming_prompt_method(
                self.session,
                streaming_behavior="steer" if action == "steer" else "followUp",
            )
            if method is None:
                method = getattr(self.session, action, None)
            if not callable(method):
                return HostActionResult(error_message=unavailable)
            await _call_text_method(method, text, images=images)
            return HostActionResult()
        except Exception as error:
            self._record_problem(
                f"{self.problem_code_prefix}_{failure_code.removeprefix('conversation_ui_')}",
                message=str(error) or error.__class__.__name__,
                exc=error,
            )
            return HostActionResult(
                error_message=str(error) or error.__class__.__name__,
                traceback_text=traceback.format_exc() if self.verbose else None,
            )

    async def _prompt(
        self,
        text: str,
        *,
        images: ImageParts,
    ) -> None:
        method = getattr(self.session, "prompt", None)
        if not callable(method):
            raise RuntimeError("Session does not support prompts")
        await _call_text_method(method, text, images=images)

    async def _dispatch_session_command(
        self, intent: object
    ) -> HostActionResult | None:
        if getattr(intent, "images", None):
            return None
        executor = getattr(self.session, "execute_command_async", None)
        if self.command_catalog_factory is None or not callable(executor):
            return None
        catalog = self.command_catalog_factory(self.session)
        effect = catalog.effect_for_route(self.command_route, intent)
        if effect is None or effect.kind is not CommandEffectKind.SESSION:
            return None
        if effect.command.source not in self.command_sources:
            return None
        invocation_name = effect.payload.get("invocation_name")
        args = effect.payload.get("args", "")
        if not isinstance(invocation_name, str) or not isinstance(args, str):
            return None
        execution = await _maybe_await(executor(invocation_name, args))
        return _controller_result_from_command_execution(
            execution,
            invocation_name=invocation_name,
        )

    async def _bash(self, command: str) -> None:
        method = getattr(self.session, "execute_bash", None)
        if not callable(method):
            raise RuntimeError("Session does not support bash execution")
        await _maybe_await(method(command, **dict(self.bash_options())))

    async def _abort(self) -> None:
        try:
            await _call_if_available(self.session, "abort")
        finally:
            await _call_if_available(self.session, "clear_queue")
            await _call_if_available(self.session, "abort_bash")

    def _record_problem(self, code: str, **details: object) -> None:
        if self.problem_logger is None:
            return
        self.problem_logger.problem(
            code,
            source="agent",
            message=str(details.pop("message", "Request failed.")),
            recoverable=True,
            exc=details.pop("exc", None),
            **details,
        )


async def _call_if_available(target: Any, method_name: str) -> None:
    method = getattr(target, method_name, None)
    if callable(method):
        await _maybe_await(method())


def _streaming_prompt_method(session: Any, *, streaming_behavior: str):
    prompt = getattr(session, "prompt", None)
    if not callable(prompt) or not _supports_keyword(prompt, "streaming_behavior"):
        return None

    async def _call(
        text: str,
        images: ImageParts = None,
    ) -> Any:
        kwargs: dict[str, object] = {"streaming_behavior": streaming_behavior}
        if _supports_keyword(prompt, "source"):
            kwargs["source"] = "interactive"
        if images is not None and _supports_keyword(prompt, "images"):
            kwargs["images"] = list(images)
        return await _maybe_await(prompt(text, **kwargs))

    return _call


async def _call_text_method(
    method: Any,
    text: str,
    *,
    images: ImageParts = None,
) -> Any:
    if images is not None and _supports_keyword(method, "images"):
        return await _maybe_await(method(text, images=list(images)))
    return await _maybe_await(method(text))


def _supports_keyword(method: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters.values()
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == keyword
        for parameter in parameters
    )


def _controller_result_from_command_execution(
    execution: object,
    *,
    invocation_name: str,
) -> HostActionResult:
    result = getattr(execution, "result", None)
    if result is None and not hasattr(execution, "result"):
        result = execution
    if isinstance(result, dict):
        display = result.get("display")
        if isinstance(display, str) and display:
            return HostActionResult(status_message=display)
        message = result.get("message")
        if isinstance(message, str) and message:
            if result.get("status") == "error":
                return HostActionResult(error_message=message)
            return HostActionResult(status_message=message)
    return HostActionResult(status_message=f"Command /{invocation_name} completed.")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = ["CommandCatalogFactory", "ConversationUiController", "ImageParts"]
