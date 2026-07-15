from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Never, Protocol, TypeAlias, TypeVar
from uuid import uuid4

T = TypeVar("T")
MaybeAwaitable: TypeAlias = T | Awaitable[T]


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    arguments: Mapping[str, Any]
    cwd: str | None = None
    reason: str | None = None
    policy_code: str | None = None
    policy_decision: object | None = None
    action_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise ValueError("ApprovalRequest tool_name must be a non-empty string")
        _validate_optional_string(self.cwd, "ApprovalRequest cwd")
        _validate_optional_string(self.reason, "ApprovalRequest reason")
        _validate_optional_string(self.policy_code, "ApprovalRequest policy_code")
        _validate_optional_string(self.action_id, "ApprovalRequest action_id")
        if self.action_id == "":
            raise ValueError("ApprovalRequest action_id must not be empty")
        object.__setattr__(
            self,
            "arguments",
            _freeze_mapping(self.arguments),
        )


@dataclass(frozen=True)
class ApprovalDecision:
    disposition: Literal["allow", "deny"]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in {"allow", "deny"}:
            raise ValueError(
                f"Unsupported approval decision disposition: {self.disposition}"
            )
        _validate_optional_string(self.reason, "ApprovalDecision reason")

    @classmethod
    def allow(cls) -> "ApprovalDecision":
        return cls(disposition="allow")

    @classmethod
    def deny(cls, reason: str | None = None) -> "ApprovalDecision":
        return cls(disposition="deny", reason=reason)


class ApprovalResolver(Protocol):
    def resolve(self, request: ApprovalRequest) -> MaybeAwaitable[ApprovalDecision]: ...


class ApprovalPresenter(Protocol):
    def present(self, request: ApprovalRequest) -> MaybeAwaitable[None]: ...


class ApprovalRequestCollisionError(RuntimeError):
    def __init__(self, action_id: str) -> None:
        super().__init__(
            f"Approval action id was already presented by this broker: {action_id}"
        )
        self.action_id = action_id


@dataclass(frozen=True)
class DenyApprovalResolver:
    def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision.deny(
            request.reason or f"Tool {request.tool_name} requires approval"
        )


@dataclass(frozen=True)
class HeadlessApprovalResolver:
    mode: Literal["allow", "deny"] = "deny"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"allow", "deny"}:
            raise ValueError(f"Unsupported headless approval mode: {self.mode}")

    def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        if self.mode == "allow":
            return ApprovalDecision.allow()
        return ApprovalDecision.deny(
            self.reason
            or request.reason
            or f"Tool {request.tool_name} requires approval"
        )


async def resolve_approval(
    resolver: ApprovalResolver | None,
    request: ApprovalRequest,
) -> ApprovalDecision:
    resolved = resolver or DenyApprovalResolver()
    result = resolved.resolve(request)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ApprovalDecision):
        raise TypeError(
            f"ApprovalResolver returned {type(result).__name__}, expected ApprovalDecision"
        )
    result.__post_init__()
    return result


def approval_request_to_dict(request: ApprovalRequest) -> dict[str, object]:
    """Project a request into mutable JSON-compatible Product data."""

    if not isinstance(request, ApprovalRequest):
        raise TypeError("request must be an ApprovalRequest")
    return {
        "tool_name": request.tool_name,
        "arguments": _thaw_value(request.arguments),
        "cwd": request.cwd,
        "reason": request.reason,
        "policy_code": request.policy_code,
        "action_id": request.action_id,
    }


def ensure_approval_action_id(request: ApprovalRequest) -> ApprovalRequest:
    """Return an immutable request with a correlation id."""

    if request.action_id:
        return request
    return replace(request, action_id=f"approval-{uuid4().hex}")


@dataclass
class _PendingApproval:
    request: ApprovalRequest
    future: asyncio.Future[ApprovalDecision] = field(compare=False, repr=False)
    accepting_presenter_results: bool = field(default=True, compare=False)


