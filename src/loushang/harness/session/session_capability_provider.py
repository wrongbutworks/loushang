"""Side-question Provider slice for the ``harness.session`` Capability."""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field

from loushang.foundation.json import dump_json_value
from loushang.harness.capabilities.contracts import CapabilityContractRange
from loushang.harness.capabilities.provider_binding import (
    CapabilityBundleProviderBinding,
    CapabilityBundleValue,
    CapabilityFacetBinding,
    CapabilityProviderContext,
)
from loushang.harness.capabilities.providers import CapabilityBundleProvider
from loushang.harness.capabilities.session_contracts import (
    SESSION_CAPABILITY_DEFINITION,
    SIDE_QUESTION_FACET,
)
from loushang.harness.runtime.side_question import (
    SideQuestionAnswer,
    SideQuestionCoordinator,
    SideQuestionProvider,
    SideQuestionProviderFactory,
    SideQuestionUpdate,
)
from loushang.harness.session.legacy_side_question import LegacySideQuestionBinding


@dataclass(frozen=True)
class _SideQuestionFacet:
    _coordinator: SideQuestionCoordinator | None = field(
        repr=False,
        compare=False,
    )

    async def ask(
        self,
        question: str,
        *,
        on_update: SideQuestionUpdate | None = None,
    ) -> SideQuestionAnswer:
        coordinator = self._coordinator
        if coordinator is None:
            raise RuntimeError("Side questions are not available for this session.")
        return await coordinator.ask(question, on_update=on_update)

    def cancel(self) -> bool:
        coordinator = self._coordinator
        return coordinator.cancel() if coordinator is not None else False

    def owns_current_task(self) -> bool:
        coordinator = self._coordinator
        return coordinator.owns_current_task() if coordinator is not None else False

    async def cancel_and_wait(self) -> bool:
        coordinator = self._coordinator
        if coordinator is None:
            return False
        return await coordinator.cancel_and_wait()


def session_side_question_provider_binding(
    *,
    scope_instance_id: str,
    staged_candidate: LegacySideQuestionBinding,
    bind_provider: Callable[[SideQuestionProviderFactory], SideQuestionProvider],
    provider_id: str = "harness.session.side-question.standard",
    source_id: str = "builtin",
) -> CapabilityBundleProviderBinding:
    """Transfer one focused Profile binding into the Session graph.

    ``bind_provider`` is the narrow Product port that binds the selected factory
    to its live Session context. It is never fingerprinted or projected.
    """

    if staged_candidate.ownership_state != "root_owned":
        raise RuntimeError("side-question candidate is not root-owned")
    provider = CapabilityBundleProvider(
        capability_id=SESSION_CAPABILITY_DEFINITION.capability_id,
        provider_id=provider_id,
        implementation_version=1,
        compatible_contract=CapabilityContractRange.exact(
            SESSION_CAPABILITY_DEFINITION.contract_version
        ),
        facets=SESSION_CAPABILITY_DEFINITION.facets,
        source_id=source_id,
        selection_rule="Product-admitted side-question selection",
    )

    def create(_context: CapabilityProviderContext) -> CapabilityBundleValue:
        staged_candidate._begin_graph_construction()
        try:
            factory = staged_candidate.provider_factory
            if factory is None:
                coordinator = None
            else:
                selected_provider = bind_provider(factory)
                if inspect.isawaitable(selected_provider):
                    close = getattr(selected_provider, "close", None)
                    if callable(close):
                        close()
                    raise TypeError("side-question Provider binding must be synchronous")
                if not callable(getattr(selected_provider, "ask", None)) or not callable(
                    getattr(selected_provider, "cancel", None)
                ):
                    raise TypeError(
                        "side-question factory returned an invalid Provider"
                    )
                coordinator = SideQuestionCoordinator(selected_provider)
            value = CapabilityBundleValue(
                facets=(
                    CapabilityFacetBinding(
                        SIDE_QUESTION_FACET,
                        _SideQuestionFacet(coordinator),
                    ),
                )
            )
            staged_candidate._commit_graph_ownership()
        except BaseException:
            if staged_candidate.ownership_state == "graph_constructing":
                staged_candidate._restore_root_ownership()
            raise
        return value

    async def dispose(value: CapabilityBundleValue) -> None:
        facet = value.require(SIDE_QUESTION_FACET)
        if not isinstance(facet, _SideQuestionFacet):
            raise TypeError("Session Provider received an alien Bundle value")
        errors: list[BaseException] = []
        try:
            await facet.cancel_and_wait()
        except BaseException as exc:
            errors.append(exc)
        try:
            staged_candidate._dispose_graph_owned()
        except BaseException as exc:
            errors.append(exc)
        if errors:
            primary = errors[0]
            for cleanup_error in errors[1:]:
                primary.add_note(
                    "Additional side-question Provider cleanup failure: "
                    f"{cleanup_error!r}"
                )
            raise primary

    return CapabilityBundleProviderBinding(
        provider=provider,
        scope_instance_id=scope_instance_id,
        binding_input_fingerprint=_binding_input_fingerprint(
            staged_candidate=staged_candidate,
            scope_instance_id=scope_instance_id,
            provider_id=provider_id,
        ),
        create=create,
        dispose=dispose,
    )


def _binding_input_fingerprint(
    *,
    staged_candidate: LegacySideQuestionBinding,
    scope_instance_id: str,
    provider_id: str,
) -> str:
    payload = dump_json_value(
        {
            "schemaVersion": 1,
            "capabilityId": SESSION_CAPABILITY_DEFINITION.capability_id,
            "contractVersion": SESSION_CAPABILITY_DEFINITION.contract_version,
            "providerId": provider_id,
            "providerVersion": 1,
            "scopeInstanceId": scope_instance_id,
            "profile": staged_candidate.profile.snapshot().to_json(),
        },
        name="Session side-question binding-input fingerprint",
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = ["session_side_question_provider_binding"]
