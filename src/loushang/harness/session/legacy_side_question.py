"""Focused legacy binding for the Session-owned side-question Provider factory.

The binding intentionally remains Profile-backed until ``harness.session`` is
migrated.  It is separate from ``harness.resources`` and has one owner: the
live Product Session that binds the selected factory to its context.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from loushang.harness.capabilities.composition_runtime import (
    standard_capability_composition_implementations,
)
from loushang.harness.runtime import (
    SIDE_QUESTION_PROVIDER_SLOT,
    ResolvedRuntimeProfile,
    RuntimeCapabilityImplementation,
    RuntimeCapabilityRegistry,
    RuntimeProfileBinder,
    RuntimeProfileBinding,
    SideQuestionProviderFactory,
)


@dataclass
class LegacySideQuestionBinding:
    """Own exactly one selected side-question factory for one Session."""

    _binding: RuntimeProfileBinding
    _binder: RuntimeProfileBinder
    _ownership_state: str = field(default="root_owned", init=False)

    @property
    def provider_factory(self) -> SideQuestionProviderFactory | None:
        value = self._binding.values().get(SIDE_QUESTION_PROVIDER_SLOT.key)
        if value is None:
            return None
        if not callable(getattr(value, "bind", None)):
            raise TypeError(
                "interaction.side_question returned an invalid Provider factory"
            )
        return cast(SideQuestionProviderFactory, value)

    @property
    def is_closed(self) -> bool:
        return self._binding.is_closed

    @property
    def profile(self) -> ResolvedRuntimeProfile:
        return self._binding.profile

    @property
    def ownership_state(self) -> str:
        return self._ownership_state

    def _begin_graph_construction(self) -> None:
        if self._ownership_state != "root_owned":
            raise RuntimeError(
                "side-question binding is not owned by the Session construction root"
            )
        self._ownership_state = "graph_constructing"

    def _commit_graph_ownership(self) -> None:
        if self._ownership_state != "graph_constructing":
            raise RuntimeError("side-question binding is not being graph-constructed")
        self._ownership_state = "graph_owned"

    def _restore_root_ownership(self) -> None:
        if self._ownership_state != "graph_constructing":
            raise RuntimeError("side-question binding is not being graph-constructed")
        self._ownership_state = "root_owned"

    def _dispose_graph_owned(self) -> None:
        self._dispose_owned(expected="graph_owned")

    def dispose(self) -> None:
        self._dispose_owned(expected="root_owned")

    def _dispose_owned(self, *, expected: str) -> None:
        if self._ownership_state == "disposed":
            return
        if self._ownership_state != expected:
            raise RuntimeError(
                "side-question binding has a different lifecycle owner: "
                f"{self._ownership_state}"
            )
        self._binder.dispose_sync(self._binding)
        self._ownership_state = "disposed"


def bind_legacy_side_question(
    profile: ResolvedRuntimeProfile,
    *,
    additional_implementations: Iterable[RuntimeCapabilityImplementation] = (),
) -> LegacySideQuestionBinding:
    """Bind only ``interaction.side_question`` from a full resolved Profile."""

    focused_profile = ResolvedRuntimeProfile(
        product_id=profile.product_id,
        capabilities=tuple(
            capability
            for capability in profile.capabilities
            if capability.slot.key == SIDE_QUESTION_PROVIDER_SLOT.key
        ),
        schema_version=profile.schema_version,
    )
    binder = RuntimeProfileBinder(
        RuntimeCapabilityRegistry(
            (
                *(
                    implementation
                    for implementation in standard_capability_composition_implementations()
                    if implementation.slot == SIDE_QUESTION_PROVIDER_SLOT.key
                ),
                *(
                    implementation
                    for implementation in additional_implementations
                    if implementation.slot == SIDE_QUESTION_PROVIDER_SLOT.key
                ),
            )
        )
    )
    return LegacySideQuestionBinding(
        _binding=binder.bind_sync(focused_profile),
        _binder=binder,
    )


__all__ = ["LegacySideQuestionBinding", "bind_legacy_side_question"]
