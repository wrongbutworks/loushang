"""Current-Session adapter for Agent sampling and AI's transport barrier."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import cast

from loushang.agent import ModelCallPreparation
from loushang.ai.json_codec import serialize_message
from loushang.ai.options import CallOptions
from loushang.ai.prepared_request import (
    PreparedModelRequest,
    PreparedRequestCommitter,
)
from loushang.ai.structured import StructuredOutputOptions
from loushang.foundation.json import JSONValue, require_json_mapping, require_json_value
from loushang.harness.capabilities import (
    CapabilityBundleProvider,
    CapabilityBundleProviderBinding,
    CapabilityBundleValue,
    CapabilityContractRange,
    CapabilityFacetBinding,
    CapabilityGraphPlanRequest,
    CapabilityProviderContext,
    RuntimeCapabilityGraphBinder,
    RuntimeCapabilityGraphPlanner,
    RuntimeCapabilityGraphProjector,
    RuntimeCapabilityGraphRuntime,
)
from loushang.harness.capabilities.graph_runtime import CapabilityFacetSet
from loushang.harness.capabilities.model_input_contracts import (
    MODEL_INPUT_CAPABILITY_DEFINITION,
    MODEL_INPUT_PREPARATION_FACET,
    MODEL_INPUT_PREPARATION_REQUIREMENT,
)
from loushang.harness.runtime import ResolvedRuntimeProfile
from loushang.harness.transcript import (
    AgentTranscriptSession,
    ModelInputRuntimeReferences,
)

CurrentSessionPredicate = Callable[[], bool]


class SessionModelCallPreparer:
    """Bind one fresh transcript committer to a final Agent-level model input."""

    def __init__(
        self,
        *,
        transcript: AgentTranscriptSession,
        graph_runtime: RuntimeCapabilityGraphRuntime,
        is_current: CurrentSessionPredicate,
    ) -> None:
        if not isinstance(transcript, AgentTranscriptSession):
            raise TypeError("model-call preparation requires AgentTranscriptSession")
        if not isinstance(graph_runtime, RuntimeCapabilityGraphRuntime):
            raise TypeError(
                "model-call preparation requires RuntimeCapabilityGraphRuntime"
            )
        if not callable(is_current):
            raise TypeError("model-call preparation requires a current-Session check")
        self._transcript = transcript
        self._projector = RuntimeCapabilityGraphProjector(graph_runtime)
        self._is_current = is_current

    def __call__(self, preparation: ModelCallPreparation) -> CallOptions:
        if not isinstance(preparation, ModelCallPreparation):
            raise TypeError("model-call preparation requires ModelCallPreparation")
        if self._is_current() is not True:
            raise RuntimeError("Session is not current; model transport is forbidden")
        if preparation.options.prepared_request_committer is not None:
            raise RuntimeError(
                "durable Session cannot replace an existing prepared-request committer"
            )

        graph = self._projector.snapshot()
        registrations = self._projector.registration_inventory()
        committer = self._transcript.create_model_input_committer(
            purpose=preparation.purpose,
            logical_input=_logical_input(preparation),
            runtime_references=ModelInputRuntimeReferences.from_snapshots(
                graph,
                registrations,
            ),
        )
        return replace(
            preparation.options,
            prepared_request_committer=_CurrentSessionCommitter(
                committer=committer,
                is_current=self._is_current,
            ),
        )


class _CurrentSessionCommitter(PreparedRequestCommitter):
    """Carry current-Session ownership through AI's final commit barrier."""

    def __init__(
        self,
        *,
        committer: PreparedRequestCommitter,
        is_current: CurrentSessionPredicate,
    ) -> None:
        self._committer = committer
        self._is_current = is_current

    async def commit_prepared_request(self, request: PreparedModelRequest) -> None:
        self._require_current()
        await self._committer.commit_prepared_request(request)
        self._require_current()

    @property
    def model_input_snapshot_ids(self) -> tuple[str, ...]:
        commits = getattr(self._committer, "commits", ())
        return tuple(
            commit.snapshot_id
            for commit in commits
            if isinstance(getattr(commit, "snapshot_id", None), str)
        )

    def _require_current(self) -> None:
        if self._is_current() is not True:
            raise RuntimeError("Session is not current; model transport is forbidden")


@dataclass(frozen=True)
class SessionModelCallCapabilityConsumer:
    """Adapt the declared preparation facet without receiving the graph runtime."""

    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != MODEL_INPUT_PREPARATION_REQUIREMENT:
            raise ValueError("model-call Consumer received the wrong facet view")

    def prepare(self, preparation: ModelCallPreparation) -> CallOptions:
        preparer = cast(
            SessionModelCallPreparer,
            self.facets.require(MODEL_INPUT_PREPARATION_FACET),
        )
        return preparer(preparation)


