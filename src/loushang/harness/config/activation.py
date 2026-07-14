from __future__ import annotations

import asyncio
import inspect
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Sequence,
)
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock, RLock, get_ident
from typing import Generic, Literal, TypeVar

TConfig = TypeVar("TConfig")
TContext = TypeVar("TContext")
_UNBOUND_CONTEXT = object()

ConfigSelector = Callable[[TConfig], object]
ConfigEffect = Callable[[object, TContext], object | Awaitable[object]]
ConfigDisposer = Callable[[TContext], object | Awaitable[object]]
ConfigRefreshMode = Literal["changed", "always"]
ConfigFailureMode = Literal["stop", "continue"]
ConfigActivationOperation = Literal["start", "refresh", "dispose"]
ConfigActivationStatus = Literal["applied", "skipped", "blocked", "failed"]


@dataclass(frozen=True)
class ConfigActivationStep(Generic[TConfig, TContext]):
    name: str
    select: ConfigSelector[TConfig]
    apply: ConfigEffect[TContext]
    depends_on: tuple[str, ...] = ()
    refresh: ConfigRefreshMode = "changed"
    cascade: bool = True
    failure_mode: ConfigFailureMode = "stop"
    dispose: ConfigDisposer[TContext] | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("config activation step name must not be empty")
        object.__setattr__(self, "name", name)
        dependencies = tuple(dependency.strip() for dependency in self.depends_on)
        if any(not dependency for dependency in dependencies):
            raise ValueError("config activation dependencies must not be empty")
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("config activation dependencies must be unique")
        if name in dependencies:
            raise ValueError(f"config activation step {name!r} cannot depend on itself")
        object.__setattr__(self, "depends_on", dependencies)
        if self.refresh not in {"changed", "always"}:
            raise ValueError(f"Unknown config refresh mode: {self.refresh}")
        if self.failure_mode not in {"stop", "continue"}:
            raise ValueError(f"Unknown config failure mode: {self.failure_mode}")


@dataclass(frozen=True)
class ConfigActivationFailure:
    step: str
    operation: ConfigActivationOperation
    error: Exception


@dataclass(frozen=True)
class ConfigActivationStepResult:
    step: str
    status: ConfigActivationStatus


