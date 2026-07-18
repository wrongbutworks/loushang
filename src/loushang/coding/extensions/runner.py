from __future__ import annotations

import inspect
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from loushang.agent.types import (
    AfterToolCallResult,
    AgentMessage,
    BeforeToolCallResult,
)
from loushang.coding.extensions.hooks import HookDispatcher
from loushang.coding.extensions.loader import ExtensionLoader
from loushang.coding.extensions.types import (
    BeforeAgentStartResult,
    ContextResult,
    ExtensionCommandContext,
    ExtensionContext,
    ExtensionRuntimeBindings,
    InputEventResult,
    LoadedExtension,
    ResolvedCommand,
    ResolvedFlag,
    ResolvedShortcut,
    SessionActionDecision,
    SessionBeforeCompactResult,
    SessionBeforeForkResult,
    SessionBeforeTreeResult,
    SessionRefreshEvent,
)
from loushang.harness.extensions.dispatch import ExtensionDispatcher
from loushang.harness.extensions.manifest import ExtensionManifest
from loushang.harness.extensions.registry import (
    resolve_extension_registry,
)
from loushang.harness.extensions.registry import (
    source_info_from_extension as _source_info_from_extension,
)
from loushang.harness.extensions.resources import ExtensionResourceRuntime
from loushang.harness.extensions.routing import (
    ExtensionRoutePlan,
    ExtensionRouter,
    ResolvedExtensionRoute,
    RouteStep,
)
from loushang.harness.extensions.types import extension_is_active
from loushang.harness.extensions.wrapper import wrap_registered_tool_definition
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.source import SourceInfo
from loushang.harness.resources.types import (
    ExtensionDescriptor,
    ResourceBundle,
)
from loushang.harness.runtime import (
    BoundProductRuntimeContext,
    RuntimeBindingState,
    UnboundProductRuntimeContext,
)
from loushang.harness.tools.core import ToolDefinition

_UNSUPPORTED_THEME_MESSAGE = "Theme switching not supported in RPC mode"


class _RunnerContext(UnboundProductRuntimeContext):
    pass


class _BoundExtensionContext(BoundProductRuntimeContext):
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
    def hasUI(self) -> bool:
        return self.base.hasUI

    @property
    def has_ui(self) -> bool:
        return self.base.has_ui

    @property
    def cwd(self) -> str:
        return self.base.cwd

    def getSystemPrompt(self) -> str:
        return self.get_system_prompt()


@dataclass
class _ContextEvent:
    messages: list[AgentMessage]


