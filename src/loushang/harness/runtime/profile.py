"""Deterministic Product runtime profile resolution and binding.

This module deliberately owns composition mechanics, not Product policy.  A
Product supplies a declared plan, and any OEM or extension layer has already
passed that Product's trust and permission checks before it reaches the
resolver.  The resulting profile is pure data and can therefore be retained
with a session without serializing factories, live objects, or credentials.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal

from loushang.harness.runtime.bindings import RuntimeBindingLease, RuntimeBindingState
from loushang.protocol import JSONValue, dump_json_value, require_json_mapping

RuntimeProfileSource = Literal["product", "oem", "extension", "session"]
RuntimeCapabilityShape = Literal["single", "ordered", "exclusive", "append_only"]
RuntimeCapabilityScope = Literal[
    "process", "tenant", "workspace", "session", "turn", "channel"
]
RuntimeRefreshBoundary = Literal["sealed", "turn"]

_SOURCES: frozenset[str] = frozenset({"product", "oem", "extension", "session"})
_SHAPES: frozenset[str] = frozenset({"single", "ordered", "exclusive", "append_only"})
_SCOPES: frozenset[str] = frozenset(
    {"process", "tenant", "workspace", "session", "turn", "channel"}
)
_REFRESH_BOUNDARIES: frozenset[str] = frozenset({"sealed", "turn"})
_SOURCE_RANK: dict[str, int] = {
    "product": 0,
    "oem": 1,
    "extension": 2,
    "session": 3,
}


def _require_nonempty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_integer(value: object, *, name: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _require_choice(value: object, *, name: str, choices: frozenset[str]) -> str:
    value = _require_nonempty_string(value, name=name)
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {options}")
    return value


@dataclass(frozen=True)
class RuntimeCapabilitySlot:
    """A Product-declared position at which runtime behavior may bind."""

    key: str
    shape: RuntimeCapabilityShape
    scope: RuntimeCapabilityScope
    refresh_boundary: RuntimeRefreshBoundary
    allowed_sources: frozenset[RuntimeProfileSource]
    required: bool = True

    def __post_init__(self) -> None:
        _require_nonempty_string(self.key, name="slot key")
        _require_choice(self.shape, name="slot shape", choices=_SHAPES)
        _require_choice(self.scope, name="slot scope", choices=_SCOPES)
        _require_choice(
            self.refresh_boundary,
            name="slot refresh boundary",
            choices=_REFRESH_BOUNDARIES,
        )
        if type(self.required) is not bool:
            raise TypeError("slot required must be a bool")
        sources = frozenset(self.allowed_sources)
        if not sources:
            raise ValueError("slot allowed_sources must not be empty")
        for source in sources:
            _require_choice(source, name="slot allowed source", choices=_SOURCES)
        if self.shape == "exclusive" and self.refresh_boundary != "sealed":
            raise ValueError("exclusive slots must use the sealed refresh boundary")
        object.__setattr__(self, "allowed_sources", sources)


@dataclass(frozen=True)
class RuntimeCapabilitySelection:
    """One implementation selection and its strictly JSON configuration."""

    slot: str
    implementation: str
    implementation_version: int
    config: Mapping[str, JSONValue] = field(default_factory=dict)
    priority: int = 0

    def __post_init__(self) -> None:
        _require_nonempty_string(self.slot, name="selection slot")
        _require_nonempty_string(self.implementation, name="selection implementation")
        _require_integer(
            self.implementation_version,
            name="selection implementation_version",
            minimum=1,
        )
        _require_integer(self.priority, name="selection priority")
        object.__setattr__(
            self,
            "config",
            require_json_mapping(dict(self.config), name="selection config"),
        )


@dataclass(frozen=True)
class RuntimeProfileLayer:
    """A source-owned group of selections applied after Product authorization."""

    source: RuntimeProfileSource
    layer_id: str
    selections: tuple[RuntimeCapabilitySelection, ...]
    priority: int = 0

    def __post_init__(self) -> None:
        _require_choice(self.source, name="layer source", choices=_SOURCES)
        _require_nonempty_string(self.layer_id, name="layer id")
        _require_integer(self.priority, name="layer priority")
        selections = tuple(self.selections)
        if any(not isinstance(item, RuntimeCapabilitySelection) for item in selections):
            raise TypeError(
                "layer selections must contain RuntimeCapabilitySelection values"
            )
        object.__setattr__(self, "selections", selections)


@dataclass(frozen=True)
class ProductRuntimePlan:
    """Product-owned declared slots and baseline selections.

    The plan is intentionally data-only.  It does not carry factories, plugin
    discovery, credentials, or configuration precedence code.
    """

    product_id: str
    slots: tuple[RuntimeCapabilitySlot, ...]
    defaults: tuple[RuntimeCapabilitySelection, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.product_id, name="product id")
        _require_integer(self.schema_version, name="plan schema_version", minimum=1)
        slots = tuple(self.slots)
        defaults = tuple(self.defaults)
        if any(not isinstance(slot, RuntimeCapabilitySlot) for slot in slots):
            raise TypeError("plan slots must contain RuntimeCapabilitySlot values")
        if any(
            not isinstance(selection, RuntimeCapabilitySelection)
            for selection in defaults
        ):
            raise TypeError(
                "plan defaults must contain RuntimeCapabilitySelection values"
            )
        slot_keys = [slot.key for slot in slots]
        duplicate_slots = sorted(
            key for key in set(slot_keys) if slot_keys.count(key) > 1
        )
        if duplicate_slots:
            raise ValueError(
                "plan slot keys must be unique: " + ", ".join(duplicate_slots)
            )
        unknown_defaults = sorted(
            {selection.slot for selection in defaults} - set(slot_keys)
        )
        if unknown_defaults:
            raise ValueError(
                "plan defaults select undeclared slots: " + ", ".join(unknown_defaults)
            )
        object.__setattr__(self, "slots", slots)
        object.__setattr__(self, "defaults", defaults)

    def slot(self, key: str) -> RuntimeCapabilitySlot:
        for slot in self.slots:
            if slot.key == key:
                return slot
        raise KeyError(f"unknown runtime capability slot: {key}")


@dataclass(frozen=True)
class RuntimeProfileDiagnostic:
    """Structured explanation for a rejected declaration or binding."""

    code: str
    message: str
    slot: str | None = None
    source: RuntimeProfileSource | None = None
    layer_id: str | None = None
    details: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_nonempty_string(self.code, name="diagnostic code")
        _require_nonempty_string(self.message, name="diagnostic message")
        if self.slot is not None:
            _require_nonempty_string(self.slot, name="diagnostic slot")
        if self.source is not None:
            _require_choice(self.source, name="diagnostic source", choices=_SOURCES)
        if self.layer_id is not None:
            _require_nonempty_string(self.layer_id, name="diagnostic layer id")
        object.__setattr__(
            self,
            "details",
            require_json_mapping(dict(self.details), name="diagnostic details"),
        )


class RuntimeProfileResolutionError(ValueError):
    """Raised when supplied profile layers cannot form one valid profile."""

    def __init__(self, diagnostics: Iterable[RuntimeProfileDiagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        if not self.diagnostics:
            raise ValueError("resolution errors must include at least one diagnostic")
        super().__init__(
            "runtime profile resolution failed: "
            + "; ".join(
                f"{diagnostic.code}: {diagnostic.message}"
                for diagnostic in self.diagnostics
            )
        )


@dataclass(frozen=True)
class RuntimeProfileLayerGrant:
    """Product authorization for one externally supplied runtime profile layer.

    The resolver deliberately has no knowledge of extension trust or Product
    permission policy.  A Product admits a layer with this value before asking
    the resolver to combine its selections with the Product baseline.
    """

    source: RuntimeProfileSource
    layer_id: str
    allowed_slots: frozenset[str] | None = None
    granted_permissions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_choice(self.source, name="layer grant source", choices=_SOURCES)
        if self.source == "product":
            raise ValueError("Product defaults must be declared on the Product plan")
        _require_nonempty_string(self.layer_id, name="layer grant id")
        if self.allowed_slots is not None:
            slots = frozenset(self.allowed_slots)
            if any(not isinstance(slot, str) or not slot for slot in slots):
                raise ValueError("layer grant allowed slots must be non-empty strings")
            object.__setattr__(self, "allowed_slots", slots)
        permissions = frozenset(self.granted_permissions)
        if any(
            not isinstance(permission, str) or not permission
            for permission in permissions
        ):
            raise ValueError("layer grant permissions must be non-empty strings")
        object.__setattr__(self, "granted_permissions", permissions)


@dataclass(frozen=True)
class RuntimeProfileAdmission:
    """Result of Product policy admitting external runtime profile layers."""

    layers: tuple[RuntimeProfileLayer, ...]
    diagnostics: tuple[RuntimeProfileDiagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def require_valid(self) -> tuple[RuntimeProfileLayer, ...]:
        if self.diagnostics:
            raise RuntimeProfileResolutionError(self.diagnostics)
        return self.layers


@dataclass(frozen=True)
class RuntimeProfileAdmissionPolicy:
    """Admit trusted OEM, extension, and session layers before resolution.

    This is intentionally an allow-list, not a plugin discovery mechanism.
    Product bootstrap is responsible for authenticating an OEM or extension
    and deriving the grants it supplies here.  The policy only verifies that a
    declared layer is entitled to select the requested runtime slots.
    """

    grants: tuple[RuntimeProfileLayerGrant, ...] = ()
    slot_permissions: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        grants = tuple(self.grants)
        if any(not isinstance(grant, RuntimeProfileLayerGrant) for grant in grants):
            raise TypeError(
                "admission grants must contain RuntimeProfileLayerGrant values"
            )
        identities = [(grant.source, grant.layer_id) for grant in grants]
        if len(identities) != len(set(identities)):
            raise ValueError("admission grants must have unique source and layer ids")
        object.__setattr__(self, "grants", grants)

        permissions: dict[str, frozenset[str]] = {}
        for slot, required in self.slot_permissions.items():
            _require_nonempty_string(slot, name="slot permission key")
            values = frozenset(required)
            if any(
                not isinstance(permission, str) or not permission
                for permission in values
            ):
                raise ValueError("slot permissions must be non-empty strings")
            permissions[slot] = values
        object.__setattr__(self, "slot_permissions", permissions)

    def admit(
        self,
        plan: ProductRuntimePlan,
        layers: Iterable[RuntimeProfileLayer],
    ) -> RuntimeProfileAdmission:
        """Return only authorized layers and diagnostics for rejected input."""

        supplied = tuple(layers)
        if any(not isinstance(layer, RuntimeProfileLayer) for layer in supplied):
            raise TypeError(
                "runtime profile layers must contain RuntimeProfileLayer values"
            )
        known_slots = {slot.key for slot in plan.slots}
        grants = {(grant.source, grant.layer_id): grant for grant in self.grants}
        admitted: list[RuntimeProfileLayer] = []
        diagnostics: list[RuntimeProfileDiagnostic] = []
        for layer in supplied:
            grant = grants.get((layer.source, layer.layer_id))
            if grant is None:
                diagnostics.append(
                    RuntimeProfileDiagnostic(
                        code="untrusted_runtime_layer",
                        message="no Product grant admits this runtime profile layer",
                        source=layer.source,
                        layer_id=layer.layer_id,
                    )
                )
                continue
            rejected = False
            for selection in layer.selections:
                if selection.slot not in known_slots:
                    # Preserve this diagnostic shape for the resolver, which
                    # remains the authority on Product plan validity.
                    continue
                if (
                    grant.allowed_slots is not None
                    and selection.slot not in grant.allowed_slots
                ):
                    diagnostics.append(
                        RuntimeProfileDiagnostic(
                            code="runtime_slot_not_granted",
                            message="runtime layer is not granted access to this slot",
                            slot=selection.slot,
                            source=layer.source,
                            layer_id=layer.layer_id,
                        )
                    )
                    rejected = True
                    continue
                required_permissions = self.slot_permissions.get(
                    selection.slot, frozenset()
                )
                missing_permissions = sorted(
                    required_permissions - grant.granted_permissions
                )
                if missing_permissions:
                    diagnostics.append(
                        RuntimeProfileDiagnostic(
                            code="runtime_slot_permission_denied",
                            message="runtime layer lacks a required slot permission",
                            slot=selection.slot,
                            source=layer.source,
                            layer_id=layer.layer_id,
                            details={"missingPermissions": missing_permissions},
                        )
                    )
                    rejected = True
            if not rejected:
                admitted.append(layer)
        return RuntimeProfileAdmission(
            layers=tuple(admitted), diagnostics=tuple(diagnostics)
        )


@dataclass(frozen=True)
class ResolvedRuntimeSelection:
    """A selection with source provenance retained for diagnostics and replay."""

    selection: RuntimeCapabilitySelection
    source: RuntimeProfileSource
    layer_id: str
    layer_priority: int


@dataclass(frozen=True)
class ResolvedRuntimeCapability:
    slot: RuntimeCapabilitySlot
    selections: tuple[ResolvedRuntimeSelection, ...]


@dataclass(frozen=True)
class RuntimeProfileSnapshotSelection:
    implementation: str
    implementation_version: int
    config: Mapping[str, JSONValue]
    source: RuntimeProfileSource
    layer_id: str
    layer_priority: int
    selection_priority: int

    def __post_init__(self) -> None:
        _require_nonempty_string(self.implementation, name="snapshot implementation")
        _require_integer(
            self.implementation_version,
            name="snapshot implementation_version",
            minimum=1,
        )
        _require_choice(self.source, name="snapshot source", choices=_SOURCES)
        _require_nonempty_string(self.layer_id, name="snapshot layer id")
        _require_integer(self.layer_priority, name="snapshot layer priority")
        _require_integer(self.selection_priority, name="snapshot selection priority")
        object.__setattr__(
            self,
            "config",
            require_json_mapping(dict(self.config), name="snapshot config"),
        )

    @classmethod
    def from_json(cls, value: object, *, name: str) -> RuntimeProfileSnapshotSelection:
        mapping = require_json_mapping(value, name=name)
        return cls(
            implementation=_require_nonempty_string(
                mapping.get("implementation"), name=f"{name}.implementation"
            ),
            implementation_version=_require_integer(
                mapping.get("implementationVersion"),
                name=f"{name}.implementationVersion",
                minimum=1,
            ),
            config=require_json_mapping(mapping.get("config"), name=f"{name}.config"),
            source=_require_choice(
                mapping.get("source"), name=f"{name}.source", choices=_SOURCES
            ),
            layer_id=_require_nonempty_string(
                mapping.get("layerId"), name=f"{name}.layerId"
            ),
            layer_priority=_require_integer(
                mapping.get("layerPriority"), name=f"{name}.layerPriority"
            ),
            selection_priority=_require_integer(
                mapping.get("selectionPriority"),
                name=f"{name}.selectionPriority",
            ),
        )

    def to_json(self) -> dict[str, JSONValue]:
        return {
            "implementation": self.implementation,
            "implementationVersion": self.implementation_version,
            "config": dict(self.config),
            "source": self.source,
            "layerId": self.layer_id,
            "layerPriority": self.layer_priority,
            "selectionPriority": self.selection_priority,
        }


@dataclass(frozen=True)
class RuntimeProfileSnapshotCapability:
    slot: str
    shape: RuntimeCapabilityShape
    scope: RuntimeCapabilityScope
    refresh_boundary: RuntimeRefreshBoundary
    selections: tuple[RuntimeProfileSnapshotSelection, ...]

    def __post_init__(self) -> None:
        _require_nonempty_string(self.slot, name="snapshot slot")
        _require_choice(self.shape, name="snapshot shape", choices=_SHAPES)
        _require_choice(self.scope, name="snapshot scope", choices=_SCOPES)
        _require_choice(
            self.refresh_boundary,
            name="snapshot refresh boundary",
            choices=_REFRESH_BOUNDARIES,
        )
        selections = tuple(self.selections)
        if any(
            not isinstance(selection, RuntimeProfileSnapshotSelection)
            for selection in selections
        ):
            raise TypeError(
                "snapshot selections must contain RuntimeProfileSnapshotSelection values"
            )
        object.__setattr__(self, "selections", selections)

    @classmethod
    def from_json(cls, value: object, *, name: str) -> RuntimeProfileSnapshotCapability:
        mapping = require_json_mapping(value, name=name)
        raw_selections = mapping.get("selections")
        if not isinstance(raw_selections, list):
            raise TypeError(f"{name}.selections must be a JSON array")
        return cls(
            slot=_require_nonempty_string(mapping.get("slot"), name=f"{name}.slot"),
            shape=_require_choice(
                mapping.get("shape"), name=f"{name}.shape", choices=_SHAPES
            ),
            scope=_require_choice(
                mapping.get("scope"), name=f"{name}.scope", choices=_SCOPES
            ),
            refresh_boundary=_require_choice(
                mapping.get("refreshBoundary"),
                name=f"{name}.refreshBoundary",
                choices=_REFRESH_BOUNDARIES,
            ),
            selections=tuple(
                RuntimeProfileSnapshotSelection.from_json(
                    selection, name=f"{name}.selections[{index}]"
                )
                for index, selection in enumerate(raw_selections)
            ),
        )

    def to_json(self) -> dict[str, JSONValue]:
        return {
            "slot": self.slot,
            "shape": self.shape,
            "scope": self.scope,
            "refreshBoundary": self.refresh_boundary,
            "selections": [selection.to_json() for selection in self.selections],
        }


@dataclass(frozen=True)
class RuntimeProfileSnapshot:
    """Durable, JSON-only description of a resolved runtime profile."""

    product_id: str
    capabilities: tuple[RuntimeProfileSnapshotCapability, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.product_id, name="snapshot product id")
        _require_integer(self.schema_version, name="snapshot schema_version", minimum=1)
        capabilities = tuple(self.capabilities)
        if any(
            not isinstance(capability, RuntimeProfileSnapshotCapability)
            for capability in capabilities
        ):
            raise TypeError(
                "snapshot capabilities must contain RuntimeProfileSnapshotCapability values"
            )
        keys = [capability.slot for capability in capabilities]
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        if duplicates:
            raise ValueError(
                "snapshot capability slots must be unique: " + ", ".join(duplicates)
            )
        object.__setattr__(self, "capabilities", capabilities)

    def to_json(self) -> dict[str, JSONValue]:
        return {
            "schemaVersion": self.schema_version,
            "productId": self.product_id,
            "capabilities": [capability.to_json() for capability in self.capabilities],
        }

    @classmethod
    def from_json(cls, value: object) -> RuntimeProfileSnapshot:
        mapping = require_json_mapping(value, name="runtime profile snapshot")
        schema_version = _require_integer(
            mapping.get("schemaVersion"),
            name="runtime profile snapshot.schemaVersion",
            minimum=1,
        )
        if schema_version != 1:
            raise ValueError(
                f"unsupported runtime profile snapshot schema version: {schema_version}"
            )
        raw_capabilities = mapping.get("capabilities")
        if not isinstance(raw_capabilities, list):
            raise TypeError(
                "runtime profile snapshot.capabilities must be a JSON array"
            )
        return cls(
            product_id=_require_nonempty_string(
                mapping.get("productId"), name="runtime profile snapshot.productId"
            ),
            capabilities=tuple(
                RuntimeProfileSnapshotCapability.from_json(
                    capability,
                    name=f"runtime profile snapshot.capabilities[{index}]",
                )
                for index, capability in enumerate(raw_capabilities)
            ),
            schema_version=schema_version,
        )


@dataclass(frozen=True)
class ResolvedRuntimeProfile:
    product_id: str
    capabilities: tuple[ResolvedRuntimeCapability, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_nonempty_string(self.product_id, name="resolved product id")
        _require_integer(self.schema_version, name="resolved schema_version", minimum=1)
        capabilities = tuple(self.capabilities)
        if any(
            not isinstance(capability, ResolvedRuntimeCapability)
            for capability in capabilities
        ):
            raise TypeError(
                "resolved capabilities must contain ResolvedRuntimeCapability values"
            )
        keys = [capability.slot.key for capability in capabilities]
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        if duplicates:
            raise ValueError(
                "resolved capability slots must be unique: " + ", ".join(duplicates)
            )
        object.__setattr__(self, "capabilities", capabilities)

    def capability(self, key: str) -> ResolvedRuntimeCapability:
        for capability in self.capabilities:
            if capability.slot.key == key:
                return capability
        raise KeyError(f"unknown resolved runtime capability slot: {key}")

    def snapshot(self) -> RuntimeProfileSnapshot:
        return RuntimeProfileSnapshot(
            product_id=self.product_id,
            schema_version=self.schema_version,
            capabilities=tuple(
                RuntimeProfileSnapshotCapability(
                    slot=capability.slot.key,
                    shape=capability.slot.shape,
                    scope=capability.slot.scope,
                    refresh_boundary=capability.slot.refresh_boundary,
                    selections=tuple(
                        RuntimeProfileSnapshotSelection(
                            implementation=resolved.selection.implementation,
                            implementation_version=resolved.selection.implementation_version,
                            config=resolved.selection.config,
                            source=resolved.source,
                            layer_id=resolved.layer_id,
                            layer_priority=resolved.layer_priority,
                            selection_priority=resolved.selection.priority,
                        )
                        for resolved in capability.selections
                    ),
                )
                for capability in self.capabilities
            ),
        )


class RuntimeProfileResolver:
    """Resolve Product, OEM, extension, and session layers deterministically."""

    def resolve(
        self,
        plan: ProductRuntimePlan,
        *,
        layers: Iterable[RuntimeProfileLayer] = (),
    ) -> ResolvedRuntimeProfile:
        supplied_layers = tuple(layers)
        if any(not isinstance(layer, RuntimeProfileLayer) for layer in supplied_layers):
            raise TypeError(
                "runtime profile layers must contain RuntimeProfileLayer values"
            )

        diagnostics: list[RuntimeProfileDiagnostic] = []
        known_slots = {slot.key: slot for slot in plan.slots}
        candidates: dict[str, list[ResolvedRuntimeSelection]] = {
            slot.key: [] for slot in plan.slots
        }
        product_layer = RuntimeProfileLayer(
            source="product",
            layer_id=f"product:{plan.product_id}",
            selections=plan.defaults,
        )
        ordered_layers = (product_layer,) + self._ordered_external_layers(
            supplied_layers, diagnostics
        )

        for layer in ordered_layers:
            grouped: dict[str, list[RuntimeCapabilitySelection]] = {}
            for selection in layer.selections:
                grouped.setdefault(selection.slot, []).append(selection)
            for slot_key, selections in grouped.items():
                slot = known_slots.get(slot_key)
                if slot is None:
                    diagnostics.append(
                        RuntimeProfileDiagnostic(
                            code="unknown_slot",
                            message="selection targets a slot absent from the Product plan",
                            slot=slot_key,
                            source=layer.source,
                            layer_id=layer.layer_id,
                        )
                    )
                    continue
                if layer.source not in slot.allowed_sources:
                    diagnostics.append(
                        RuntimeProfileDiagnostic(
                            code="source_not_allowed",
                            message="source is not authorized to select this slot",
                            slot=slot_key,
                            source=layer.source,
                            layer_id=layer.layer_id,
                            details={"allowedSources": sorted(slot.allowed_sources)},
                        )
                    )
                    continue
                if slot.shape in {"single", "exclusive"} and len(selections) > 1:
                    diagnostics.append(
                        RuntimeProfileDiagnostic(
                            code="ambiguous_single_selection",
                            message="a single or exclusive slot has multiple selections in one layer",
                            slot=slot_key,
                            source=layer.source,
                            layer_id=layer.layer_id,
                        )
                    )
                    continue
                for selection in sorted(selections, key=_selection_order_key):
                    candidates[slot_key].append(
                        ResolvedRuntimeSelection(
                            selection=selection,
                            source=layer.source,
                            layer_id=layer.layer_id,
                            layer_priority=layer.priority,
                        )
                    )

        if diagnostics:
            raise RuntimeProfileResolutionError(diagnostics)

        capabilities: list[ResolvedRuntimeCapability] = []
        for slot in plan.slots:
            resolved = self._resolve_slot(slot, candidates[slot.key], diagnostics)
            capabilities.append(
                ResolvedRuntimeCapability(slot=slot, selections=resolved)
            )
        if diagnostics:
            raise RuntimeProfileResolutionError(diagnostics)
        return ResolvedRuntimeProfile(
            product_id=plan.product_id,
            capabilities=tuple(capabilities),
            schema_version=plan.schema_version,
        )

    @staticmethod
    def _ordered_external_layers(
        layers: tuple[RuntimeProfileLayer, ...],
        diagnostics: list[RuntimeProfileDiagnostic],
    ) -> tuple[RuntimeProfileLayer, ...]:
        seen: set[tuple[str, str]] = set()
        valid: list[RuntimeProfileLayer] = []
        for layer in layers:
            identity = (layer.source, layer.layer_id)
            if layer.source == "product":
                diagnostics.append(
                    RuntimeProfileDiagnostic(
                        code="product_layer_not_allowed",
                        message="Product defaults must be declared on ProductRuntimePlan",
                        source=layer.source,
                        layer_id=layer.layer_id,
                    )
                )
                continue
            if identity in seen:
                diagnostics.append(
                    RuntimeProfileDiagnostic(
                        code="duplicate_layer",
                        message="a source may contribute one layer with a given layer id",
                        source=layer.source,
                        layer_id=layer.layer_id,
                    )
                )
                continue
            seen.add(identity)
            valid.append(layer)
        return tuple(
            sorted(
                valid,
                key=lambda layer: (
                    _SOURCE_RANK[layer.source],
                    layer.priority,
                    layer.layer_id,
                ),
            )
        )

    @staticmethod
    def _resolve_slot(
        slot: RuntimeCapabilitySlot,
        candidates: list[ResolvedRuntimeSelection],
        diagnostics: list[RuntimeProfileDiagnostic],
    ) -> tuple[ResolvedRuntimeSelection, ...]:
        ordered = tuple(sorted(candidates, key=_resolved_selection_order_key))
        if slot.shape in {"single", "exclusive"}:
            result = ordered[-1:] if ordered else ()
        elif slot.shape == "ordered":
            latest: dict[tuple[str, int], ResolvedRuntimeSelection] = {}
            for candidate in ordered:
                identity = (
                    candidate.selection.implementation,
                    candidate.selection.implementation_version,
                )
                latest[identity] = candidate
            result = tuple(sorted(latest.values(), key=_resolved_selection_order_key))
        else:
            result = ordered
        if slot.required and not result:
            diagnostics.append(
                RuntimeProfileDiagnostic(
                    code="missing_required_selection",
                    message="required slot has no active selection",
                    slot=slot.key,
                )
            )
        return result


def _selection_order_key(selection: RuntimeCapabilitySelection) -> tuple[object, ...]:
    return (
        selection.priority,
        selection.implementation,
        selection.implementation_version,
        dump_json_value(selection.config, name="selection config", sort_keys=True),
    )


def _resolved_selection_order_key(
    resolved: ResolvedRuntimeSelection,
) -> tuple[object, ...]:
    return (
        _SOURCE_RANK[resolved.source],
        resolved.layer_priority,
        resolved.layer_id,
        *_selection_order_key(resolved.selection),
    )


RuntimeCapabilityFactory = Callable[
    [RuntimeCapabilitySelection, object | None], object | Awaitable[object]
]
RuntimeCapabilityDisposer = Callable[[object, object | None], None | Awaitable[None]]


@dataclass(frozen=True)
class RuntimeCapabilityImplementation:
    """One registered factory for an exact slot, key, and wire version."""

    slot: str
    implementation: str
    implementation_version: int
    create: RuntimeCapabilityFactory
    dispose: RuntimeCapabilityDisposer | None = None

    def __post_init__(self) -> None:
        _require_nonempty_string(self.slot, name="implementation slot")
        _require_nonempty_string(self.implementation, name="implementation key")
        _require_integer(
            self.implementation_version,
            name="implementation version",
            minimum=1,
        )
        if not callable(self.create):
            raise TypeError("implementation create must be callable")
        if self.dispose is not None and not callable(self.dispose):
            raise TypeError("implementation dispose must be callable when supplied")


class RuntimeCapabilityRegistry:
    """Exact implementation registry used only by an explicit binder."""

    def __init__(
        self,
        implementations: Iterable[RuntimeCapabilityImplementation] = (),
    ) -> None:
        self._implementations: dict[
            tuple[str, str, int], RuntimeCapabilityImplementation
        ] = {}
        for implementation in implementations:
            self.register(implementation)

    def register(self, implementation: RuntimeCapabilityImplementation) -> None:
        if not isinstance(implementation, RuntimeCapabilityImplementation):
            raise TypeError(
                "implementation must be a RuntimeCapabilityImplementation value"
            )
        key = (
            implementation.slot,
            implementation.implementation,
            implementation.implementation_version,
        )
        if key in self._implementations:
            raise ValueError(
                "runtime capability implementation already registered: "
                + "/".join((key[0], key[1], str(key[2])))
            )
        self._implementations[key] = implementation

    def resolve(
        self,
        selection: RuntimeCapabilitySelection,
    ) -> RuntimeCapabilityImplementation:
        key = (
            selection.slot,
            selection.implementation,
            selection.implementation_version,
        )
        try:
            return self._implementations[key]
        except KeyError as exc:
            raise RuntimeCapabilityBindingError(
                "no registered factory matches the resolved selection",
                slot=selection.slot,
                implementation=selection.implementation,
                implementation_version=selection.implementation_version,
            ) from exc


class RuntimeCapabilityBindingError(RuntimeError):
    """Raised when a capability factory or disposer cannot complete safely."""

    def __init__(
        self,
        message: str,
        *,
        slot: str,
        implementation: str | None = None,
        implementation_version: int | None = None,
    ) -> None:
        self.slot = slot
        self.implementation = implementation
        self.implementation_version = implementation_version
        detail = f"{message} [slot={slot}"
        if implementation is not None:
            detail += f", implementation={implementation}"
        if implementation_version is not None:
            detail += f", version={implementation_version}"
        super().__init__(detail + "]")


class SealedRuntimeCapabilityError(RuntimeError):
    """Raised when a session-sealed selection is changed after binding."""

    def __init__(self, slot: str) -> None:
        self.slot = slot
        super().__init__(f"runtime capability is sealed for this session: {slot}")


@dataclass(frozen=True)
class RuntimeProfileBindings:
    """Live values created from one profile, exposed through a generation lease."""

    profile: ResolvedRuntimeProfile
    values: Mapping[str, object | tuple[object, ...]]


@dataclass(frozen=True)
class _BoundRuntimeCapability:
    resolved: ResolvedRuntimeSelection
    implementation: RuntimeCapabilityImplementation
    value: object


class RuntimeProfileBinding:
    """Own one live profile and its generation-scoped read leases."""

    def __init__(
        self,
        *,
        profile: ResolvedRuntimeProfile,
        context: object | None,
        state: RuntimeBindingState[RuntimeProfileBindings],
        bound: Mapping[str, tuple[_BoundRuntimeCapability, ...]],
    ) -> None:
        self._profile = profile
        self._context = context
        self._state = state
        self._bound = dict(bound)
        self._closed = False

    @property
    def profile(self) -> ResolvedRuntimeProfile:
        return self._profile

    @property
    def is_closed(self) -> bool:
        return self._closed

    def capture(self) -> RuntimeBindingLease[RuntimeProfileBindings]:
        self._require_open()
        return self._state.capture()

    def value(self, slot: str) -> object | tuple[object, ...]:
        self._require_open()
        values = self._state.require().values
        try:
            return values[slot]
        except KeyError as exc:
            raise KeyError(f"runtime capability is not bound: {slot}") from exc

    def values(self) -> Mapping[str, object | tuple[object, ...]]:
        self._require_open()
        return self._state.require().values

    def _replace(
        self,
        *,
        profile: ResolvedRuntimeProfile,
        bound: Mapping[str, tuple[_BoundRuntimeCapability, ...]],
    ) -> None:
        self._profile = profile
        self._bound = dict(bound)
        self._state.refresh(_live_bindings(profile, self._bound))
        self._state.invalidate("runtime profile binding was refreshed")

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("runtime profile binding is closed")


class RuntimeProfileBinder:
    """Create, refresh, and dispose instances from an already-resolved profile."""

    def __init__(self, registry: RuntimeCapabilityRegistry) -> None:
        self._registry = registry

    async def bind(
        self,
        profile: ResolvedRuntimeProfile,
        *,
        context: object | None = None,
    ) -> RuntimeProfileBinding:
        bound = await self._create_profile(profile, context=context)
        state = RuntimeBindingState[RuntimeProfileBindings](
            unbound_message="runtime profile binding has not been initialized",
            stale_message="runtime profile binding was refreshed",
        )
        state.bind(_live_bindings(profile, bound))
        return RuntimeProfileBinding(
            profile=profile,
            context=context,
            state=state,
            bound=bound,
        )

    def bind_sync(
        self,
        profile: ResolvedRuntimeProfile,
        *,
        context: object | None = None,
    ) -> RuntimeProfileBinding:
        """Bind only synchronous factories without creating an event loop.

        Product bootstrap is often synchronous.  It may use this narrow path
        for pure factories, while factories that perform I/O or other async
        work must continue through :meth:`bind`.
        """

        bound = self._create_profile_sync(profile, context=context)
        state = RuntimeBindingState[RuntimeProfileBindings](
            unbound_message="runtime profile binding has not been initialized",
            stale_message="runtime profile binding was refreshed",
        )
        state.bind(_live_bindings(profile, bound))
        return RuntimeProfileBinding(
            profile=profile,
            context=context,
            state=state,
            bound=bound,
        )

    async def rebind(
        self,
        binding: RuntimeProfileBinding,
        profile: ResolvedRuntimeProfile,
        *,
        boundary: Literal["turn"] = "turn",
    ) -> None:
        if boundary != "turn":
            raise ValueError(
                "runtime profile rebind is only supported at a turn boundary"
            )
        binding._require_open()
        if binding.profile.product_id != profile.product_id:
            raise ValueError("a binding cannot change Product runtime plans")

        previous = {
            capability.slot.key: capability
            for capability in binding.profile.capabilities
        }
        target = {
            capability.slot.key: capability for capability in profile.capabilities
        }
        changed_keys = tuple(
            key
            for key in sorted(set(previous) | set(target))
            if _capability_signature(previous.get(key))
            != _capability_signature(target.get(key))
        )
        if not changed_keys:
            return
        for key in changed_keys:
            capability = target.get(key) or previous[key]
            if capability.slot.refresh_boundary == "sealed":
                raise SealedRuntimeCapabilityError(key)

        replacements: dict[str, tuple[_BoundRuntimeCapability, ...]] = {}
        created: list[_BoundRuntimeCapability] = []
        try:
            for capability in profile.capabilities:
                if capability.slot.key not in changed_keys:
                    continue
                entries = await self._create_capability(
                    capability, context=binding._context
                )
                replacements[capability.slot.key] = entries
                created.extend(entries)
        except Exception:
            await self._dispose_entries_reversing(created, context=binding._context)
            raise

        try:
            for key in reversed(changed_keys):
                await self._dispose_entries(
                    binding._bound.get(key, ()), context=binding._context
                )
        except Exception:
            await self._dispose_entries_reversing(created, context=binding._context)
            raise

        updated = dict(binding._bound)
        for key in changed_keys:
            updated.pop(key, None)
        updated.update(replacements)
        binding._replace(profile=profile, bound=updated)

    async def dispose(self, binding: RuntimeProfileBinding) -> None:
        if binding._closed:
            return
        errors: list[Exception] = []
        for capability in reversed(binding.profile.capabilities):
            try:
                await self._dispose_entries(
                    binding._bound.get(capability.slot.key, ()),
                    context=binding._context,
                )
            except Exception as exc:
                errors.append(exc)
        binding._closed = True
        binding._state.invalidate("runtime profile binding was disposed")
        if errors:
            raise errors[0]

    def dispose_sync(self, binding: RuntimeProfileBinding) -> None:
        """Dispose a binding created from synchronous factories."""

        if binding._closed:
            return
        errors: list[Exception] = []
        for capability in reversed(binding.profile.capabilities):
            try:
                self._dispose_entries_sync(
                    binding._bound.get(capability.slot.key, ()),
                    context=binding._context,
                )
            except Exception as exc:
                errors.append(exc)
        binding._closed = True
        binding._state.invalidate("runtime profile binding was disposed")
        if errors:
            raise errors[0]

    def _create_profile_sync(
        self,
        profile: ResolvedRuntimeProfile,
        *,
        context: object | None,
    ) -> dict[str, tuple[_BoundRuntimeCapability, ...]]:
        bound: dict[str, tuple[_BoundRuntimeCapability, ...]] = {}
        created: list[_BoundRuntimeCapability] = []
        try:
            for capability in profile.capabilities:
                entries = self._create_capability_sync(capability, context=context)
                if entries:
                    bound[capability.slot.key] = entries
                    created.extend(entries)
        except Exception:
            self._dispose_entries_reversing_sync(created, context=context)
            raise
        return bound

    def _create_capability_sync(
        self,
        capability: ResolvedRuntimeCapability,
        *,
        context: object | None,
    ) -> tuple[_BoundRuntimeCapability, ...]:
        created: list[_BoundRuntimeCapability] = []
        try:
            for resolved in capability.selections:
                implementation = self._registry.resolve(resolved.selection)
                value = _require_sync_result(
                    implementation.create(resolved.selection, context),
                    slot=resolved.selection.slot,
                    implementation=resolved.selection.implementation,
                    implementation_version=resolved.selection.implementation_version,
                    action="factory",
                )
                created.append(
                    _BoundRuntimeCapability(
                        resolved=resolved,
                        implementation=implementation,
                        value=value,
                    )
                )
        except RuntimeCapabilityBindingError:
            self._dispose_entries_reversing_sync(created, context=context)
            raise
        except Exception as exc:
            self._dispose_entries_reversing_sync(created, context=context)
            selection = capability.selections[len(created)].selection
            raise RuntimeCapabilityBindingError(
                "capability factory failed",
                slot=selection.slot,
                implementation=selection.implementation,
                implementation_version=selection.implementation_version,
            ) from exc
        return tuple(created)

    async def _create_profile(
        self,
        profile: ResolvedRuntimeProfile,
        *,
        context: object | None,
    ) -> dict[str, tuple[_BoundRuntimeCapability, ...]]:
        bound: dict[str, tuple[_BoundRuntimeCapability, ...]] = {}
        created: list[_BoundRuntimeCapability] = []
        try:
            for capability in profile.capabilities:
                entries = await self._create_capability(capability, context=context)
                if entries:
                    bound[capability.slot.key] = entries
                    created.extend(entries)
        except Exception:
            await self._dispose_entries_reversing(created, context=context)
            raise
        return bound

    async def _create_capability(
        self,
        capability: ResolvedRuntimeCapability,
        *,
        context: object | None,
    ) -> tuple[_BoundRuntimeCapability, ...]:
        created: list[_BoundRuntimeCapability] = []
        try:
            for resolved in capability.selections:
                implementation = self._registry.resolve(resolved.selection)
                value = await _await_result(
                    implementation.create(resolved.selection, context)
                )
                created.append(
                    _BoundRuntimeCapability(
                        resolved=resolved,
                        implementation=implementation,
                        value=value,
                    )
                )
        except RuntimeCapabilityBindingError:
            await self._dispose_entries_reversing(created, context=context)
            raise
        except Exception as exc:
            await self._dispose_entries_reversing(created, context=context)
            selection = capability.selections[len(created)].selection
            raise RuntimeCapabilityBindingError(
                "capability factory failed",
                slot=selection.slot,
                implementation=selection.implementation,
                implementation_version=selection.implementation_version,
            ) from exc
        return tuple(created)

    async def _dispose_entries(
        self,
        entries: Iterable[_BoundRuntimeCapability],
        *,
        context: object | None,
    ) -> None:
        for entry in reversed(tuple(entries)):
            if entry.implementation.dispose is None:
                continue
            try:
                await _await_result(entry.implementation.dispose(entry.value, context))
            except Exception as exc:
                raise RuntimeCapabilityBindingError(
                    "capability disposer failed",
                    slot=entry.resolved.selection.slot,
                    implementation=entry.resolved.selection.implementation,
                    implementation_version=entry.resolved.selection.implementation_version,
                ) from exc

    async def _dispose_entries_reversing(
        self,
        entries: Iterable[_BoundRuntimeCapability],
        *,
        context: object | None,
    ) -> None:
        with suppress(Exception):
            await self._dispose_entries(entries, context=context)

    def _dispose_entries_sync(
        self,
        entries: Iterable[_BoundRuntimeCapability],
        *,
        context: object | None,
    ) -> None:
        for entry in reversed(tuple(entries)):
            if entry.implementation.dispose is None:
                continue
            try:
                _require_sync_result(
                    entry.implementation.dispose(entry.value, context),
                    slot=entry.resolved.selection.slot,
                    implementation=entry.resolved.selection.implementation,
                    implementation_version=entry.resolved.selection.implementation_version,
                    action="disposer",
                )
            except RuntimeCapabilityBindingError:
                raise
            except Exception as exc:
                raise RuntimeCapabilityBindingError(
                    "capability disposer failed",
                    slot=entry.resolved.selection.slot,
                    implementation=entry.resolved.selection.implementation,
                    implementation_version=entry.resolved.selection.implementation_version,
                ) from exc

    def _dispose_entries_reversing_sync(
        self,
        entries: Iterable[_BoundRuntimeCapability],
        *,
        context: object | None,
    ) -> None:
        with suppress(Exception):
            self._dispose_entries_sync(entries, context=context)


async def _await_result(value: object | Awaitable[object]) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _require_sync_result(
    value: object | Awaitable[object],
    *,
    slot: str,
    implementation: str,
    implementation_version: int,
    action: str,
) -> object:
    if not inspect.isawaitable(value):
        return value
    if inspect.iscoroutine(value):
        value.close()
    raise RuntimeCapabilityBindingError(
        f"synchronous binding cannot await a capability {action}",
        slot=slot,
        implementation=implementation,
        implementation_version=implementation_version,
    )


def _capability_signature(
    capability: ResolvedRuntimeCapability | None,
) -> tuple[object, ...] | None:
    if capability is None:
        return None
    return (
        capability.slot,
        tuple(
            (
                resolved.selection.implementation,
                resolved.selection.implementation_version,
                dump_json_value(
                    resolved.selection.config,
                    name="resolved selection config",
                    sort_keys=True,
                ),
                resolved.source,
                resolved.layer_id,
                resolved.layer_priority,
                resolved.selection.priority,
            )
            for resolved in capability.selections
        ),
    )


def _live_bindings(
    profile: ResolvedRuntimeProfile,
    bound: Mapping[str, tuple[_BoundRuntimeCapability, ...]],
) -> RuntimeProfileBindings:
    values: dict[str, object | tuple[object, ...]] = {}
    for capability in profile.capabilities:
        entries = bound.get(capability.slot.key, ())
        if not entries:
            continue
        if capability.slot.shape in {"single", "exclusive"}:
            values[capability.slot.key] = entries[0].value
        else:
            values[capability.slot.key] = tuple(entry.value for entry in entries)
    return RuntimeProfileBindings(profile=profile, values=values)


# Initial shared vocabulary.  These identifiers are neutral contracts, not
# imports of a particular store, transcript, or compaction implementation.
CONVERSATION_STORE_SLOT = RuntimeCapabilitySlot(
    key="conversation.store",
    shape="single",
    scope="session",
    refresh_boundary="sealed",
    allowed_sources=frozenset({"product", "oem"}),
)
AGENT_TRANSCRIPT_PROFILE_SLOT = RuntimeCapabilitySlot(
    key="agent.transcript_profile",
    shape="single",
    scope="session",
    refresh_boundary="sealed",
    allowed_sources=frozenset({"product", "oem"}),
)
CONTEXT_COMPACTION_SLOT = RuntimeCapabilitySlot(
    key="context.compaction",
    shape="single",
    scope="session",
    refresh_boundary="turn",
    allowed_sources=frozenset({"product", "oem", "extension", "session"}),
)
RESOURCE_RUNTIME_SLOT = RuntimeCapabilitySlot(
    key="resource.runtime",
    shape="single",
    scope="workspace",
    refresh_boundary="sealed",
    allowed_sources=frozenset({"product", "oem"}),
)
PROMPT_SECTIONS_SLOT = RuntimeCapabilitySlot(
    key="prompt.sections",
    shape="ordered",
    scope="session",
    refresh_boundary="turn",
    allowed_sources=frozenset({"product", "oem", "extension", "session"}),
)
SKILL_ACTIVATION_SLOT = RuntimeCapabilitySlot(
    key="skill.activation",
    shape="single",
    scope="session",
    refresh_boundary="turn",
    allowed_sources=frozenset({"product", "oem", "extension", "session"}),
)
TOOL_PACKS_SLOT = RuntimeCapabilitySlot(
    key="tool.packs",
    shape="ordered",
    scope="session",
    refresh_boundary="turn",
    allowed_sources=frozenset({"product", "oem", "extension"}),
)
COMMAND_PACKS_SLOT = RuntimeCapabilitySlot(
    key="command.packs",
    shape="ordered",
    scope="session",
    refresh_boundary="turn",
    allowed_sources=frozenset({"product", "oem", "extension"}),
)
SIDE_QUESTION_PROVIDER_SLOT = RuntimeCapabilitySlot(
    key="interaction.side_question",
    shape="single",
    scope="session",
    refresh_boundary="sealed",
    allowed_sources=frozenset({"product", "oem", "extension"}),
    required=False,
)
CONTINUITY_PROVIDER_PACKS_SLOT = RuntimeCapabilitySlot(
    key="continuity.provider_packs",
    shape="ordered",
    scope="process",
    refresh_boundary="sealed",
    allowed_sources=frozenset({"product", "oem"}),
    required=False,
)


def standard_agent_session_slots() -> tuple[RuntimeCapabilitySlot, ...]:
    """Return fresh declarations for the first three shared session slots."""

    return (
        CONVERSATION_STORE_SLOT,
        AGENT_TRANSCRIPT_PROFILE_SLOT,
        CONTEXT_COMPACTION_SLOT,
    )


def standard_capability_composition_slots() -> tuple[RuntimeCapabilitySlot, ...]:
    """Return fresh declarations for shared Product capability composition."""

    return (
        RESOURCE_RUNTIME_SLOT,
        PROMPT_SECTIONS_SLOT,
        SKILL_ACTIVATION_SLOT,
        TOOL_PACKS_SLOT,
        COMMAND_PACKS_SLOT,
        SIDE_QUESTION_PROVIDER_SLOT,
        CONTINUITY_PROVIDER_PACKS_SLOT,
    )


__all__ = [
    "AGENT_TRANSCRIPT_PROFILE_SLOT",
    "COMMAND_PACKS_SLOT",
    "CONTEXT_COMPACTION_SLOT",
    "CONVERSATION_STORE_SLOT",
    "CONTINUITY_PROVIDER_PACKS_SLOT",
    "PROMPT_SECTIONS_SLOT",
    "ProductRuntimePlan",
    "ResolvedRuntimeCapability",
    "ResolvedRuntimeProfile",
    "ResolvedRuntimeSelection",
    "RuntimeCapabilityBindingError",
    "RuntimeCapabilityImplementation",
    "RuntimeCapabilityRegistry",
    "RuntimeCapabilityScope",
    "RuntimeCapabilitySelection",
    "RuntimeCapabilityShape",
    "RuntimeCapabilitySlot",
    "RuntimeProfileBinder",
    "RuntimeProfileBinding",
    "RuntimeProfileBindings",
    "RuntimeProfileDiagnostic",
    "RuntimeProfileAdmission",
    "RuntimeProfileAdmissionPolicy",
    "RuntimeProfileLayerGrant",
    "RuntimeProfileLayer",
    "RuntimeProfileResolutionError",
    "RuntimeProfileResolver",
    "RuntimeProfileSnapshot",
    "RuntimeProfileSnapshotCapability",
    "RuntimeProfileSnapshotSelection",
    "RuntimeProfileSource",
    "RuntimeRefreshBoundary",
    "SIDE_QUESTION_PROVIDER_SLOT",
    "SealedRuntimeCapabilityError",
    "RESOURCE_RUNTIME_SLOT",
    "SKILL_ACTIVATION_SLOT",
    "TOOL_PACKS_SLOT",
    "standard_agent_session_slots",
    "standard_capability_composition_slots",
]