class SessionModelCallRuntime:
    """Own the Session graph node and expose only the Agent preparation seam."""

    def __init__(
        self,
        *,
        transcript: AgentTranscriptSession,
        profile: ResolvedRuntimeProfile,
        runtime_id: str,
        is_current: CurrentSessionPredicate,
    ) -> None:
        if not isinstance(transcript, AgentTranscriptSession):
            raise TypeError("model-call runtime requires AgentTranscriptSession")
        if not isinstance(profile, ResolvedRuntimeProfile):
            raise TypeError("model-call runtime requires ResolvedRuntimeProfile")
        if not isinstance(runtime_id, str) or not runtime_id.strip():
            raise ValueError("model-call runtime id must be non-empty")
        if not callable(is_current):
            raise TypeError("model-call runtime requires a current-Session check")

        self._transcript = transcript
        self._is_current = is_current
        self._runtime = RuntimeCapabilityGraphRuntime(
            product_id=profile.product_id,
            runtime_id=runtime_id,
            profile_fingerprint=_fingerprint(profile.snapshot().to_json()),
        )
        self._binder = RuntimeCapabilityGraphBinder()
        self._bind_lock = asyncio.Lock()
        self._consumer: SessionModelCallCapabilityConsumer | None = None

        provider = CapabilityBundleProvider(
            capability_id=MODEL_INPUT_CAPABILITY_DEFINITION.capability_id,
            provider_id="harness.model_input.standard",
            implementation_version=1,
            compatible_contract=CapabilityContractRange.exact(1),
            facets=MODEL_INPUT_CAPABILITY_DEFINITION.facets,
            required_authorities=frozenset({"transcript"}),
            source_id="builtin",
            selection_rule="Product durable Model Input selection",
        )
        self._plan = RuntimeCapabilityGraphPlanner().plan(
            CapabilityGraphPlanRequest(
                product_id=profile.product_id,
                roots=(MODEL_INPUT_CAPABILITY_DEFINITION.capability_id,),
                definitions=(MODEL_INPUT_CAPABILITY_DEFINITION,),
                providers=(provider,),
            )
        )

        def create(_context: CapabilityProviderContext) -> CapabilityBundleValue:
            return CapabilityBundleValue(
                (
                    CapabilityFacetBinding(
                        MODEL_INPUT_PREPARATION_FACET,
                        SessionModelCallPreparer(
                            transcript=self._transcript,
                            graph_runtime=self._runtime,
                            is_current=self._is_current,
                        ),
                    ),
                )
            )

        self._binding = CapabilityBundleProviderBinding(
            provider=provider,
            scope_instance_id=runtime_id,
            binding_input_fingerprint=_fingerprint(
                {
                    "conversation_id": transcript.header.conversation_id,
                    "runtime_id": runtime_id,
                }
            ),
            create=create,
        )

    @property
    def graph_runtime(self) -> RuntimeCapabilityGraphRuntime:
        return self._runtime

    async def bind(self) -> None:
        if self._consumer is not None:
            return
        async with self._bind_lock:
            if self._consumer is not None:
                return
            await self._binder.bind(self._runtime, self._plan, (self._binding,))
            self._consumer = SessionModelCallCapabilityConsumer(
                self._runtime.capture(MODEL_INPUT_PREPARATION_REQUIREMENT)
            )

    async def prepare(self, preparation: ModelCallPreparation) -> CallOptions:
        await self.bind()
        consumer = self._consumer
        if consumer is None:
            raise RuntimeError("model-call Capability is not bound")
        return consumer.prepare(preparation)

    async def dispose(self) -> None:
        async with self._bind_lock:
            self._consumer = None
            await self._binder.dispose(self._runtime)


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _logical_input(preparation: ModelCallPreparation) -> dict[str, object]:
    context = preparation.context
    return {
        "system_prompt": context.system_prompt,
        "messages": [serialize_message(message) for message in context.messages],
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": require_json_mapping(
                    tool.parameters,
                    name=f"Model Input Tool schema {tool.name!r}",
                ),
            }
            for tool in context.tools or ()
        ],
        "request_options": _request_options(preparation.options),
    }


def _request_options(options: CallOptions) -> dict[str, JSONValue]:
    projected: dict[str, JSONValue] = {}
    for name in (
        "cache_retention",
        "cache_key",
        "max_output_tokens",
        "temperature",
    ):
        value = getattr(options, name)
        if value is not None:
            projected[name] = require_json_value(
                value,
                name=f"Model Input request option {name!r}",
            )

    if options.reasoning is not None:
        projected["reasoning"] = require_json_mapping(
            {
                "enabled": options.reasoning.enabled,
                "effort": options.reasoning.effort,
                "budget_tokens": options.reasoning.budget_tokens,
                "expose_summary": options.reasoning.expose_summary,
            },
            name="Model Input reasoning options",
        )
    if options.tool_choice is not None:
        projected["tool_choice"] = require_json_value(
            options.tool_choice,
            name="Model Input Tool choice",
        )
    if options.output is not None:
        projected["output"] = _structured_output(options.output)
    return projected


def _structured_output(output: StructuredOutputOptions) -> dict[str, JSONValue]:
    projected: dict[str, object] = {
        "mode": output.mode,
        "strict": output.strict,
    }
    if output.schema is not None:
        projected["schema"] = _structured_output_schema(output.schema)
    return require_json_mapping(projected, name="Model Input structured output")


def _structured_output_schema(
    schema: Mapping[str, JSONValue] | type,
) -> dict[str, JSONValue]:
    if isinstance(schema, Mapping):
        return require_json_mapping(schema, name="Model Input structured output schema")
    for method_name in ("model_json_schema", "schema"):
        method = getattr(schema, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, Mapping):
                return require_json_mapping(
                    value,
                    name="Model Input structured output schema",
                )
    raise TypeError("structured output type must expose a JSON schema")


__all__ = [
    "CurrentSessionPredicate",
    "SessionModelCallCapabilityConsumer",
    "SessionModelCallPreparer",
    "SessionModelCallRuntime",
]
