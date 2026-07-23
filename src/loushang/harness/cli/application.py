"""Product-neutral application coordinator for standard Agent CLI hosts."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager, redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TextIO, TypeAlias, TypeVar, cast

from loushang.harness.cli.launch import (
    CliLaunchPlan,
    cli_output_guard_enabled,
    cli_static_error,
)

ArgsT = TypeVar("ArgsT")
StateT = TypeVar("StateT")
RuntimeT = TypeVar("RuntimeT")
SessionT = TypeVar("SessionT")
ResultT = TypeVar("ResultT")

CliMaybeAsync: TypeAlias = ResultT | Awaitable[ResultT]


@dataclass(frozen=True, slots=True)
class CliParseResult(Generic[ArgsT]):
    args: ArgsT | None
    exit_code: int = 2


@dataclass(frozen=True, slots=True)
class CliPhaseResult(Generic[ResultT]):
    """A phase either continues with a value or exits with a code."""

    value: ResultT | None = None
    exit_code: int | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.exit_code is None):
            raise ValueError("CLI phase result must contain one value or exit code")

    @classmethod
    def continue_with(cls, value: ResultT) -> "CliPhaseResult[ResultT]":
        return cls(value=value)

    @classmethod
    def exit(cls, exit_code: int) -> "CliPhaseResult[ResultT]":
        return cls(exit_code=exit_code)


@dataclass(frozen=True, slots=True)
class CliBootstrapContext(Generic[ArgsT]):
    raw_argv: tuple[str, ...]
    args: ArgsT
    launch_plan: CliLaunchPlan
    project_root: Path
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO


@dataclass(frozen=True, slots=True)
class CliRuntimeContext(Generic[ArgsT, StateT, RuntimeT]):
    bootstrap: CliBootstrapContext[ArgsT]
    state: StateT
    runtime: RuntimeT


@dataclass(frozen=True, slots=True)
class CliSessionContext(Generic[ArgsT, StateT, RuntimeT, SessionT]):
    bootstrap: CliBootstrapContext[ArgsT]
    args: ArgsT
    launch_plan: CliLaunchPlan
    state: StateT
    runtime: RuntimeT
    session: SessionT


CliOutputGuard: TypeAlias = Callable[[bool], AbstractContextManager[None]]


@dataclass(frozen=True)
class CliApplicationPorts(Generic[ArgsT, StateT, RuntimeT, SessionT]):
    """Product bindings for the shared CLI application phase order."""

    parse_args: Callable[
        [Sequence[str], TextIO, Mapping[str, object] | None, bool],
        CliParseResult[ArgsT],
    ]
    initialize_args: Callable[[ArgsT], None]
    launch_plan: Callable[[ArgsT], CliLaunchPlan]
    args_cwd: Callable[[ArgsT], str | None]
    early_operation: Callable[
        [CliBootstrapContext[ArgsT]], CliMaybeAsync[int | None]
    ]
    validated_operation: Callable[
        [CliBootstrapContext[ArgsT]], CliMaybeAsync[int | None]
    ]
    prepare_state: Callable[
        [CliBootstrapContext[ArgsT]], CliMaybeAsync[CliPhaseResult[StateT]]
    ]
    startup_context: Callable[
        [CliBootstrapContext[ArgsT], StateT], AbstractContextManager[None]
    ]
    build_runtime: Callable[
        [CliBootstrapContext[ArgsT], StateT], CliMaybeAsync[RuntimeT]
    ]
    runtime_operation: Callable[
        [CliRuntimeContext[ArgsT, StateT, RuntimeT]],
        CliMaybeAsync[int | None],
    ]
    resolve_session: Callable[
        [CliRuntimeContext[ArgsT, StateT, RuntimeT]],
        CliMaybeAsync[SessionT | None],
    ]
    collect_extension_flags: Callable[[SessionT], Mapping[str, object]]
    configure_session: Callable[
        [CliSessionContext[ArgsT, StateT, RuntimeT, SessionT]],
        CliMaybeAsync[int | None],
    ]
    session_operations: Callable[
        [CliSessionContext[ArgsT, StateT, RuntimeT, SessionT]],
        CliMaybeAsync[int | None],
    ]
    run_host: Callable[
        [CliSessionContext[ArgsT, StateT, RuntimeT, SessionT]],
        CliMaybeAsync[int],
    ]
    output_guard: CliOutputGuard
    format_error: Callable[[BaseException], str] = str


class CliApplicationRuntime(Generic[ArgsT, StateT, RuntimeT, SessionT]):
    """Run the standard two-pass Agent CLI application lifecycle."""

    def __init__(
        self,
        ports: CliApplicationPorts[ArgsT, StateT, RuntimeT, SessionT],
    ) -> None:
        self._ports = ports

    async def run(
        self,
        argv: Sequence[str],
        *,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
        cwd: str | Path | None = None,
    ) -> int:
        raw_argv = tuple(argv)
        parsed = self._ports.parse_args(raw_argv, stderr, None, True)
        if parsed.args is None:
            return parsed.exit_code
        bootstrap_args = parsed.args
        self._ports.initialize_args(bootstrap_args)
        project_root = Path(
            cwd or self._ports.args_cwd(bootstrap_args) or Path.cwd()
        ).resolve()
        bootstrap = CliBootstrapContext(
            raw_argv=raw_argv,
            args=bootstrap_args,
            launch_plan=self._ports.launch_plan(bootstrap_args),
            project_root=project_root,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )

        early_result = await _resolve(self._ports.early_operation(bootstrap))
        if early_result is not None:
            return early_result
        static_error = cli_static_error(bootstrap.launch_plan)
        if static_error is not None:
            stderr.write(f"Error: {static_error}.\n")
            return 2
        validated_result = await _resolve(
            self._ports.validated_operation(bootstrap)
        )
        if validated_result is not None:
            return validated_result

        with self._ports.output_guard(
            cli_output_guard_enabled(bootstrap.launch_plan)
        ):
            prepared = await _resolve(self._ports.prepare_state(bootstrap))
        if prepared.exit_code is not None:
            return prepared.exit_code
        state = cast(StateT, prepared.value)

        with self._ports.startup_context(bootstrap, state):
            with self._ports.output_guard(
                cli_output_guard_enabled(bootstrap.launch_plan)
            ):
                runtime = await _resolve(
                    self._ports.build_runtime(bootstrap, state)
                )
            runtime_context = CliRuntimeContext(
                bootstrap=bootstrap,
                state=state,
                runtime=runtime,
            )
            with self._ports.output_guard(
                cli_output_guard_enabled(
                    self._ports.launch_plan(bootstrap_args)
                )
            ):
                runtime_result = await _resolve(
                    self._ports.runtime_operation(runtime_context)
                )
            if runtime_result is not None:
                return runtime_result
            try:
                with self._ports.output_guard(
                    cli_output_guard_enabled(bootstrap.launch_plan)
                ):
                    session = await _resolve(
                        self._ports.resolve_session(runtime_context)
                    )
            except (
                FileNotFoundError,
                NotADirectoryError,
                RuntimeError,
                ValueError,
            ) as error:
                stderr.write(f"Error: {self._ports.format_error(error)}\n")
                return 1
        if session is None:
            return 2

        extension_flags = self._ports.collect_extension_flags(session)
        parsed = self._ports.parse_args(
            raw_argv,
            stderr,
            extension_flags,
            False,
        )
        if parsed.args is None:
            return parsed.exit_code
        args = parsed.args
        session_context = CliSessionContext(
            bootstrap=bootstrap,
            args=args,
            launch_plan=self._ports.launch_plan(args),
            state=state,
            runtime=runtime,
            session=session,
        )
        with self._ports.output_guard(
            cli_output_guard_enabled(session_context.launch_plan)
        ):
            configure_result = await _resolve(
                self._ports.configure_session(session_context)
            )
            if configure_result is not None:
                return configure_result
            operation_result = await _resolve(
                self._ports.session_operations(session_context)
            )
            if operation_result is not None:
                return operation_result
            return await _resolve(self._ports.run_host(session_context))


def capture_cli_parse(
    parser: Callable[..., ArgsT],
    argv: Sequence[str],
    stderr: TextIO,
    extension_flags: Mapping[str, object] | None,
    allow_unknown: bool,
) -> CliParseResult[ArgsT]:
    """Run a Product argparse adapter without taking ownership of process stderr."""

    try:
        with redirect_stderr(stderr):
            return CliParseResult(
                parser(
                    argv,
                    extension_flags=extension_flags,
                    allow_unknown=allow_unknown,
                )
            )
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 2
        return CliParseResult(args=None, exit_code=code)


def invoke_cli_builder(
    builder: Callable[..., ResultT],
    *,
    required: Mapping[str, object],
    optional: Mapping[str, object] | None = None,
) -> ResultT:
    """Invoke a Product builder with only supported additive keywords."""

    kwargs = dict(required)
    for name, value in (optional or {}).items():
        if _accepts_keyword(builder, name):
            kwargs[name] = value
    return builder(**kwargs)


def format_cli_error(error: BaseException) -> str:
    filename = getattr(error, "filename", None)
    if isinstance(error, OSError):
        strerror = getattr(error, "strerror", None)
        if filename is not None and strerror:
            return f"{strerror}: {filename}"
    return str(error)


def _accepts_keyword(callback: Callable[..., object], name: str) -> bool:
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        return False
    parameter = parameters.get(name)
    if parameter is not None and parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }:
        return True
    return any(
        candidate.kind is inspect.Parameter.VAR_KEYWORD
        for candidate in parameters.values()
    )


async def _resolve(value: CliMaybeAsync[ResultT]) -> ResultT:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "CliApplicationPorts",
    "CliApplicationRuntime",
    "CliBootstrapContext",
    "CliOutputGuard",
    "CliParseResult",
    "CliPhaseResult",
    "CliRuntimeContext",
    "CliSessionContext",
    "capture_cli_parse",
    "format_cli_error",
    "invoke_cli_builder",
]
