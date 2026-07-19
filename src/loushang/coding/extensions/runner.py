from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from loushang.agent.types import (
    AfterToolCallResult,
    AgentMessage,
    BeforeToolCallResult,
)
from loushang.coding.extensions.hooks import HookDispatcher
from loushang.coding.extensions.loader import ExtensionLoader
from loushang.harness.extensions.context import (
    BoundExtensionContext,
    ExtensionCommandContext,
    ExtensionContext,
    ExtensionRuntimeBindings,
    SessionActionDecision,
    SessionBeforeCompactResult,
    SessionBeforeForkResult,
    SessionBeforeTreeResult,
    SessionRefreshEvent,
    UnboundExtensionContext,
)
from loushang.harness.extensions.registry import (
    source_info_from_extension as _source_info_from_extension,
)
from loushang.harness.extensions.routing import (
    ResolvedExtensionRoute,
    RouteStep,
)
from loushang.harness.extensions.runtime import ExtensionRuntime
from loushang.harness.extensions.types import (
    BeforeAgentStartResult,
    ContextResult,
    LoadedExtension,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.types import (
    ExtensionDescriptor,
)
from loushang.harness.runtime import (
    RuntimeBindingState,
)


class _RunnerContext(UnboundExtensionContext):
    pass


class _BoundExtensionContext(BoundExtensionContext):
    pass


class _RunnerRuntimeState(RuntimeBindingState[ExtensionRuntimeBindings]):
    def __init__(self) -> None:
        super().__init__(
            unbound_message="Extension runner runtime bindings have not been set.",
            stale_message=(
                "Extension context is stale after session replacement or reload."
            ),
        )
        self.flag_values: dict[str, bool | str] = {}


@dataclass(frozen=True)
class _BeforeAgentStartContext:
    base: ExtensionContext
    get_system_prompt: Callable[[], str]

    def __getattr__(self, name: str):
        return getattr(self.base, name)

    @property
    def ui(self):
        return self.base.ui

    @property
    def has_ui(self) -> bool:
        return self.base.has_ui

    @property
    def cwd(self) -> str:
        return self.base.cwd


@dataclass
class _ContextEvent:
    messages: list[AgentMessage]


@dataclass(frozen=True)
class _BeforeAgentStartState:
    system_prompt: str
    extra_messages: tuple[object, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    system_prompt_changed: bool = False


class ExtensionRunner(ExtensionRuntime):
    def __init__(
        self, extensions: list[LoadedExtension | ExtensionDescriptor] | None = None
    ) -> None:
        self._diagnostics: list[ResourceDiagnostic] = []
        self._runtime_state = _RunnerRuntimeState()
        loader = ExtensionLoader()
        loaded_extensions: list[LoadedExtension] = []

        for extension in extensions or []:
            if isinstance(extension, ExtensionDescriptor):
                loaded_extension = loader.load_extension(extension)
                self._diagnostics.extend(loader.get_diagnostics())
                loader = ExtensionLoader()
                if loaded_extension is None:
                    continue
            else:
                loaded_extension = extension
            loaded_extensions.append(loaded_extension)
            self._diagnostics.extend(loaded_extension.diagnostics)
        super().__init__(
            loaded_extensions,
            context_factory=lambda fallback_cwd, extension: self._context_from_runtime(
                fallback_cwd=fallback_cwd,
                extension=extension,
            ),
            resource_context_factory=lambda cwd: _RunnerContext(cwd=cwd),
            diagnostics=self._diagnostics,
            runtime_error_handler=self._emit_runtime_error,
        )
        self._runtime_state.flag_values = self._flag_values
        self._bind_extension_apis()

    def create_command_context(
        self, *, fallback_cwd: str = ""
    ) -> ExtensionCommandContext:
        return self._context_from_runtime(fallback_cwd=fallback_cwd)

    async def emit_user_bash(self, event: object, *, cwd: str = "") -> object | None:
        return await super().emit_user_bash(_event_object(event), cwd=cwd)

    async def emit_event(self, event: object, *, cwd: str = "") -> None:
        event_type = _event_type(event)
        if event_type is None:
            return
        await super().emit_event(
            event_type,
            _event_object(event),
            cwd=cwd,
        )

    def getMessageRenderer(self, custom_type: str):
        return self.get_message_renderer(custom_type)

    def listMessageRenderers(self) -> list[dict[str, object]]:
        return self.list_message_renderers()

    def listExtensions(self) -> list[dict[str, object]]:
        return self.list_extensions()

    def bind_runtime(self, bindings: ExtensionRuntimeBindings) -> None:
        self._runtime_state.bind(bindings)
        self._bind_extension_apis()

    def refresh_runtime(self, bindings: ExtensionRuntimeBindings) -> None:
        self._runtime_state.refresh(bindings)
        self._bind_extension_apis()

    def _bind_extension_apis(self) -> None:
        for extension in self._active_extensions:
            self._bind_extension_api(extension)

    def _bind_extension_api(self, extension: LoadedExtension) -> None:
        binder = getattr(extension.api, "bind_runtime_state", None)
        if callable(binder):
            binder(self._runtime_state)

    def invalidate_contexts(
        self,
        message: str = "Extension context is stale after session replacement or reload.",
    ) -> None:
        self._runtime_state.invalidate(message)

    async def emit_session_start(self, session: object) -> None:
        await self._emit_session_hook("session_start", session)

    async def emit_session_refresh(self, event: SessionRefreshEvent) -> None:
        await self._emit_session_hook("session_refresh", event)

    async def emit_before_agent_start(
        self,
        *,
        prompt: str,
        images: list[object] | None = None,
        system_prompt: str | None = None,
        system_prompt_options: object | None = None,
        cwd: str = "",
    ) -> BeforeAgentStartResult | None:
        prompt_state = [system_prompt or ""]
        context = _BeforeAgentStartContext(
            base=self._context_from_runtime(fallback_cwd=cwd),
            get_system_prompt=lambda: prompt_state[0],
        )

        def event_factory(
            state: _BeforeAgentStartState,
            route: ResolvedExtensionRoute,
        ) -> _ExtensionEvent:
            del route
            prompt_state[0] = state.system_prompt
            return _ExtensionEvent(
                type="before_agent_start",
                prompt=prompt,
                images=images,
                system_prompt=state.system_prompt,
                systemPrompt=state.system_prompt,
                system_prompt_options=system_prompt_options,
                systemPromptOptions=system_prompt_options,
            )

        def reducer(
            state: _BeforeAgentStartState,
            result: object,
            route: ResolvedExtensionRoute,
        ) -> RouteStep[_BeforeAgentStartState]:
            del route
            coerced = _coerce_before_agent_start_result(result)
            if coerced is None:
                return RouteStep(state)
            next_system_prompt = coerced.system_prompt
            if next_system_prompt is None and coerced.system_prompt_append:
                next_system_prompt = (
                    f"{state.system_prompt}\n\n{coerced.system_prompt_append}"
                )
            return RouteStep(
                _BeforeAgentStartState(
                    system_prompt=(
                        next_system_prompt
                        if next_system_prompt is not None
                        else state.system_prompt
                    ),
                    extra_messages=(
                        *state.extra_messages,
                        *coerced.extra_messages,
                    ),
                    diagnostics=(*state.diagnostics, *coerced.diagnostics),
                    system_prompt_changed=(
                        state.system_prompt_changed or next_system_prompt is not None
                    ),
                )
            )

        outcome = await self._plain_diagnostic_router.reduce(
            "before_agent_start",
            _BeforeAgentStartState(system_prompt=system_prompt or ""),
            event_factory=event_factory,
            reducer=reducer,
            context_factory=lambda extension: context,
        )
        state = outcome.state
        prompt_state[0] = state.system_prompt
        diagnostics = list(state.diagnostics)
        if diagnostics:
            self._diagnostics.extend(diagnostics)
        if (
            not state.extra_messages
            and not state.system_prompt_changed
            and not diagnostics
        ):
            return None
        return BeforeAgentStartResult(
            system_prompt=(
                state.system_prompt if state.system_prompt_changed else None
            ),
            extra_messages=list(state.extra_messages),
            diagnostics=diagnostics,
        )

    async def emit_session_shutdown(self, session: object) -> None:
        await self._emit_session_hook("session_shutdown", session)

    async def before_session_switch(
        self, event: object
    ) -> SessionActionDecision | None:
        return await self._emit_decision_hook(
            "session_before_switch", event, fallback_cwd=getattr(event, "cwd", "")
        )

    async def before_session_fork(
        self, event: object
    ) -> SessionBeforeForkResult | None:
        result = await self._emit_decision_hook(
            "session_before_fork",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeForkResult):
            return result
        return SessionBeforeForkResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def before_session_compact(
        self, event: object
    ) -> SessionBeforeCompactResult | None:
        result = await self._emit_decision_hook(
            "session_before_compact",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeCompactResult):
            return result
        return SessionBeforeCompactResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def before_session_tree(
        self, event: object
    ) -> SessionBeforeTreeResult | None:
        result = await self._emit_decision_hook(
            "session_before_tree",
            event,
            fallback_cwd=getattr(event, "cwd", ""),
            result_type=SessionActionDecision,
        )
        if result is None:
            return None
        if isinstance(result, SessionBeforeTreeResult):
            return result
        return SessionBeforeTreeResult(
            cancel=result.cancel,
            diagnostics=result.diagnostics,
        )

    async def emit_context(
        self,
        messages: list[AgentMessage],
        signal: object | None = None,
        *,
        cwd: str = "",
    ) -> list[AgentMessage]:
        del signal

        current_messages = deepcopy(messages)
        context = self._context_from_runtime(fallback_cwd=cwd)

        def reducer(
            state: list[AgentMessage],
            result: object,
            route: ResolvedExtensionRoute,
        ) -> RouteStep[list[AgentMessage]]:
            if not isinstance(result, ContextResult):
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="invalid_extension_context_result",
                        message="context hooks must return ContextResult or None.",
                        source_path=route.extension.source_path,
                    )
                )
                return RouteStep(state)
            if result.diagnostics:
                self._diagnostics.extend(result.diagnostics)
            return RouteStep(
                cast(list[AgentMessage], result.messages)
                if result.messages is not None
                else state
            )

        outcome = await self._plain_diagnostic_router.reduce(
            "context",
            current_messages,
            event_factory=lambda state, route: _ContextEvent(messages=state),
            reducer=reducer,
            context_factory=lambda extension: context,
        )
        return outcome.state

    async def before_tool_call(
        self, event, signal: object | None = None
    ) -> BeforeToolCallResult | None:
        return await self._tool_hook_dispatcher(
            _context_from_agent_event(event).cwd
        ).before_tool_call(event, signal)

    async def after_tool_call(
        self, event, signal: object | None = None
    ) -> AfterToolCallResult | None:
        return await self._tool_hook_dispatcher(
            _context_from_agent_event(event).cwd
        ).after_tool_call(event, signal)

    def _tool_hook_dispatcher(self, fallback_cwd: str) -> HookDispatcher:
        return HookDispatcher(
            self._extensions,
            context_factory=lambda _extension: self._context_from_runtime(
                fallback_cwd=fallback_cwd
            ),
            diagnostics=self._diagnostics,
            runtime_error_handler=lambda extension, event, error: (
                self._emit_runtime_error(
                    extension=extension,
                    event=event,
                    error=error,
                )
            ),
            route_plan=self._route_plan,
        )

    async def _emit_session_hook(self, hook_name: str, session: object) -> None:
        fallback_cwd = _context_from_session(session).cwd
        await self._router.observe(
            hook_name,
            session,
            context_factory=lambda extension: self._context_from_runtime(
                fallback_cwd=fallback_cwd,
                extension=extension,
            ),
        )

    async def _emit_decision_hook(
        self,
        hook_name: str,
        event: object,
        *,
        fallback_cwd: str,
        result_type: type[SessionActionDecision] = SessionActionDecision,
    ) -> SessionActionDecision | None:
        context = self._context_from_runtime(fallback_cwd=fallback_cwd)

        def reducer(
            state: SessionActionDecision | None,
            result: object,
            route: ResolvedExtensionRoute,
        ) -> RouteStep[SessionActionDecision | None]:
            if not isinstance(result, result_type):
                expected_name = result_type.__name__
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code=f"invalid_extension_{hook_name}_decision",
                        message=(
                            f"{hook_name} hooks must return {expected_name} or None."
                        ),
                        source_path=route.extension.source_path,
                    )
                )
                return RouteStep(state)
            if result.diagnostics:
                self._diagnostics.extend(result.diagnostics)
            return RouteStep(result)

        outcome = await self._router.reduce(
            hook_name,
            None,
            event_factory=lambda state, route: event,
            reducer=reducer,
            context_factory=lambda extension: context,
        )
        return outcome.state

    def _context_from_runtime(
        self,
        *,
        fallback_cwd: str = "",
        extension: LoadedExtension | None = None,
    ) -> ExtensionContext:
        if not self._runtime_state.is_bound:
            return cast(
                ExtensionContext,
                _RunnerContext(
                    cwd=fallback_cwd,
                    get_flag_value=self.get_flag_value,
                ),
            )
        return cast(
            ExtensionContext,
            _BoundExtensionContext(
                self._runtime_state.capture(),
                (
                    _source_info_from_extension(extension)
                    if extension is not None
                    else None
                ),
                get_flag_value=self.get_flag_value,
            ),
        )

    def _emit_runtime_error(
        self,
        extension: LoadedExtension,
        event: str,
        error: Exception,
    ) -> None:
        bindings = self._runtime_state.bindings
        callback = getattr(bindings, "on_error", None) if bindings is not None else None
        if not callable(callback):
            return
        callback(
            {
                "extensionPath": str(extension.source_path),
                "event": event,
                "error": str(error),
            }
        )


