"""Typed, Product-neutral operations over a bound session control surface.

This module is intentionally below any RPC or channel schema.  Products choose
which operation groups to expose, map their own requests to these values, and
project their own responses and errors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from loushang.ai.types import ImagePart
from loushang.harness.runtime import SessionOperationResult
from loushang.harness.session.facade import SessionControlPort


class SessionOperationCapability(str, Enum):
    """A coherent group of optional Product session operations."""

    INPUT = "input"
    QUEUE = "queue"
    LIFECYCLE = "lifecycle"
    IDENTITY = "identity"
    RETRY = "retry"
    MAINTENANCE = "maintenance"


class SessionOperationUnavailableError(RuntimeError):
    """Raised when a Product did not bind an optional operation group."""


@dataclass(frozen=True)
class SessionOperationAvailability:
    """Explicit capability declaration for one Product session binding."""

    capabilities: frozenset[SessionOperationCapability]

    @classmethod
    def standard(cls) -> "SessionOperationAvailability":
        """Expose every operation supported by ``SessionControlPort``."""

        return cls(frozenset(SessionOperationCapability))

    @classmethod
    def from_capabilities(
        cls,
        capabilities: Iterable[SessionOperationCapability],
    ) -> "SessionOperationAvailability":
        return cls(frozenset(capabilities))

    def supports(self, capability: SessionOperationCapability) -> bool:
        return capability in self.capabilities

    def require(self, capability: SessionOperationCapability) -> None:
        if not self.supports(capability):
            raise SessionOperationUnavailableError(
                f"Session operation capability is unavailable: {capability.value}"
            )


@dataclass(frozen=True)
class SessionPromptRequest:
    """One Product-adapted prompt submission without transport vocabulary."""

    text: str
    images: tuple[ImagePart, ...] = ()
    streaming_behavior: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("Session prompt text must be a non-empty string.")
        if self.streaming_behavior is not None and not isinstance(
            self.streaming_behavior, str
        ):
            raise TypeError("Session prompt streaming behavior must be a string.")
        if self.source is not None and not isinstance(self.source, str):
            raise TypeError("Session prompt source must be a string.")


@dataclass(frozen=True)
class SessionLifecycleOperationPorts:
    """Product callbacks for standard session replacement operations."""

    new_session: Callable[
        [str | None, str | None], Awaitable[SessionOperationResult[Any, Any]]
    ]
    restore_session: Callable[[str | Path], Awaitable[SessionOperationResult[Any, Any]]]
    fork_session: Callable[
        [str | None, str], Awaitable[SessionOperationResult[Any, Any]]
    ]
    clone_session: Callable[[], Awaitable[SessionOperationResult[Any, Any]]] | None = None


class SessionOperationRuntime:
    """Execute admitted session control groups through one explicit port.

    The runtime does not own background task scheduling, request validation,
    error schema, model selection, or output projection.  A host may schedule
    ``prompt`` itself while preserving the preflight callback contract.
    """

    def __init__(
        self,
        control: SessionControlPort,
        *,
        availability: SessionOperationAvailability | None = None,
        lifecycle: SessionLifecycleOperationPorts | None = None,
    ) -> None:
        self._control = control
        self._availability = (
            SessionOperationAvailability.standard()
            if availability is None
            else availability
        )
        self._lifecycle = lifecycle

    @property
    def availability(self) -> SessionOperationAvailability:
        return self._availability

    async def prompt(
        self,
        request: SessionPromptRequest,
        *,
        on_preflight: Callable[[bool], None] | None = None,
    ) -> None:
        self._require(SessionOperationCapability.INPUT)
        prompt_kwargs: dict[str, object] = {
            "streaming_behavior": request.streaming_behavior,
            "source": request.source,
        }
        if on_preflight is not None:
            prompt_kwargs["preflight_result"] = on_preflight
        if request.images:
            prompt_kwargs["images"] = list(request.images)
        await self._control.prompt(request.text, **prompt_kwargs)
        await self._control.wait_for_idle()

    async def new_session(
        self,
        *,
        cwd: str | None = None,
        parent_session: str | None = None,
    ) -> SessionOperationResult[Any, Any]:
        self._require_lifecycle_port()
        return await self._lifecycle.new_session(cwd, parent_session)

    async def restore_session(
        self,
        session_ref: str | Path,
    ) -> SessionOperationResult[Any, Any]:
        self._require_lifecycle_port()
        return await self._lifecycle.restore_session(session_ref)

    async def fork_session(
        self,
        entry_id: str | None,
        *,
        position: str = "at",
    ) -> SessionOperationResult[Any, Any]:
        self._require_lifecycle_port()
        return await self._lifecycle.fork_session(entry_id, position)

    async def clone_session(self) -> SessionOperationResult[Any, Any]:
        """Create an independent session at the current product position."""
        self._require_lifecycle_port()
        if self._lifecycle.clone_session is None:
            raise SessionOperationUnavailableError(
                "Session clone operation is unavailable"
            )
        return await self._lifecycle.clone_session()

    def steer(self, text: str, *, images: Iterable[ImagePart] = ()) -> None:
        self._require(SessionOperationCapability.INPUT)
        self._control.steer(text, images=list(images) or None)

    def follow_up(self, text: str, *, images: Iterable[ImagePart] = ()) -> None:
        self._require(SessionOperationCapability.INPUT)
        self._control.follow_up(text, images=list(images) or None)

    @property
    def pending_message_count(self) -> int:
        self._require(SessionOperationCapability.QUEUE)
        return self._control.pending_message_count

    def get_steering_messages(self) -> list[str]:
        self._require(SessionOperationCapability.QUEUE)
        return self._control.get_steering_messages()

    def get_follow_up_messages(self) -> list[str]:
        self._require(SessionOperationCapability.QUEUE)
        return self._control.get_follow_up_messages()

    def clear_queue(self) -> dict[str, list[str]]:
        self._require(SessionOperationCapability.QUEUE)
        return self._control.clear_queue()

    async def continue_run(self) -> None:
        self._require(SessionOperationCapability.LIFECYCLE)
        await self._control.continue_run()

    def abort(self) -> bool:
        self._require(SessionOperationCapability.LIFECYCLE)
        return self._control.abort()

    async def wait_for_idle(self) -> None:
        self._require(SessionOperationCapability.LIFECYCLE)
        await self._control.wait_for_idle()

    @property
    def session_id(self) -> str:
        self._require(SessionOperationCapability.IDENTITY)
        return self._control.session_id

    @property
    def session_name(self) -> str | None:
        self._require(SessionOperationCapability.IDENTITY)
        return self._control.session_name

    async def set_session_name(self, name: str | None) -> None:
        self._require(SessionOperationCapability.IDENTITY)
        await self._control.set_session_name(name)

    @property
    def is_retrying(self) -> bool:
        self._require(SessionOperationCapability.RETRY)
        return self._control.is_retrying

    def abort_retry(self) -> None:
        self._require(SessionOperationCapability.RETRY)
        self._control.abort_retry()

    async def wait_for_retry(self) -> None:
        self._require(SessionOperationCapability.RETRY)
        await self._control.wait_for_retry()

    @property
    def is_compacting(self) -> bool:
        self._require(SessionOperationCapability.MAINTENANCE)
        return self._control.is_compacting

    @property
    def auto_retry_enabled(self) -> bool:
        self._require(SessionOperationCapability.MAINTENANCE)
        return self._control.auto_retry_enabled

    @property
    def auto_compaction_enabled(self) -> bool:
        self._require(SessionOperationCapability.MAINTENANCE)
        return self._control.auto_compaction_enabled

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self._require(SessionOperationCapability.MAINTENANCE)
        self._control.set_auto_retry_enabled(enabled)

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        self._require(SessionOperationCapability.MAINTENANCE)
        self._control.set_auto_compaction_enabled(enabled)

    async def compact(self, custom_instructions: str | None = None) -> object:
        self._require(SessionOperationCapability.MAINTENANCE)
        return await self._control.compact(custom_instructions)

    def abort_compaction(self) -> None:
        self._require(SessionOperationCapability.MAINTENANCE)
        self._control.abort_compaction()

    def _require(self, capability: SessionOperationCapability) -> None:
        self._availability.require(capability)

    def _require_lifecycle_port(self) -> None:
        self._require(SessionOperationCapability.LIFECYCLE)
        if self._lifecycle is None:
            raise SessionOperationUnavailableError(
                "Session lifecycle operation ports are not bound"
            )


__all__ = [
    "SessionOperationAvailability",
    "SessionOperationCapability",
    "SessionOperationRuntime",
    "SessionOperationUnavailableError",
    "SessionLifecycleOperationPorts",
    "SessionPromptRequest",
]
