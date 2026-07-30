"""Package inventory and lifecycle commands for the shared RPC host."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loushang.harness.host.rpc.arguments import optional_string, require_string
from loushang.harness.host.rpc.output import RpcOutput
from loushang.harness.host.rpc.routing import LegacyRpcHandler


@dataclass(frozen=True)
class _LifecycleSpec:
    command: str
    method: str
    unavailable: str
    failure: str
    invalid: str
    failure_code: str
    invalid_code: str


@dataclass(frozen=True)
class _CollectionSpec:
    command: str
    method: str
    data_key: str
    unavailable: str
    failure: str
    invalid: str
    failure_code: str
    invalid_code: str


_LIFECYCLE_SPECS = (
    _LifecycleSpec(
        "materialize_package",
        "materialize_package",
        "Package materialization is not available.",
        "Failed to materialize package",
        "Package materialization returned an invalid response.",
        "package_materialization_failed",
        "invalid_package_materialization_response",
    ),
    _LifecycleSpec(
        "install_package",
        "install_package",
        "Package installation is not available.",
        "Failed to install package",
        "Package installation returned an invalid response.",
        "package_installation_failed",
        "invalid_package_installation_response",
    ),
    _LifecycleSpec(
        "update_package",
        "update_package",
        "Package update is not available.",
        "Failed to update package",
        "Package update returned an invalid response.",
        "package_update_failed",
        "invalid_package_update_response",
    ),
    _LifecycleSpec(
        "remove_package",
        "remove_package",
        "Package removal is not available.",
        "Failed to remove package",
        "Package removal returned an invalid response.",
        "package_removal_failed",
        "invalid_package_removal_response",
    ),
    _LifecycleSpec(
        "uninstall_package",
        "uninstall_package",
        "Package uninstallation is not available.",
        "Failed to uninstall package",
        "Package uninstallation returned an invalid response.",
        "package_uninstallation_failed",
        "invalid_package_uninstallation_response",
    ),
)

_COLLECTION_SPECS = (
    _CollectionSpec(
        "update_packages",
        "update_packages",
        "records",
        "Package update is not available.",
        "Failed to update packages",
        "Package update returned an invalid response.",
        "package_update_failed",
        "invalid_package_update_response",
    ),
    _CollectionSpec(
        "check_package_updates",
        "check_package_updates",
        "updates",
        "Package update check is not available.",
        "Failed to check package updates",
        "Package update check returned an invalid response.",
        "package_update_check_failed",
        "invalid_package_update_check_response",
    ),
)


class RpcPackageCommands:
    """Resolve package capabilities from runtime first, then current session."""

    def __init__(
        self,
        *,
        runtime: object,
        get_session: Callable[[], object],
        output: RpcOutput,
    ) -> None:
        self._runtime = runtime
        self._get_session = get_session
        self._output = output

    def bindings(self) -> tuple[tuple[str, LegacyRpcHandler], ...]:
        return (
            ("get_packages", self.get_packages),
            *(
                (spec.command, self._lifecycle_handler(spec))
                for spec in _LIFECYCLE_SPECS
            ),
            *(
                (spec.command, self._collection_handler(spec))
                for spec in _COLLECTION_SPECS
            ),
        )

    def get_packages(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        catalog_path = optional_string(payload, "catalogPath", "catalog_path")
        method = self._resolve("get_packages")
        if method is None:
            self._output.error(
                request_id=command_id,
                command="get_packages",
                error="Package listing is not available.",
            )
            return
        try:
            packages = method(catalog_path=catalog_path)
        except Exception as error:
            self._output.error(
                request_id=command_id,
                command="get_packages",
                error=f"Failed to query packages: {error}",
                code="package_query_failed",
            )
            return
        if not isinstance(packages, list):
            self._output.error(
                request_id=command_id,
                command="get_packages",
                error="Package listing returned an invalid response.",
                code="invalid_package_query_response",
            )
            return
        self._output.success(
            request_id=command_id,
            command="get_packages",
            data={"packages": packages},
        )

    def _lifecycle_handler(self, spec: _LifecycleSpec) -> LegacyRpcHandler:
        async def handle(
            command_id: str | None, payload: dict[str, Any]
        ) -> None:
            source = require_string(payload, "source")
            method = self._resolve(spec.method)
            if method is None:
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=spec.unavailable,
                )
                return
            try:
                record = method(source)
                if inspect.isawaitable(record):
                    record = await record
            except Exception as error:
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=f"{spec.failure}: {error}",
                    code=spec.failure_code,
                )
                return
            if not isinstance(record, dict):
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=spec.invalid,
                    code=spec.invalid_code,
                )
                return
            if failure := _lifecycle_failure(record):
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=f"{spec.failure}: {failure}",
                    code=spec.failure_code,
                )
                return
            self._output.success(
                request_id=command_id,
                command=spec.command,
                data={"record": record},
            )

        return handle

    def _collection_handler(self, spec: _CollectionSpec) -> LegacyRpcHandler:
        async def handle(
            command_id: str | None, payload: dict[str, Any]
        ) -> None:
            del payload
            method = self._resolve(spec.method)
            if method is None:
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=spec.unavailable,
                )
                return
            try:
                result = method()
                if inspect.isawaitable(result):
                    result = await result
            except Exception as error:
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=f"{spec.failure}: {error}",
                    code=spec.failure_code,
                )
                return
            if not isinstance(result, list):
                self._output.error(
                    request_id=command_id,
                    command=spec.command,
                    error=spec.invalid,
                    code=spec.invalid_code,
                )
                return
            self._output.success(
                request_id=command_id,
                command=spec.command,
                data={spec.data_key: result},
            )

        return handle

    def _resolve(self, method_name: str) -> Callable[..., object] | None:
        method = getattr(self._runtime, method_name, None)
        if callable(method):
            return method
        method = getattr(self._get_session(), method_name, None)
        return method if callable(method) else None


def _lifecycle_failure(record: dict[str, Any]) -> str | None:
    if record.get("lifecycle") != "failed":
        return None
    message = record.get("errorMessage", record.get("error_message"))
    return (
        str(message)
        if isinstance(message, str) and message
        else "Package lifecycle failed."
    )


__all__ = ["RpcPackageCommands"]
