"""Product-neutral binding of parsed CLI commands to Product handlers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from loushang.harness.cli.types import CliInvocation, CliProfileError

CliOperationHandler: TypeAlias = Callable[
    [CliInvocation], object | Awaitable[object]
]


class CliOperationUnavailableError(LookupError):
    """Raised when a profile command has no bound Product operation."""


@dataclass(frozen=True, slots=True)
class CliOperationSpec:
    """One command-to-handler binding supplied by a Product host."""

    operation_id: str
    handler: CliOperationHandler
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise CliProfileError("CLI operation id must be non-empty")
        if not callable(self.handler):
            raise TypeError("CLI operation handler must be callable")
        if any(not alias or alias.startswith("-") for alias in self.aliases):
            raise CliProfileError("CLI operation aliases must be command names")

    @property
    def names(self) -> tuple[str, ...]:
        return (self.operation_id, *self.aliases)


class CliOperationRuntime:
    """Resolve a parsed command and invoke the injected Product handler.

    This runtime does not know about sessions, transports, JSON, or Product
    command semantics.  Channel or a Product host owns framing and error
    projection; Harness owns only this binding and duplicate detection.
    """

    def __init__(self, operations: Mapping[str, CliOperationSpec]) -> None:
        by_name: dict[str, CliOperationSpec] = {}
        for key, operation in operations.items():
            if key != operation.operation_id:
                raise CliProfileError(
                    "CLI operation mapping keys must match operation_id"
                )
            for name in operation.names:
                if name in by_name:
                    raise CliProfileError(f"duplicate CLI operation name: {name!r}")
                by_name[name] = operation
        self._operations = by_name

    async def dispatch(self, invocation: CliInvocation) -> object:
        if invocation.command_id is None:
            raise CliOperationUnavailableError(
                "CLI invocation does not identify a command operation"
            )
        return await self.dispatch_name(invocation.command_id, invocation)

    async def dispatch_name(
        self,
        operation_name: str,
        invocation: CliInvocation,
    ) -> object:
        try:
            operation = self._operations[operation_name]
        except KeyError as exc:
            raise CliOperationUnavailableError(
                f"CLI operation is not bound: {operation_name}"
            ) from exc
        result = operation.handler(invocation)
        if inspect.isawaitable(result):
            return await result
        return result


__all__ = [
    "CliOperationHandler",
    "CliOperationRuntime",
    "CliOperationSpec",
    "CliOperationUnavailableError",
]