@dataclass(frozen=True)
class ConfigActivationReport:
    revision: int
    operation: ConfigActivationOperation
    results: tuple[ConfigActivationStepResult, ...] = ()
    failures: tuple[ConfigActivationFailure, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    def raise_for_failure(self) -> None:
        if self.failures:
            raise ConfigActivationError(self) from self.failures[0].error


class ConfigActivationError(RuntimeError):
    def __init__(self, report: ConfigActivationReport) -> None:
        failure = report.failures[0]
        super().__init__(
            f"Config activation {report.operation} failed at {failure.step}: "
            f"{failure.error}"
        )
        self.report = report


class ConfigActivationRuntime(Generic[TConfig, TContext]):
    """Order and refresh config effects without owning Product services."""

    def __init__(
        self,
        steps: Sequence[ConfigActivationStep[TConfig, TContext]],
        *,
        rollback_on_start_failure: bool = False,
    ) -> None:
        self._steps = _ordered_steps(steps)
        self._steps_by_name = {step.name: step for step in self._steps}
        self._rollback_on_start_failure = rollback_on_start_failure
        self._selections: dict[str, object] = {}
        self._active_order: list[str] = []
        self._dirty: set[str] = set()
        self._context: object = _UNBOUND_CONTEXT
        self._cleanup_only = False
        self._revision = 0
        self._mode: Literal["sync", "async"] | None = None
        self._mode_lock = Lock()
        self._sync_lock = RLock()
        self._sync_owner: int | None = None
        self._async_lock = asyncio.Lock()
        self._async_owner: asyncio.Task[object] | None = None

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def ordered_names(self) -> tuple[str, ...]:
        return tuple(step.name for step in self._steps)

    def start(self, config: TConfig, context: TContext) -> ConfigActivationReport:
        with self._sync_operation():
            self._bind_start(context)
            return self._run_sync(
                operation="start",
                config=config,
                context=context,
                force=(),
            )

    def refresh(
        self,
        config: TConfig,
        context: TContext,
        *,
        force: Iterable[str] = (),
    ) -> ConfigActivationReport:
        with self._sync_operation():
            self._require_active_context(context, operation="refresh")
            return self._run_sync(
                operation="refresh",
                config=config,
                context=context,
                force=force,
            )

    def dispose(self, context: TContext) -> ConfigActivationReport:
        with self._sync_operation():
            if self._context is _UNBOUND_CONTEXT:
                return self._dispose_sync(context)
            self._require_active_context(context, operation="dispose")
            return self._dispose_sync(context)

    async def astart(
        self,
        config: TConfig,
        context: TContext,
    ) -> ConfigActivationReport:
        async with self._async_operation():
            self._bind_start(context)
            return await self._run_async(
                operation="start",
                config=config,
                context=context,
                force=(),
            )

    async def arefresh(
        self,
        config: TConfig,
        context: TContext,
        *,
        force: Iterable[str] = (),
    ) -> ConfigActivationReport:
        async with self._async_operation():
            self._require_active_context(context, operation="refresh")
            return await self._run_async(
                operation="refresh",
                config=config,
                context=context,
                force=force,
            )

    async def adispose(self, context: TContext) -> ConfigActivationReport:
        async with self._async_operation():
            if self._context is _UNBOUND_CONTEXT:
                return await self._dispose_async(context)
            self._require_active_context(context, operation="dispose")
            return await self._dispose_async(context)

    @contextmanager
    def _sync_operation(self) -> Iterator[None]:
        self._claim_mode("sync")
        owner = get_ident()
        with self._sync_lock:
            if self._sync_owner == owner:
                raise RuntimeError(
                    "config activation runtime does not allow reentrant operations"
                )
            self._sync_owner = owner
            try:
                yield
            finally:
                self._sync_owner = None

    @asynccontextmanager
    async def _async_operation(self) -> AsyncIterator[None]:
        self._claim_mode("async")
        owner = asyncio.current_task()
        if owner is not None and self._async_owner is owner:
            raise RuntimeError(
                "config activation runtime does not allow reentrant operations"
            )
        async with self._async_lock:
            self._async_owner = owner
            try:
                yield
            finally:
                self._async_owner = None

    def _claim_mode(self, mode: Literal["sync", "async"]) -> None:
        with self._mode_lock:
            if self._mode is None:
                self._mode = mode
                return
            if self._mode != mode:
                raise RuntimeError(
                    "config activation runtime cannot mix sync and async operations"
                )

    def _bind_start(self, context: TContext) -> None:
        if self._context is not _UNBOUND_CONTEXT:
            raise RuntimeError(
                "config activation runtime is already started; use refresh or dispose"
            )
        self._context = context
        self._cleanup_only = False

    def _require_active_context(
        self,
        context: TContext,
        *,
        operation: Literal["refresh", "dispose"],
    ) -> None:
        if self._context is _UNBOUND_CONTEXT:
            raise RuntimeError(
                f"config activation runtime must be started before {operation}"
            )
        if self._context is not context:
            raise RuntimeError(
                f"config activation {operation} must use the context passed to start"
            )
        if operation == "refresh" and self._cleanup_only:
            raise RuntimeError("config activation cleanup is incomplete; retry dispose")

    def _run_sync(
        self,
        *,
        operation: Literal["start", "refresh"],
        config: TConfig,
        context: TContext,
        force: Iterable[str],
    ) -> ConfigActivationReport:
        forced = self._validated_force(force)
        revision = self._next_revision()
        results: list[ConfigActivationStepResult] = []
        failures: list[ConfigActivationFailure] = []
        failed: set[str] = set()
        applied: set[str] = set()
        applied_this_run: list[str] = []
        halted = False
        for step in self._steps:
            if halted or any(dependency in failed for dependency in step.depends_on):
                results.append(ConfigActivationStepResult(step.name, "blocked"))
                failed.add(step.name)
                self._dirty.add(step.name)
                continue
            try:
                selection = step.select(config)
                should_apply = self._should_apply(
                    step,
                    operation=operation,
                    selection=selection,
                    forced=forced,
                    applied=applied,
                )
                if not should_apply:
                    results.append(ConfigActivationStepResult(step.name, "skipped"))
                    continue
                outcome = step.apply(selection, context)
                _require_sync(outcome, step=step.name, operation=operation)
            except Exception as exc:
                failures.append(ConfigActivationFailure(step.name, operation, exc))
                results.append(ConfigActivationStepResult(step.name, "failed"))
                failed.add(step.name)
                self._dirty.add(step.name)
                halted = step.failure_mode == "stop"
                continue
            self._record_applied(step, selection)
            applied.add(step.name)
            applied_this_run.append(step.name)
            results.append(ConfigActivationStepResult(step.name, "applied"))
        if failures and operation == "start" and self._rollback_on_start_failure:
            failure_count = len(failures)
            self._cleanup_only = True
            self._rollback_sync(applied_this_run, context, failures)
            self._cleanup_only = len(failures) > failure_count
        return ConfigActivationReport(
            revision=revision,
            operation=operation,
            results=tuple(results),
            failures=tuple(failures),
        )

    async def _run_async(
        self,
        *,
        operation: Literal["start", "refresh"],
        config: TConfig,
        context: TContext,
        force: Iterable[str],
    ) -> ConfigActivationReport:
        forced = self._validated_force(force)
        revision = self._next_revision()
        results: list[ConfigActivationStepResult] = []
        failures: list[ConfigActivationFailure] = []
        failed: set[str] = set()
        applied: set[str] = set()
        applied_this_run: list[str] = []
        halted = False
        for step in self._steps:
            if halted or any(dependency in failed for dependency in step.depends_on):
                results.append(ConfigActivationStepResult(step.name, "blocked"))
                failed.add(step.name)
                self._dirty.add(step.name)
                continue
            try:
                selection = step.select(config)
                should_apply = self._should_apply(
                    step,
                    operation=operation,
                    selection=selection,
                    forced=forced,
                    applied=applied,
                )
                if not should_apply:
                    results.append(ConfigActivationStepResult(step.name, "skipped"))
                    continue
                outcome = step.apply(selection, context)
                if inspect.isawaitable(outcome):
                    await outcome
            except asyncio.CancelledError:
                self._dirty.add(step.name)
                raise
            except Exception as exc:
                failures.append(ConfigActivationFailure(step.name, operation, exc))
                results.append(ConfigActivationStepResult(step.name, "failed"))
                failed.add(step.name)
                self._dirty.add(step.name)
                halted = step.failure_mode == "stop"
                continue
            self._record_applied(step, selection)
            applied.add(step.name)
            applied_this_run.append(step.name)
            results.append(ConfigActivationStepResult(step.name, "applied"))
        if failures and operation == "start" and self._rollback_on_start_failure:
            failure_count = len(failures)
            self._cleanup_only = True
            await self._rollback_async(applied_this_run, context, failures)
            self._cleanup_only = len(failures) > failure_count
        return ConfigActivationReport(
            revision=revision,
            operation=operation,
            results=tuple(results),
            failures=tuple(failures),
        )

    def _should_apply(
        self,
        step: ConfigActivationStep[TConfig, TContext],
        *,
        operation: Literal["start", "refresh"],
        selection: object,
        forced: frozenset[str],
        applied: set[str],
    ) -> bool:
        if operation == "start":
            return True
        if step.name in self._dirty:
            return True
        if step.name in forced or step.refresh == "always":
            return True
        if step.name not in self._selections:
            return True
        if selection != self._selections[step.name]:
            return True
        return any(
            dependency in applied and self._steps_by_name[dependency].cascade
            for dependency in step.depends_on
        )

    def _record_applied(
        self,
        step: ConfigActivationStep[TConfig, TContext],
        selection: object,
    ) -> None:
        try:
            self._selections[step.name] = deepcopy(selection)
        except Exception:
            self._selections[step.name] = selection
        self._dirty.discard(step.name)
        if step.name not in self._active_order:
            self._active_order.append(step.name)

    def _dispose_sync(self, context: TContext) -> ConfigActivationReport:
        if self._context is not _UNBOUND_CONTEXT:
            self._cleanup_only = True
        revision = self._next_revision()
        results: list[ConfigActivationStepResult] = []
        failures: list[ConfigActivationFailure] = []
        protected: set[str] = set()
        for name in reversed(tuple(self._active_order)):
            step = self._steps_by_name[name]
            if name in protected:
                results.append(ConfigActivationStepResult(name, "blocked"))
                continue
            if step.dispose is None:
                results.append(ConfigActivationStepResult(name, "skipped"))
                self._forget(name)
                continue
            try:
                outcome = step.dispose(context)
                _require_sync(outcome, step=name, operation="dispose")
            except Exception as exc:
                failures.append(ConfigActivationFailure(name, "dispose", exc))
                results.append(ConfigActivationStepResult(name, "failed"))
                protected.update(self._dependency_closure(name))
                continue
            results.append(ConfigActivationStepResult(name, "applied"))
            self._forget(name)
        if not failures:
            self._reset_lifecycle()
        return ConfigActivationReport(
            revision=revision,
            operation="dispose",
            results=tuple(results),
            failures=tuple(failures),
        )

    async def _dispose_async(self, context: TContext) -> ConfigActivationReport:
        if self._context is not _UNBOUND_CONTEXT:
            self._cleanup_only = True
        revision = self._next_revision()
        results: list[ConfigActivationStepResult] = []
        failures: list[ConfigActivationFailure] = []
        protected: set[str] = set()
        for name in reversed(tuple(self._active_order)):
            step = self._steps_by_name[name]
            if name in protected:
                results.append(ConfigActivationStepResult(name, "blocked"))
                continue
            if step.dispose is None:
                results.append(ConfigActivationStepResult(name, "skipped"))
                self._forget(name)
                continue
            try:
                outcome = step.dispose(context)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception as exc:
                failures.append(ConfigActivationFailure(name, "dispose", exc))
                results.append(ConfigActivationStepResult(name, "failed"))
                protected.update(self._dependency_closure(name))
                continue
            results.append(ConfigActivationStepResult(name, "applied"))
            self._forget(name)
        if not failures:
            self._reset_lifecycle()
        return ConfigActivationReport(
            revision=revision,
            operation="dispose",
            results=tuple(results),
            failures=tuple(failures),
        )

    def _rollback_sync(
        self,
        names: Iterable[str],
        context: TContext,
        failures: list[ConfigActivationFailure],
    ) -> None:
        protected: set[str] = set()
        for name in reversed(tuple(names)):
            step = self._steps_by_name[name]
            if name in protected:
                continue
            if step.dispose is None:
                protected.update(self._dependency_closure(name))
                continue
            try:
                outcome = step.dispose(context)
                _require_sync(outcome, step=name, operation="dispose")
            except Exception as exc:
                failures.append(ConfigActivationFailure(name, "dispose", exc))
                protected.update(self._dependency_closure(name))
            else:
                self._forget(name)

    async def _rollback_async(
        self,
        names: Iterable[str],
        context: TContext,
        failures: list[ConfigActivationFailure],
    ) -> None:
        protected: set[str] = set()
        for name in reversed(tuple(names)):
            step = self._steps_by_name[name]
            if name in protected:
                continue
            if step.dispose is None:
                protected.update(self._dependency_closure(name))
                continue
            try:
                outcome = step.dispose(context)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception as exc:
                failures.append(ConfigActivationFailure(name, "dispose", exc))
                protected.update(self._dependency_closure(name))
            else:
                self._forget(name)

    def _forget(self, name: str) -> None:
        self._selections.pop(name, None)
        self._dirty.discard(name)
        try:
            self._active_order.remove(name)
        except ValueError:
            return

    def _dependency_closure(self, name: str) -> set[str]:
        dependencies: set[str] = set()
        pending = list(self._steps_by_name[name].depends_on)
        while pending:
            dependency = pending.pop()
            if dependency in dependencies:
                continue
            dependencies.add(dependency)
            pending.extend(self._steps_by_name[dependency].depends_on)
        return dependencies

    def _reset_lifecycle(self) -> None:
        self._active_order.clear()
        self._selections.clear()
        self._dirty.clear()
        self._context = _UNBOUND_CONTEXT
        self._cleanup_only = False

    def _validated_force(self, force: Iterable[str]) -> frozenset[str]:
        forced = frozenset(force)
        unknown = forced.difference(self._steps_by_name)
        if unknown:
            raise KeyError(
                f"Unknown config activation steps: {', '.join(sorted(unknown))}"
            )
        return forced

    def _next_revision(self) -> int:
        self._revision += 1
        return self._revision


def _ordered_steps(
    steps: Sequence[ConfigActivationStep[TConfig, TContext]],
) -> tuple[ConfigActivationStep[TConfig, TContext], ...]:
    declared = tuple(steps)
    by_name: dict[str, ConfigActivationStep[TConfig, TContext]] = {}
    for step in declared:
        if step.name in by_name:
            raise ValueError(f"Duplicate config activation step: {step.name}")
        by_name[step.name] = step
    for step in declared:
        missing = tuple(
            dependency for dependency in step.depends_on if dependency not in by_name
        )
        if missing:
            raise ValueError(
                f"Config activation step {step.name!r} has unknown dependencies: "
                f"{', '.join(missing)}"
            )
    ordered: list[ConfigActivationStep[TConfig, TContext]] = []
    remaining = list(declared)
    resolved: set[str] = set()
    while remaining:
        ready = [
            step
            for step in remaining
            if all(dependency in resolved for dependency in step.depends_on)
        ]
        if not ready:
            names = ", ".join(step.name for step in remaining)
            raise ValueError(f"Config activation dependency cycle: {names}")
        for step in ready:
            ordered.append(step)
            resolved.add(step.name)
            remaining.remove(step)
    return tuple(ordered)


def _require_sync(
    outcome: object,
    *,
    step: str,
    operation: ConfigActivationOperation,
) -> None:
    if not inspect.isawaitable(outcome):
        return
    if inspect.iscoroutine(outcome):
        outcome.close()
    raise TypeError(
        f"Config activation step {step!r} returned an awaitable during sync {operation}"
    )


__all__ = [
    "ConfigActivationError",
    "ConfigActivationFailure",
    "ConfigActivationOperation",
    "ConfigActivationReport",
    "ConfigActivationRuntime",
    "ConfigActivationStatus",
    "ConfigActivationStep",
    "ConfigActivationStepResult",
    "ConfigFailureMode",
    "ConfigRefreshMode",
]