@dataclass(frozen=True)
class _BeforeAgentStartState:
    system_prompt: str
    extra_messages: tuple[object, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()
    system_prompt_changed: bool = False


class ExtensionRunner:
    def __init__(
        self, extensions: list[LoadedExtension | ExtensionDescriptor] | None = None
    ) -> None:
        self._diagnostics: list[ResourceDiagnostic] = []
        self._extensions: list[LoadedExtension] = []
        self._active_extensions: list[LoadedExtension] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_source_info_by_name: dict[str, SourceInfo[Path]] = {}
        self._command_diagnostics: list[ResourceDiagnostic] = []
        self._flag_diagnostics: list[ResourceDiagnostic] = []
        self._shortcut_diagnostics: list[ResourceDiagnostic] = []
        self._registered_commands: list[ResolvedCommand] = []
        self._registered_commands_by_invocation_name: dict[str, ResolvedCommand] = {}
        self._resolved_flags: list[ResolvedFlag] = []
        self._resolved_shortcuts: list[ResolvedShortcut] = []
        self._runtime_state = _RunnerRuntimeState()
        loader = ExtensionLoader()

        for extension in extensions or []:
            if isinstance(extension, ExtensionDescriptor):
                loaded_extension = loader.load_extension(extension)
                self._diagnostics.extend(loader.get_diagnostics())
                loader = ExtensionLoader()
                if loaded_extension is None:
                    continue
            else:
                loaded_extension = extension
            self._extensions.append(loaded_extension)
            if extension_is_active(loaded_extension):
                self._active_extensions.append(loaded_extension)
                self._bind_extension_api(loaded_extension)
            self._diagnostics.extend(loaded_extension.diagnostics)

        self._route_plan = ExtensionRoutePlan.from_extensions(
            self._extensions,
            diagnostics=self._diagnostics,
        )

        def runtime_error_handler(extension, event, error) -> None:
            self._emit_runtime_error(
                extension=extension,
                event=event,
                error=error,
            )

        self._router = ExtensionRouter(
            self._route_plan,
            diagnostics=self._diagnostics,
            runtime_error_handler=runtime_error_handler,
            include_route_id_in_error_metadata=False,
        )
        self._plain_diagnostic_router = ExtensionRouter(
            self._route_plan,
            diagnostics=self._diagnostics,
            runtime_error_handler=runtime_error_handler,
            include_route_id_in_error_metadata=False,
            include_provenance_in_error_metadata=False,
        )
        self._apply_registry_snapshot()

    def get_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._diagnostics)

    def get_command_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._command_diagnostics)

    def get_flag_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._flag_diagnostics)

    def get_shortcut_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._shortcut_diagnostics)

    def get_registered_commands(self) -> list[ResolvedCommand]:
        return list(self._registered_commands)

    def get_command(self, invocation_name: str) -> ResolvedCommand | None:
        return self._registered_commands_by_invocation_name.get(invocation_name)

    def _extension_by_name(self, name: str) -> LoadedExtension:
        for extension in self._active_extensions:
            if extension.name == name:
                return extension
        return LoadedExtension(name=name, source_path=Path("<unknown>"))

    async def get_command_argument_completions(
        self, invocation_name: str, prefix: str
    ) -> list[object] | None:
        command = self.get_command(invocation_name)
        if command is None or command.get_argument_completions is None:
            return None
        try:
            result = command.get_argument_completions(prefix)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="extension_command_argument_completions_failed",
                    message=f"Extension command argument completions failed: {exc}",
                    source_path=command.source_info.path,
                )
            )
            self._emit_runtime_error(
                extension=self._extension_by_name(command.extension_name),
                event="command_argument_completions",
                error=exc,
            )
            return None
        if result is None:
            return None
        if not isinstance(result, list):
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="invalid_extension_command_argument_completions",
                    message="Command argument completions must return a list or None.",
                    source_path=command.source_info.path,
                )
            )
            return None
        return result

    def get_flags(self) -> list[ResolvedFlag]:
        return list(self._resolved_flags)

    def get_shortcuts(self) -> list[ResolvedShortcut]:
        return list(self._resolved_shortcuts)

    def set_flag_value(self, name: str, value: bool | str) -> None:
        self._runtime_state.flag_values[name] = value

    def get_flag_values(self) -> dict[str, bool | str]:
        return dict(self._runtime_state.flag_values)

    def create_command_context(
        self, *, fallback_cwd: str = ""
    ) -> ExtensionCommandContext:
        return self._context_from_runtime(fallback_cwd=fallback_cwd)

    def has_handlers(self, hook_name: str) -> bool:
        return self._dispatcher(fallback_cwd="").has_handlers(hook_name)

    async def emit_user_bash(self, event: object, *, cwd: str = "") -> object | None:
        return await self._dispatcher(fallback_cwd=cwd).dispatch_first_truthy(
            "user_bash",
            _event_object(event),
        )

    async def emit_event(self, event: object, *, cwd: str = "") -> None:
        event_type = _event_type(event)
        if event_type is None:
            return
        await self._dispatcher(fallback_cwd=cwd).dispatch(
            event_type,
            _event_object(event),
        )

    async def emit_input(
        self,
        text: str,
        images: list[object] | None = None,
        *,
        source: str = "interactive",
        cwd: str = "",
    ) -> InputEventResult:
        return await self._dispatcher(fallback_cwd=cwd).dispatch_input(
            text,
            images,
            source=source,
        )

    def list_tool_definitions(self) -> list[ToolDefinition]:
        return list(self._tool_definitions)

    def get_tool_source_info(self, name: str) -> SourceInfo[Path] | None:
        return self._tool_source_info_by_name.get(name)

    def get_message_renderer(self, custom_type: str):
        for extension in self._active_extensions:
            renderer = extension.message_renderers.get(custom_type)
            if renderer is not None:
                return renderer
        return None

    def getMessageRenderer(self, custom_type: str):
        return self.get_message_renderer(custom_type)

    def list_message_renderers(self) -> list[dict[str, object]]:
        renderers: list[dict[str, object]] = []
        for extension in self._active_extensions:
            source_info = _source_info_from_extension(extension)
            for custom_type in extension.message_renderers:
                renderers.append(
                    {
                        "custom_type": custom_type,
                        "customType": custom_type,
                        "extension_name": extension.name,
                        "extensionName": extension.name,
                        "source_info": _serialize_source_info(source_info),
                        "sourceInfo": _serialize_source_info(source_info),
                    }
                )
        return renderers

    def listMessageRenderers(self) -> list[dict[str, object]]:
        return self.list_message_renderers()

    def get_diagnostic_snapshot(self) -> dict[str, object]:
        return {
            "total": len(self._diagnostics),
            "commands": len(self._command_diagnostics),
            "flags": len(self._flag_diagnostics),
            "shortcuts": len(self._shortcut_diagnostics),
            "diagnostics": [
                {
                    "code": diagnostic.code,
                    "message": diagnostic.message,
                    "sourcePath": diagnostic.source_path.as_posix()
                    if diagnostic.source_path is not None
                    else None,
                    "resourceId": diagnostic.resource_id,
                    "resourceType": diagnostic.resource_type,
                    "sourceKind": diagnostic.source_kind,
                    "metadata": dict(diagnostic.metadata),
                }
                for diagnostic in self._diagnostics
            ],
        }

    def list_extensions(self) -> list[dict[str, object]]:
        return [
            _extension_visibility_snapshot(extension, diagnostics=self._diagnostics)
            for extension in self._extensions
        ]

    def listExtensions(self) -> list[dict[str, object]]:
        return self.list_extensions()

    def discover_resources(
        self, bundle: ResourceBundle, *, reason: str = "refresh"
    ) -> ResourceBundle:
        del reason
        return self._resource_runtime().discover(
            bundle,
            context=_RunnerContext(cwd=str(bundle.cwd)),
        )

    async def discover_resources_async(
        self, bundle: ResourceBundle, *, reason: str = "refresh"
    ) -> ResourceBundle:
        del reason
        return await self._resource_runtime().discover_async(
            bundle,
            context=_RunnerContext(cwd=str(bundle.cwd)),
        )

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

    def _apply_registry_snapshot(self) -> None:
        registry = resolve_extension_registry(self._active_extensions)
        self._diagnostics.extend(registry.diagnostics)
        self._flag_diagnostics.extend(registry.flag_diagnostics)
        self._shortcut_diagnostics.extend(registry.shortcut_diagnostics)
        self._registered_commands.extend(registry.commands)
        self._registered_commands_by_invocation_name.update(registry.command_index())
        self._resolved_flags.extend(registry.flags)
        self._resolved_shortcuts.extend(registry.shortcuts)
        for name, value in registry.flag_defaults.items():
            self._runtime_state.flag_values.setdefault(name, value)
        for registration in registry.tools:
            source_info = registration.source_info

            def context_factory(
                source_info: SourceInfo[Path] = source_info,
            ) -> ExtensionContext:
                return self._context_from_runtime(
                    fallback_cwd=str(source_info.path.parent)
                )

            self._tool_source_info_by_name[registration.definition.name] = source_info
            self._tool_definitions.append(
                wrap_registered_tool_definition(
                    registration.definition,
                    context_factory,
                )
            )

    def _dispatcher(self, *, fallback_cwd: str) -> ExtensionDispatcher:
        return ExtensionDispatcher(
            self._extensions,
            context_factory=lambda extension: self._context_from_runtime(
                fallback_cwd=fallback_cwd,
                extension=extension,
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

    def _resource_runtime(self) -> ExtensionResourceRuntime:
        return ExtensionResourceRuntime(
            self._extensions,
            diagnostics=self._diagnostics,
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
                    get_flag_value=self._runtime_state.flag_values.get,
                    unsupported_theme_message=_UNSUPPORTED_THEME_MESSAGE,
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
                get_flag_value=self._runtime_state.flag_values.get,
                unsupported_theme_message=_UNSUPPORTED_THEME_MESSAGE,
            ),
        )

    def _emit_runtime_error(
        self, *, extension: LoadedExtension, event: str, error: Exception
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


def _extension_visibility_snapshot(
    extension: LoadedExtension,
    *,
    diagnostics: list[ResourceDiagnostic],
) -> dict[str, object]:
    manifest = cast(ExtensionManifest | None, extension.manifest)
    policy = extension.policy
    source_info = _source_info_from_extension(extension)
    extension_id = manifest.id if manifest is not None else extension.name
    extension_name = manifest.name if manifest is not None else extension.name
    manifest_path = _extension_manifest_path(extension)
    surfaces = [_serialize_surface(surface) for surface in extension.surfaces]
    return {
        "id": extension_id,
        "name": extension_name,
        "runtimeName": extension.name,
        "version": manifest.version if manifest is not None else None,
        "description": manifest.description if manifest is not None else None,
        "sourcePath": source_info.path.as_posix(),
        "manifestPath": manifest_path.as_posix() if manifest_path is not None else None,
        "enabled": policy.enabled if policy is not None else True,
        "permissionLevel": (
            policy.permission_level
            if policy is not None
            else manifest.permissions.level
            if manifest is not None
            else "safe"
        ),
        "capabilities": list(
            policy.capabilities
            if policy is not None
            else manifest.permissions.capabilities
            if manifest is not None
            else ()
        ),
        "surfaces": surfaces,
        "contributions": list(surfaces),
        "diagnostics": [
            _serialize_diagnostic(diagnostic)
            for diagnostic in _extension_visibility_diagnostics(
                extension,
                diagnostics=diagnostics,
                manifest_path=manifest_path,
            )
        ],
    }


def _serialize_surface(surface: object) -> dict[str, object]:
    metadata = getattr(surface, "metadata", {})
    source = metadata.get("source") if isinstance(metadata, dict) else None
    return {
        "type": str(getattr(surface, "type", "")),
        "name": str(getattr(surface, "name", "")),
        "active": bool(getattr(surface, "active", True)),
        "priority": int(getattr(surface, "priority", 0)),
        "source": source if isinstance(source, str) else "",
        "sourcePath": _path_text(getattr(surface, "source_path", None)),
        "diagnostics": [
            _serialize_diagnostic(diagnostic)
            for diagnostic in getattr(surface, "diagnostics", ())
            if isinstance(diagnostic, ResourceDiagnostic)
        ],
    }


def _extension_visibility_diagnostics(
    extension: LoadedExtension,
    *,
    diagnostics: list[ResourceDiagnostic],
    manifest_path: Path | None,
) -> list[ResourceDiagnostic]:
    source_paths = {
        path
        for path in (
            extension.source_path,
            extension.entry_path,
            manifest_path,
            *_extension_manifest_candidate_paths(extension),
        )
        if path is not None
    }
    result: list[ResourceDiagnostic] = []
    seen: set[tuple[str, str, str | None]] = set()
    for diagnostic in extension.diagnostics:
        result, seen = _append_extension_diagnostic(result, seen, diagnostic)
    for diagnostic in diagnostics:
        if diagnostic.source_path is None or diagnostic.source_path not in source_paths:
            continue
        result, seen = _append_extension_diagnostic(result, seen, diagnostic)
    return result


def _append_extension_diagnostic(
    result: list[ResourceDiagnostic],
    seen: set[tuple[str, str, str | None]],
    diagnostic: ResourceDiagnostic,
) -> tuple[list[ResourceDiagnostic], set[tuple[str, str, str | None]]]:
    key = (
        diagnostic.code,
        diagnostic.message,
        diagnostic.source_path.as_posix()
        if diagnostic.source_path is not None
        else None,
    )
    if key not in seen:
        seen.add(key)
        result.append(diagnostic)
    return result, seen


def _serialize_diagnostic(diagnostic: ResourceDiagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "sourcePath": diagnostic.source_path.as_posix()
        if diagnostic.source_path is not None
        else None,
        "resourceId": diagnostic.resource_id,
        "resourceType": diagnostic.resource_type,
        "sourceKind": diagnostic.source_kind,
        "metadata": dict(diagnostic.metadata),
    }


def _extension_manifest_path(extension: LoadedExtension) -> Path | None:
    for candidate in _extension_manifest_candidate_paths(extension):
        if candidate.is_file():
            return candidate
    return None


def _extension_manifest_candidate_paths(extension: LoadedExtension) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if extension.source_path.suffix:
        candidates.append(extension.source_path.with_name("loushang-extension.toml"))
    else:
        candidates.append(extension.source_path / "loushang-extension.toml")
    if extension.entry_path is not None:
        candidates.append(extension.entry_path.parent / "loushang-extension.toml")
    return tuple(dict.fromkeys(candidates))


def _path_text(value: object) -> str:
    return value.as_posix() if isinstance(value, Path) else str(value or "")


def _serialize_source_info(source_info: SourceInfo[Path]) -> dict[str, object]:
    return {
        "path": source_info.path.as_posix(),
        "source": source_info.source,
        "scope": source_info.scope,
        "origin": source_info.origin,
        "baseDir": source_info.base_dir.as_posix()
        if source_info.base_dir is not None
        else None,
        "base_dir": source_info.base_dir.as_posix()
        if source_info.base_dir is not None
        else None,
    }
