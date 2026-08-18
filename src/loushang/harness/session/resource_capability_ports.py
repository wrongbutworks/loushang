"""Stable focused ports for the staged-to-mounted Resources handoff."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

from loushang.harness.capabilities.composition_runtime import (
    CapabilityCompositionRuntime,
)
from loushang.harness.capabilities.packs import (
    CapabilityPack,
    CapabilityPackComposition,
)
from loushang.harness.capabilities.prompt import PreparedPrompt, PromptSection
from loushang.harness.resources.activation import ResourceActivation
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session.session_capability_consumer import (
    SessionResourceCompositionCapabilityConsumer,
)

T = TypeVar("T")


class SessionResourceCapabilityPorts:
    """Route narrow calls from one root-owned candidate to mounted Consumers.

    The object has no graph access and owns no live mechanism.  Its stable
    children may be captured by synchronous Session controllers before the
    asynchronous graph publication.  Installation switches every child to
    generation-scoped Consumers in one no-await window.
    """

    def __init__(self, candidate: CapabilityCompositionRuntime) -> None:
        if candidate.ownership_state != "root_owned":
            raise ValueError("resource ports require a root-owned candidate")
        self._candidate: CapabilityCompositionRuntime | None = candidate
        self._consumer: SessionResourceCompositionCapabilityConsumer | None = None
        self.activation = _ActivationPort(self)
        self.skills = _SkillActivationPort(self)
        self.prompt = _PromptPort(self)
        self.tools = _ToolPackPort(self)
        self.commands = _CommandPackPort(self)

    def install(
        self,
        *,
        consumer: SessionResourceCompositionCapabilityConsumer,
    ) -> None:
        if self._candidate is None:
            raise RuntimeError("resource Consumers are already installed")
        self._consumer = consumer
        self._candidate = None

    def invalidate(self) -> None:
        self._candidate = None
        self._consumer = None

    def _candidate_or_raise(self) -> CapabilityCompositionRuntime:
        candidate = self._candidate
        if candidate is None or candidate.ownership_state != "root_owned":
            raise RuntimeError("Resources Capability is not mounted")
        return candidate

    def _activation_or_candidate(
        self,
    ) -> SessionResourceCompositionCapabilityConsumer | CapabilityCompositionRuntime:
        return self._consumer or self._candidate_or_raise()

    def _prompt_or_candidate(
        self,
    ) -> SessionResourceCompositionCapabilityConsumer | CapabilityCompositionRuntime:
        return self._consumer or self._candidate_or_raise()

    def _tools_or_candidate(
        self,
    ) -> SessionResourceCompositionCapabilityConsumer | CapabilityCompositionRuntime:
        return self._consumer or self._candidate_or_raise()

    def _commands_or_candidate(
        self,
    ) -> SessionResourceCompositionCapabilityConsumer | CapabilityCompositionRuntime:
        return self._consumer or self._candidate_or_raise()


@dataclass(frozen=True)
class _ActivationPort:
    owner: SessionResourceCapabilityPorts

    def activate(self, bundle: ResourceBundle | None) -> ResourceActivation:
        target = self.owner._activation_or_candidate()
        if isinstance(target, SessionResourceCompositionCapabilityConsumer):
            return target.activate(bundle)
        return target.activate_resources(bundle)


@dataclass(frozen=True)
class _SkillActivationPort:
    owner: SessionResourceCapabilityPorts

    def apply(
        self,
        bundle: ResourceBundle,
        disabled_skills: tuple[str, ...] | list[str],
    ) -> ResourceBundle:
        target = self.owner._activation_or_candidate()
        if isinstance(target, SessionResourceCompositionCapabilityConsumer):
            return target.apply_skill_activation(bundle, disabled_skills)
        return target.apply_skill_activation(bundle, disabled_skills)


@dataclass(frozen=True)
class _PromptPort:
    owner: SessionResourceCapabilityPorts

    def compose(self, sections: Iterable[PromptSection]) -> PreparedPrompt:
        target = self.owner._prompt_or_candidate()
        if isinstance(target, SessionResourceCompositionCapabilityConsumer):
            return target.compose_prompt(sections)
        return target.prompt_section_composer.compose(sections)


@dataclass(frozen=True)
class _ToolPackPort:
    owner: SessionResourceCapabilityPorts

    def compose(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        target = self.owner._tools_or_candidate()
        if isinstance(target, SessionResourceCompositionCapabilityConsumer):
            return target.compose_tools(packs)
        return target.tool_pack_composer.compose(packs)


@dataclass(frozen=True)
class _CommandPackPort:
    owner: SessionResourceCapabilityPorts

    def compose(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        target = self.owner._commands_or_candidate()
        if isinstance(target, SessionResourceCompositionCapabilityConsumer):
            return target.compose_commands(packs)
        return target.command_pack_composer.compose(packs)


__all__ = ["SessionResourceCapabilityPorts"]