class ApprovalBroker:
    """Event-loop-confined lifecycle manager for interactive approvals."""

    def __init__(
        self,
        *,
        fallback: ApprovalResolver,
        timeout_seconds: float | None = None,
    ) -> None:
        if fallback is self:
            raise ValueError("ApprovalBroker cannot use itself as fallback")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._fallback = fallback
        self._timeout_seconds = timeout_seconds
        self._presenter: ApprovalPresenter | None = None
        self._pending: dict[str, _PendingApproval] = {}
        self._presented_action_ids: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._disposed = False

    def set_presenter(self, presenter: ApprovalPresenter | None) -> None:
        if self._disposed and presenter is not None:
            raise RuntimeError("ApprovalBroker is disposed")
        self._presenter = presenter

    def pending_requests(self) -> tuple[ApprovalRequest, ...]:
        return tuple(pending.request for pending in self._pending.values())

    async def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        request = ensure_approval_action_id(request)
        action_id = request.action_id
        assert action_id is not None
        if action_id in self._pending:
            raise ApprovalRequestCollisionError(action_id)
        if self._disposed or self._presenter is None:
            return await resolve_approval(self._fallback, request)
        if action_id in self._presented_action_ids:
            raise ApprovalRequestCollisionError(action_id)

        loop = self._capture_loop()
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        pending = _PendingApproval(request=request, future=future)
        self._presented_action_ids.add(action_id)
        self._pending[action_id] = pending
        presenter = self._presenter
        assert presenter is not None
        try:
            waiter = self._present_and_wait(
                presenter,
                request,
                future,
            )
            if self._timeout_seconds is None:
                return await waiter
            waiter_task = asyncio.create_task(waiter)
            try:
                done, _ = await asyncio.wait(
                    (waiter_task,),
                    timeout=self._timeout_seconds,
                )
                if waiter_task in done:
                    return waiter_task.result()
                pending.accepting_presenter_results = False
                await _cancel_child_task(waiter_task)
                if future.done():
                    return future.result()
                return await self._resolve_fallback_or_pending_decision(
                    request,
                    future,
                )
            finally:
                if not waiter_task.done():
                    await _cancel_child_task(waiter_task)
        finally:
            current = self._pending.get(action_id)
            if current is pending:
                self._pending.pop(action_id, None)
            if not future.done():
                future.cancel()
            _dismiss_presented_request(presenter, request)

    async def _present_and_wait(
        self,
        presenter: ApprovalPresenter,
        request: ApprovalRequest,
        future: asyncio.Future[ApprovalDecision],
    ) -> ApprovalDecision:
        presented = presenter.present(request)
        if not inspect.isawaitable(presented):
            return await asyncio.shield(future)

        presentation_task = asyncio.ensure_future(presented)
        try:
            done, _ = await asyncio.wait(
                (presentation_task, future),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if presentation_task in done:
                await presentation_task
                return await asyncio.shield(future)
            return future.result()
        finally:
            if not presentation_task.done():
                _cancel_detached_presentation(
                    presentation_task,
                    presenter=presenter,
                    request=request,
                )

    async def _resolve_fallback_or_pending_decision(
        self,
        request: ApprovalRequest,
        future: asyncio.Future[ApprovalDecision],
    ) -> ApprovalDecision:
        fallback_task = asyncio.create_task(resolve_approval(self._fallback, request))
        try:
            done, _ = await asyncio.wait(
                (fallback_task, future),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if future in done:
                if fallback_task in done:
                    with suppress(asyncio.CancelledError, Exception):
                        fallback_task.result()
                return future.result()
            return fallback_task.result()
        finally:
            if not fallback_task.done():
                _cancel_detached_task(fallback_task)

    def resolve_request(
        self,
        action_id: str,
        decision: ApprovalDecision,
    ) -> bool:
        _validate_approval_decision(decision)
        self._require_loop_if_pending()
        pending = self._pending.get(action_id)
        if (
            pending is None
            or not pending.accepting_presenter_results
            or pending.future.done()
        ):
            return False
        pending.future.set_result(decision)
        return True

    def cancel_request(
        self,
        action_id: str,
        decision: ApprovalDecision,
    ) -> bool:
        _validate_approval_decision(decision)
        self._require_loop_if_pending()
        pending = self._pending.get(action_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result(decision)
        return True

    def cancel_all(self, decision: ApprovalDecision) -> int:
        _validate_approval_decision(decision)
        self._require_loop_if_pending()
        completed = 0
        for pending in tuple(self._pending.values()):
            if pending.future.done():
                continue
            pending.future.set_result(decision)
            completed += 1
        return completed

    def dispose(self, decision: ApprovalDecision) -> int:
        _validate_approval_decision(decision)
        if self._disposed:
            return 0
        self._require_loop_if_pending()
        self._disposed = True
        self._presenter = None
        completed = self.cancel_all(decision)
        self._presented_action_ids.clear()
        return completed

    def _capture_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            if self._pending:
                raise RuntimeError("ApprovalBroker cannot be used across event loops")
            self._loop = loop
        return loop

    def _require_loop_if_pending(self) -> None:
        if not self._pending:
            return
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            raise RuntimeError(
                "ApprovalBroker must be resolved on its owning event loop"
            )


class _FrozenDict(dict[str, Any]):
    """Immutable dict snapshot that remains compatible with serializers."""

    def _immutable(self, *args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise TypeError("frozen mapping does not support mutation")

    def __setitem__(self, key: str, value: Any) -> Never:
        self._immutable(key, value)

    def __delitem__(self, key: str) -> Never:
        self._immutable(key)

    def clear(self) -> Never:
        self._immutable()

    def pop(self, key: str, default: Any = None) -> Never:
        self._immutable(key, default)

    def popitem(self) -> Never:
        self._immutable()

    def setdefault(self, key: str, default: Any = None) -> Never:
        self._immutable(key, default)

    def update(self, *args: Any, **kwargs: Any) -> Never:
        self._immutable(*args, **kwargs)

    def __ior__(self, other: object) -> Never:
        self._immutable(other)

    def __reduce__(self) -> tuple[type[_FrozenDict], tuple[dict[str, Any]]]:
        return type(self), (dict(self),)

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenDict:
        copied = type(self)(
            {deepcopy(key, memo): deepcopy(value, memo) for key, value in self.items()}
        )
        memo[id(self)] = copied
        return copied


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise TypeError("ApprovalRequest arguments must be a mapping")
    return _FrozenDict(
        {
            _require_string_key(key): _freeze_value(value)
            for key, value in values.items()
        }
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict(
            {
                _require_string_key(key): _freeze_value(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise TypeError(
        "ApprovalRequest argument values must be JSON-compatible mappings, "
        "sequences, strings, numbers, booleans, or null"
    )


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


def _validate_optional_string(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")


def _require_string_key(key: object) -> str:
    if not isinstance(key, str):
        raise TypeError("ApprovalRequest argument mapping keys must be strings")
    return key


def _validate_approval_decision(decision: object) -> ApprovalDecision:
    if not isinstance(decision, ApprovalDecision):
        raise TypeError("decision must be an ApprovalDecision")
    decision.__post_init__()
    return decision


def _cancel_detached_task(task: asyncio.Future[Any]) -> None:
    task.cancel()
    task.add_done_callback(_consume_detached_result)


async def _cancel_child_task(task: asyncio.Future[Any]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise


def _cancel_detached_presentation(
    task: asyncio.Future[Any],
    *,
    presenter: ApprovalPresenter,
    request: ApprovalRequest,
) -> None:
    task.cancel()

    def _finish_presentation(completed: asyncio.Future[Any]) -> None:
        _consume_detached_result(completed)
        _dismiss_presented_request(presenter, request)

    task.add_done_callback(_finish_presentation)


def _dismiss_presented_request(
    presenter: ApprovalPresenter,
    request: ApprovalRequest,
) -> None:
    try:
        dismiss = getattr(presenter, "dismiss", None)
        if not callable(dismiss):
            return
        result = dismiss(request)
        if inspect.isawaitable(result):
            task = asyncio.ensure_future(result)
            task.add_done_callback(_consume_detached_result)
    except asyncio.CancelledError:
        return
    except Exception:
        return


def _consume_detached_result(completed: asyncio.Future[Any]) -> None:
    with suppress(asyncio.CancelledError, Exception):
        completed.result()


__all__ = [
    "ApprovalBroker",
    "ApprovalDecision",
    "ApprovalPresenter",
    "ApprovalRequest",
    "ApprovalRequestCollisionError",
    "ApprovalResolver",
    "DenyApprovalResolver",
    "HeadlessApprovalResolver",
    "MaybeAwaitable",
    "approval_request_to_dict",
    "ensure_approval_action_id",
    "resolve_approval",
]
