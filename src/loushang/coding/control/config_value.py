from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class ConfigCommandResult:
    ok: bool
    stdout: bytes | str = ""


ConfigCommandRunner = Callable[[str], ConfigCommandResult]


class ConfigValueResolver:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        runner: Callable[..., ConfigCommandResult] | None = None,
        cache: MutableMapping[str, str | None] | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._env = env
        self._runner = _run_config_command if runner is None else runner
        self._cache = cache if cache is not None else {}
        self._timeout_seconds = timeout_seconds

    def resolve(self, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("!"):
            return self._resolve_command(value)
        environment = environ if self._env is None else self._env
        return environment.get(value, value)

    def _resolve_command(self, value: str) -> str | None:
        if value in self._cache:
            return self._cache[value]
        command = value[1:].strip()
        if not command:
            self._cache[value] = None
            return None
        result = self._runner(command, timeout_seconds=self._timeout_seconds)
        resolved = _stdout_text(result).strip() if result.ok else None
        self._cache[value] = resolved or None
        return self._cache[value]


_PROCESS_CACHE: dict[str, str | None] = {}


def resolve_config_value(
    value: str | None,
    *,
    env: Mapping[str, str] | None = None,
    runner: Callable[..., ConfigCommandResult] | None = None,
    timeout_seconds: float = 10,
) -> str | None:
    return ConfigValueResolver(
        env=env,
        runner=runner,
        cache=_PROCESS_CACHE,
        timeout_seconds=timeout_seconds,
    ).resolve(value)


def clear_config_value_cache() -> None:
    _PROCESS_CACHE.clear()


def _stdout_text(result: ConfigCommandResult) -> str:
    return result.stdout.decode("utf-8", "replace") if isinstance(result.stdout, bytes) else result.stdout


def _run_config_command(command: str, *, timeout_seconds: float = 10) -> ConfigCommandResult:
    try:
        result = subprocess.run(
            command,
            check=False,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return ConfigCommandResult(ok=False)
    return ConfigCommandResult(ok=result.returncode == 0, stdout=result.stdout)


__all__ = [
    "ConfigCommandResult",
    "ConfigValueResolver",
    "clear_config_value_cache",
    "resolve_config_value",
]
