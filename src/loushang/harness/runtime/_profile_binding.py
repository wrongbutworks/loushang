"""Live capability registry, binding, refresh, and disposal mechanics."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from loushang.foundation.json import dump_json_value
from loushang.harness.runtime._profile_types import (
    ResolvedRuntimeCapability,
    ResolvedRuntimeProfile,
    ResolvedRuntimeSelection,
    RuntimeCapabilitySelection,
    _require_integer,
    _require_nonempty_string,
)
from loushang.harness.runtime.bindings import RuntimeBindingLease, RuntimeBindingState

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
