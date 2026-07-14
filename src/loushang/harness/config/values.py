from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class ConfigCommandResult:
    ok: bool
    stdout: bytes | str = ""


ConfigCommandRunner = Callable[..., ConfigCommandResult]


class ConfigValueResolver:
    """Resolve config references while leaving command execution to the Product."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        runner: ConfigCommandRunner | None = None,
        cache: MutableMapping[str, str | None] | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._env = env
        self._runner = runner
        self._cache = cache if cache is not None else {}
        self._timeout_seconds = timeout_seconds

    def resolve(self, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("!"):
            return self._resolve_command(value)
        environment = environ if self._env is None else self._env
        return environment.get(value, value)

    def clear(self) -> None:
        self._cache.clear()

    def _resolve_command(self, value: str) -> str | None:
        if value in self._cache:
            return self._cache[value]
        command = value[1:].strip()
        if not command or self._runner is None:
            self._cache[value] = None
            return None
        result = self._runner(command, timeout_seconds=self._timeout_seconds)
        resolved = _stdout_text(result).strip() if result.ok else None
        self._cache[value] = resolved or None
        return self._cache[value]


def _stdout_text(result: ConfigCommandResult) -> str:
    if isinstance(result.stdout, bytes):
        return result.stdout.decode("utf-8", "replace")
    return result.stdout


__all__ = [
    "ConfigCommandResult",
    "ConfigCommandRunner",
    "ConfigValueResolver",
]
