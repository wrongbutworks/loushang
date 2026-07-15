from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, MutableMapping

from loushang.harness.config.values import (
    ConfigCommandResult,
)
from loushang.harness.config.values import (
    ConfigValueResolver as HarnessConfigValueResolver,
)


class ConfigValueResolver(HarnessConfigValueResolver):
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        runner=None,
        cache: MutableMapping[str, str | None] | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        super().__init__(
            env=env,
            runner=_run_config_command if runner is None else runner,
            cache=cache,
            timeout_seconds=timeout_seconds,
        )


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
