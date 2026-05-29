from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import ModuleType


DEFAULT_SDK_ENTRY_NAMES: tuple[str, ...] = (
    "create_services",
    "create_agent_session_services",
    "create_agent_session",
    "create_agent_session_result",
    "create_agent_session_from_services",
    "create_agent_session_runtime",
)


@dataclass(frozen=True)
class SdkSurfaceSnapshot:
    export_names: tuple[str, ...]
    entry_signatures: Mapping[str, tuple[str, ...]]
    missing_exports: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_exports

    def to_dict(self) -> dict[str, object]:
        return {
            "export_names": list(self.export_names),
            "entry_signatures": {
                name: list(parameters) for name, parameters in self.entry_signatures.items()
            },
            "missing_exports": list(self.missing_exports),
        }


@dataclass(frozen=True)
class SdkSurfaceCompatibilityReport:
    missing_exports: tuple[str, ...] = ()
    missing_entries: tuple[str, ...] = ()
    signature_mismatches: Mapping[str, Mapping[str, tuple[str, ...]]] = field(default_factory=dict)
    broken_exports: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not (
            self.missing_exports
            or self.missing_entries
            or self.signature_mismatches
            or self.broken_exports
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "missing_exports": list(self.missing_exports),
            "missing_entries": list(self.missing_entries),
            "signature_mismatches": {
                name: {
                    "expected": list(values.get("expected", ())),
                    "actual": list(values.get("actual", ())),
                }
                for name, values in self.signature_mismatches.items()
            },
            "broken_exports": list(self.broken_exports),
        }


def get_sdk_surface_snapshot(
    module: ModuleType | None = None,
    *,
    entry_names: Sequence[str] = DEFAULT_SDK_ENTRY_NAMES,
) -> SdkSurfaceSnapshot:
    target = module or importlib.import_module("loushang.coding")
    export_names = tuple(getattr(target, "__all__", ()))
    missing_exports = tuple(name for name in export_names if not hasattr(target, name))
    entry_signatures: dict[str, tuple[str, ...]] = {}
    for name in entry_names:
        value = getattr(target, name, None)
        if callable(value):
            entry_signatures[name] = tuple(inspect.signature(value).parameters)
    return SdkSurfaceSnapshot(
        export_names=export_names,
        entry_signatures=entry_signatures,
        missing_exports=missing_exports,
    )


def check_sdk_surface_compatibility(
    module: ModuleType | None = None,
    *,
    required_exports: Sequence[str] = (),
    required_entry_signatures: Mapping[str, Sequence[str]] | None = None,
) -> SdkSurfaceCompatibilityReport:
    entry_signatures = required_entry_signatures or {}
    compatibility_entry_names = (
        *DEFAULT_SDK_ENTRY_NAMES,
        *(name for name in entry_signatures if name not in DEFAULT_SDK_ENTRY_NAMES),
    )
    snapshot = get_sdk_surface_snapshot(
        module,
        entry_names=compatibility_entry_names,
    )
    export_names = set(snapshot.export_names)
    target = module or importlib.import_module("loushang.coding")
    missing_exports = tuple(
        name
        for name in required_exports
        if name not in export_names or not hasattr(target, name)
    )
    missing_entries = tuple(name for name in entry_signatures if name not in snapshot.entry_signatures)
    signature_mismatches: dict[str, dict[str, tuple[str, ...]]] = {}
    for name, expected in entry_signatures.items():
        actual = snapshot.entry_signatures.get(name)
        if actual is None:
            continue
        expected_tuple = tuple(expected)
        if actual != expected_tuple:
            signature_mismatches[name] = {
                "expected": expected_tuple,
                "actual": actual,
            }
    return SdkSurfaceCompatibilityReport(
        missing_exports=missing_exports,
        missing_entries=missing_entries,
        signature_mismatches=signature_mismatches,
        broken_exports=snapshot.missing_exports,
    )


__all__ = [
    "DEFAULT_SDK_ENTRY_NAMES",
    "SdkSurfaceCompatibilityReport",
    "SdkSurfaceSnapshot",
    "check_sdk_surface_compatibility",
    "get_sdk_surface_snapshot",
]