def _context_from_session(session: object) -> _RunnerContext:
    session_manager = getattr(session, "session_manager", None)
    get_cwd = getattr(session_manager, "get_cwd", None)
    if callable(get_cwd):
        return _RunnerContext(cwd=str(get_cwd()))
    return _RunnerContext(cwd="")


def _context_from_agent_event(event: object) -> _RunnerContext:
    agent_context = getattr(event, "context", None)
    messages = getattr(agent_context, "messages", None)
    if isinstance(messages, list):
        return _RunnerContext(cwd="")
    return _RunnerContext(cwd="")


def _event_type(event: object) -> str | None:
    if isinstance(event, dict):
        value = event.get("type")
        return value if isinstance(value, str) else None
    value = getattr(event, "type", None)
    return value if isinstance(value, str) else None


def _event_object(event: object) -> object:
    if not isinstance(event, dict):
        return event
    values = dict(event)
    values.update(_event_aliases(values))
    return _ExtensionEvent(**values)


def _event_aliases(values: dict[str, object]) -> dict[str, object]:
    aliases: dict[str, object] = {}
    alias_names = {
        "assistant_message_event": "assistantMessageEvent",
        "tool_call_id": "toolCallId",
        "tool_name": "toolName",
        "tool_results": "toolResults",
        "turn_index": "turnIndex",
        "is_error": "isError",
        "partial_result": "partialResult",
        "new_leaf_id": "newLeafId",
        "old_leaf_id": "oldLeafId",
        "summary_entry": "summaryEntry",
        "compaction_entry": "compactionEntry",
        "from_extension": "fromExtension",
        "exclude_from_context": "excludeFromContext",
        "previous_model": "previousModel",
    }
    for source_name, alias_name in alias_names.items():
        if source_name in values:
            aliases[alias_name] = values[source_name]
    return aliases


@dataclass
class _ExtensionEvent:
    def __init__(self, **values: object) -> None:
        for key, value in values.items():
            setattr(self, key, value)


def _coerce_before_agent_start_result(result: object) -> BeforeAgentStartResult | None:
    if result is None:
        return None
    if isinstance(result, BeforeAgentStartResult):
        return result
    if isinstance(result, dict):
        system_prompt = result.get("systemPrompt", result.get("system_prompt"))
        system_prompt_append = result.get(
            "systemPromptAppend", result.get("system_prompt_append", "")
        )
        extra_messages = result.get(
            "messages", result.get("extraMessages", result.get("extra_messages", []))
        )
        diagnostics = result.get("diagnostics", [])
        return BeforeAgentStartResult(
            system_prompt=system_prompt if isinstance(system_prompt, str) else None,
            system_prompt_append=system_prompt_append
            if isinstance(system_prompt_append, str)
            else "",
            extra_messages=extra_messages if isinstance(extra_messages, list) else [],
            diagnostics=diagnostics if isinstance(diagnostics, list) else [],
        )
    return None
