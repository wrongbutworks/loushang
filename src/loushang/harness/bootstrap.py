"""Product-neutral resource bootstrap orchestration.

Products provide resource loaders, extension runtimes, and diagnostic
normalizers.  Harness owns the ordering and the invariant that extension
resource discovery happens after flags have been applied.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.config.activation import (
    ConfigActivationReport,
    ConfigActivationRuntime,
    ConfigActivationStep,
)

LoaderT = TypeVar("LoaderT")
BundleT = TypeVar("BundleT")
ExtensionT = TypeVar("ExtensionT")
DiagnosticT = TypeVar("DiagnosticT")
ActivationConfigT = TypeVar("ActivationConfigT")
ActivationContextT = TypeVar("ActivationContextT")
FlagValues = Mapping[str, bool | str] | None


@dataclass(frozen=True)
class ResourceBootstrapPorts(Generic[LoaderT, BundleT, ExtensionT, DiagnosticT]):
    """Callbacks that bind Product resource and extension semantics."""

    discover_resources: Callable[[LoaderT, Path], BundleT]
    create_extension_runtime: Callable[[BundleT], ExtensionT]
    apply_extension_flags: Callable[[ExtensionT, FlagValues], Sequence[DiagnosticT]]
    rediscover_resources: Callable[[ExtensionT, BundleT], BundleT]
    bundle_diagnostics: Callable[[BundleT], Sequence[DiagnosticT]]
    extension_diagnostics: Callable[[ExtensionT], Sequence[DiagnosticT]]
    normalize_diagnostic: Callable[[DiagnosticT, str, str], DiagnosticT]


@dataclass(frozen=True)
class ResourceBootstrapResult(Generic[BundleT, ExtensionT, DiagnosticT]):
    """Resources, extensions, and normalized diagnostics for one cwd."""

    resource_bundle: BundleT
    extension_runtime: ExtensionT
    diagnostics: tuple[DiagnosticT, ...]


class ResourceBootstrapRuntime(Generic[LoaderT, BundleT, ExtensionT, DiagnosticT]):
    """Run the shared resource/extension bootstrap transaction."""

    def __init__(
        self,
        ports: ResourceBootstrapPorts[LoaderT, BundleT, ExtensionT, DiagnosticT],
    ) -> None:
        self._ports = ports

    def prepare(
        self,
        *,
        loader: LoaderT,
        cwd: str | Path,
        extension_flags: FlagValues = None,
    ) -> ResourceBootstrapResult[BundleT, ExtensionT, DiagnosticT]:
        resolved_cwd = Path(cwd).expanduser().resolve(strict=False)
        bundle = self._ports.discover_resources(loader, resolved_cwd)
        loader_diagnostics = tuple(self._ports.bundle_diagnostics(bundle))
        extension_runtime = self._ports.create_extension_runtime(bundle)
        flag_diagnostics = tuple(
            self._ports.apply_extension_flags(extension_runtime, extension_flags)
        )
        bundle = self._ports.rediscover_resources(extension_runtime, bundle)
        diagnostics = tuple(
            self._ports.normalize_diagnostic(diagnostic, phase, source)
            for phase, source, source_diagnostics in (
                ("resource_loading", "loader", loader_diagnostics),
                (
                    "resource_loading",
                    "extensions",
                    self._ports.extension_diagnostics(extension_runtime),
                ),
                ("resource_loading", "bootstrap", flag_diagnostics),
            )
            for diagnostic in source_diagnostics
        )
        return ResourceBootstrapResult(
            resource_bundle=bundle,
            extension_runtime=extension_runtime,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True)
class BootstrapActivationPlan(Generic[ActivationConfigT, ActivationContextT]):
    """Product-provided steps for one ordered bootstrap transaction."""

    steps: tuple[ConfigActivationStep[ActivationConfigT, ActivationContextT], ...]
    rollback_on_start_failure: bool = True


@dataclass(frozen=True)
class BootstrapActivationResult(Generic[ActivationContextT]):
    """Activation context together with its structured execution report."""

    context: ActivationContextT
    report: ConfigActivationReport


class BootstrapActivationRuntime(Generic[ActivationConfigT, ActivationContextT]):
    """Run a product bootstrap plan as one ordered activation transaction."""

    def __init__(
        self,
        plan: BootstrapActivationPlan[ActivationConfigT, ActivationContextT],
    ) -> None:
        self._runtime = ConfigActivationRuntime(
            plan.steps,
            rollback_on_start_failure=plan.rollback_on_start_failure,
        )

    def activate(
        self,
        config: ActivationConfigT,
        context: ActivationContextT,
    ) -> BootstrapActivationResult[ActivationContextT]:
        report = self._runtime.start(config, context)
        return BootstrapActivationResult(context=context, report=report)

    @property
    def ordered_step_names(self) -> tuple[str, ...]:
        return self._runtime.ordered_names


__all__ = [
    "ResourceBootstrapPorts",
    "ResourceBootstrapResult",
    "ResourceBootstrapRuntime",
    "BootstrapActivationPlan",
    "BootstrapActivationResult",
    "BootstrapActivationRuntime",
]
