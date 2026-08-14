from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from inspect import Parameter, signature
from pathlib import Path
from types import NoneType
from typing import (
    Annotated,
    Any,
    NotRequired,
    Protocol,
    Required,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
    runtime_checkable,
)
from uuid import uuid4

from loushang.agent.types import AgentTool, AgentToolResult, ToolExecutionMode
from loushang.ai.types import ToolCall
from loushang.harness.presentation import ToolRenderContext, ToolRenderResultOptions
from loushang.harness.runtime.registration import (
    RegistrationDisposalResult,
    RegistrationIdentity,
    RegistrationLease,
    RegistrationOwner,
)
from loushang.harness.tools.execution import (
    AuthorizedExecution,
    DirectExecution,
    ExecutionBinding,
    ToolCallContext,
    ToolExecutionHost,
)

_TOOL_SPEC_ATTR = "__loushang_tool_spec__"

ToolRenderOutput = str | Mapping[str, Any] | None
ToolRenderCall = Callable[[object, Mapping[str, str], ToolRenderContext], ToolRenderOutput]
ToolRenderResult = Callable[
    [AgentToolResult[Any], ToolRenderResultOptions, Mapping[str, str], ToolRenderContext],
    ToolRenderOutput,
]


class ToolContextProvider(Protocol):
    """Build Product-neutral context for one materialized tool call."""

    def __call__(self, *, tool_call_id: str) -> object: ...


_SCALAR_TYPES: dict[type[object], str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _as_tuple_of_strings(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must be a sequence of strings")
        normalized.append(item)
    return tuple(normalized)


def _validate_execution_mode(value: ToolExecutionMode, field_name: str) -> ToolExecutionMode:
    if value not in {"sequential", "parallel"}:
        raise ValueError(f"{field_name} must be 'sequential' or 'parallel'")
    return value


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    description: str
    parameters: dict[str, Any]
    execution: ExecutionBinding
    prepare_arguments: Callable[[object], dict[str, Any]] | None = None
    execution_mode: ToolExecutionMode = "parallel"
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] = field(default_factory=tuple)
    render_call: ToolRenderCall | None = None
    render_result: ToolRenderResult | None = None
    provider_parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "prompt_guidelines",
            _as_tuple_of_strings(self.prompt_guidelines, "prompt_guidelines"),
        )
        object.__setattr__(
            self,
            "execution_mode",
            _validate_execution_mode(self.execution_mode, "execution_mode"),
        )
        if self.render_call is not None and not callable(self.render_call):
            raise TypeError("render_call must be callable")
        if self.render_result is not None and not callable(self.render_result):
            raise TypeError("render_result must be callable")
        if self.provider_parameters is not None and not isinstance(self.provider_parameters, dict):
            raise TypeError("provider_parameters must be a dict")
        if not isinstance(self.execution, DirectExecution | AuthorizedExecution):
            raise TypeError(
                "execution must be DirectExecution or AuthorizedExecution"
            )

    @property
    def renderCall(self) -> ToolRenderCall | None:
        return self.render_call

    @property
    def renderResult(self) -> ToolRenderResult | None:
        return self.render_result


def project_tool_definition(
    definition: ToolDefinition,
    source_info: object | None = None,
    *,
    builtin_names: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Project a tool definition into the neutral session/tool wire shape."""
    return {
        "name": definition.name,
        "description": definition.description,
        "parameters": definition.parameters,
        "sourceInfo": _project_tool_source_info(source_info, definition.name, builtin_names),
    }


def _project_tool_source_info(
    source_info: object | None,
    name: str,
    builtin_names: frozenset[str],
) -> dict[str, object]:
    if source_info is None:
        source = "builtin" if name in builtin_names else "sdk"
        return {
            "path": f"<{source}:{name}>",
            "source": source,
            "scope": "temporary",
            "origin": "top-level",
            "baseDir": None,
        }
    base_dir = getattr(source_info, "base_dir", None)
    return {
        "path": _path_text(getattr(source_info, "path", "")),
        "source": getattr(source_info, "source", "filesystem"),
        "scope": getattr(source_info, "scope", "project"),
        "origin": getattr(source_info, "origin", "top-level"),
        "baseDir": _path_text(base_dir) if base_dir is not None else None,
    }


def _path_text(value: object) -> str:
    return value.as_posix() if isinstance(value, Path) else str(value)


@dataclass(frozen=True)
class DecoratedToolSpec:
    fn: Callable[..., object]
    name: str | None = None
    description: str | None = None
    label: str | None = None
    prompt_snippet: str | None = None
    prompt_guidelines: tuple[str, ...] | list[str] = ()
    schema_overrides: dict[str, object] | None = None

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self.fn(*args, **kwargs)


@runtime_checkable
class DecoratedTool(Protocol):
    __loushang_tool_spec__: DecoratedToolSpec


def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    label: str | None = None,
    prompt_snippet: str | None = None,
    prompt_guidelines: tuple[str, ...] | list[str] = (),
    schema_overrides: dict[str, object] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = DecoratedToolSpec(
            fn=fn,
            name=name,
            description=description,
            label=label,
            prompt_snippet=prompt_snippet,
            prompt_guidelines=prompt_guidelines,
            schema_overrides=schema_overrides,
        )
        setattr(fn, _TOOL_SPEC_ATTR, spec)
        return fn

    return decorator


def _base_object_schema() -> tuple[
    dict[str, object],
    dict[str, object],
    list[str],
]:
    properties: dict[str, object] = {}
    required: list[str] = []
    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return schema, properties, required


def _unwrap_annotation(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap_annotation(get_args(annotation)[0])
    if origin in (Required, NotRequired):
        return _unwrap_annotation(get_args(annotation)[0])
    if origin is None and annotation is not None:
        return annotation
    return annotation


def _merge_schema(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = dict(base)
    for key, value in overrides.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_schema(existing, value)
        else:
            merged[key] = value
    return merged


def apply_schema_overrides(schema: dict[str, object], overrides: dict[str, object] | None) -> dict[str, object]:
    if overrides in (None, {}):
        return schema
    if not isinstance(overrides, dict):
        raise TypeError("schema overrides must be a mapping")
    return _merge_schema(schema, overrides)


def infer_schema_from_signature(
    fn: Callable[..., object],
    *,
    exclude_names: set[str] | frozenset[str] | None = None,
) -> dict[str, object]:
    sig = signature(fn)
    hints = get_type_hints(fn, include_extras=True)
    schema, properties, required = _base_object_schema()
    excluded = set(exclude_names or ())

    for param in sig.parameters.values():
        if param.name in excluded:
            continue
        if param.kind == Parameter.POSITIONAL_ONLY:
            raise TypeError("positional-only parameters are not supported for schema inference")
        if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            raise TypeError("variadic parameters are not supported for schema inference")
        if param.name not in hints:
            raise TypeError(f"parameter {param.name!r} must be annotated")
        annotation = hints[param.name]
        properties[param.name] = infer_schema_from_type(annotation)
        if param.default is Parameter.empty:
            required.append(param.name)

    return schema


def infer_schema_from_type(annotation: object) -> dict[str, object]:
    annotation = _unwrap_annotation(annotation)

    if annotation is Any:
        raise TypeError("cannot infer schema from typing.Any")

    origin = get_origin(annotation)
    if origin is None:
        if annotation in _SCALAR_TYPES:
            return {"type": _SCALAR_TYPES[annotation]}

        if isinstance(annotation, type):
            if is_typeddict(annotation):
                return _infer_schema_from_typeddict(annotation)
            if is_dataclass(annotation):
                return _infer_schema_from_dataclass(annotation)
            if _is_pydantic_model(annotation):
                return _infer_schema_from_pydantic_model(annotation)

        raise TypeError(f"unsupported schema annotation: {annotation!r}")

    if origin is list:
        (item_annotation,) = get_args(annotation) or (Any,)
        return {"type": "array", "items": infer_schema_from_type(item_annotation)}

    if origin is tuple:
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": infer_schema_from_type(args[0])}
        raise TypeError("fixed-length tuples are not supported for schema inference")

    union_args = get_args(annotation)
    if union_args and any(arg is NoneType for arg in union_args):
        non_none = [arg for arg in union_args if arg is not NoneType]
        if len(non_none) != 1:
            raise TypeError("optional unions must contain exactly one non-None type")
        return {
            "anyOf": [
                infer_schema_from_type(non_none[0]),
                {"type": "null"},
            ]
        }

    if origin is NoneType or annotation is NoneType:
        raise TypeError("bare None is not a supported schema annotation")

    raise TypeError(f"unsupported schema annotation: {annotation!r}")


def _infer_schema_from_dataclass(cls: type[object]) -> dict[str, object]:
    type_hints = get_type_hints(cls, include_extras=True)
    schema, properties, required = _base_object_schema()

    for dataclass_field in fields(cast(Any, cls)):
        annotation = type_hints.get(dataclass_field.name, dataclass_field.type)
        properties[dataclass_field.name] = infer_schema_from_type(annotation)
        if dataclass_field.default is MISSING and dataclass_field.default_factory is MISSING:
            required.append(dataclass_field.name)

    return schema


def _infer_schema_from_typeddict(cls: type[object]) -> dict[str, object]:
    type_hints = get_type_hints(cls, include_extras=True)
    schema, properties, required = _base_object_schema()

    required_keys = cast(
        frozenset[str],
        getattr(cls, "__required_keys__", frozenset()),
    )
    optional_keys = cast(
        frozenset[str],
        getattr(cls, "__optional_keys__", frozenset()),
    )

    for name, annotation in type_hints.items():
        properties[name] = infer_schema_from_type(annotation)
        if _typeddict_key_is_required(
            cls,
            name,
            annotation,
            required_keys=required_keys,
            optional_keys=optional_keys,
        ):
            required.append(name)

    return schema


def _typeddict_key_is_required(
    cls: type[object],
    name: str,
    annotation: object,
    *,
    required_keys: frozenset[str],
    optional_keys: frozenset[str],
) -> bool:
    origin = get_origin(annotation)
    if origin is Required:
        return True
    if origin is NotRequired:
        return False
    if name in optional_keys:
        return False
    if name in required_keys:
        return True
    return bool(getattr(cls, "__total__", True))


def _is_pydantic_model(annotation: type[object]) -> bool:
    try:
        from pydantic import BaseModel
    except ImportError:
        return False
    return issubclass(annotation, BaseModel)


def _infer_schema_from_pydantic_model(annotation: type[object]) -> dict[str, object]:
    if hasattr(annotation, "model_json_schema"):
        schema = annotation.model_json_schema()
    elif hasattr(annotation, "schema"):
        schema = annotation.schema()
    else:
        raise TypeError("pydantic model does not expose a schema method")

    if not isinstance(schema, dict):
        raise TypeError("pydantic model schema must be a mapping")
    _raise_on_unresolved_pydantic_refs(schema)
    return schema


def _raise_on_unresolved_pydantic_refs(value: object, *, in_properties_map: bool = False) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not in_properties_map and key in {"$ref", "$defs", "definitions"}:
                raise ValueError("unresolved pydantic refs are not yet supported")
            if key == "properties":
                _raise_on_unresolved_pydantic_refs(item, in_properties_map=True)
            else:
                _raise_on_unresolved_pydantic_refs(item)
    elif isinstance(value, list):
        for item in value:
            _raise_on_unresolved_pydantic_refs(item)


@dataclass
class WrappedToolDefinition:
    definition: ToolDefinition
    execution_host: ToolExecutionHost
    context_provider: ToolContextProvider | None = None

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def label(self) -> str:
        return self.definition.label

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self.definition.provider_parameters or self.definition.parameters

    @property
    def prepare_arguments(self):
        return self.definition.prepare_arguments

    @property
    def execution_mode(self) -> ToolExecutionMode:
        return self.definition.execution_mode

    @property
    def render_call(self) -> ToolRenderCall | None:
        return self.definition.render_call

    @property
    def renderCall(self) -> ToolRenderCall | None:
        return self.definition.renderCall

    @property
    def render_result(self) -> ToolRenderResult | None:
        return self.definition.render_result

    @property
    def renderResult(self) -> ToolRenderResult | None:
        return self.definition.renderResult

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        signal: object | None = None,
        on_update: object | None = None,
    ) -> AgentToolResult[Any]:
        context = _build_tool_call_context(
            tool_call_id=tool_call_id,
            signal=signal,
            on_update=on_update,
            context_provider=self.context_provider,
        )
        return await self.execution_host.dispatch(
            self.definition,
            ToolCall(
                type="toolCall",
                id=tool_call_id,
                name=self.definition.name,
                arguments=dict(params),
            ),
            context,
        )


def _build_tool_call_context(
    *,
    tool_call_id: str,
    signal: object | None,
    on_update: object | None,
    context_provider: ToolContextProvider | None,
) -> ToolCallContext:
    provided = (
        context_provider(tool_call_id=tool_call_id)
        if context_provider is not None
        else None
    )
    if isinstance(provided, ToolCallContext):
        return ToolCallContext(
            tool_call_id=tool_call_id,
            cwd=provided.cwd,
            diagnostics=provided.diagnostics,
            signal=signal,
            model=provided.model,
            event_sink=provided.event_sink,
            exec_service=provided.exec_service,
            on_update=on_update if callable(on_update) else None,
            operation_bindings=provided.operation_bindings,
        )
    return ToolCallContext(
        tool_call_id=tool_call_id,
        cwd=getattr(provided, "cwd", None),
        diagnostics=getattr(provided, "diagnostics", None),
        signal=signal,
        model=getattr(provided, "model", None),
        event_sink=getattr(provided, "event_sink", None),
        exec_service=getattr(provided, "exec_service", None),
        on_update=on_update if callable(on_update) else None,
    )


def wrap_tool_definition(
    definition: ToolDefinition,
    *,
    execution_host: ToolExecutionHost | None = None,
    context_provider: ToolContextProvider | None = None,
) -> AgentTool[Any]:
    return WrappedToolDefinition(
        definition=definition,
        execution_host=execution_host or ToolExecutionHost(),
        context_provider=context_provider,
    )


def wrap_tool_definitions(
    definitions: list[ToolDefinition],
    *,
    execution_host: ToolExecutionHost | None = None,
    context_provider: ToolContextProvider | None = None,
) -> list[AgentTool[Any]]:
    host = execution_host or ToolExecutionHost()
    return [
        wrap_tool_definition(
            definition,
            execution_host=host,
            context_provider=context_provider,
        )
        for definition in definitions
    ]


@dataclass(frozen=True)
class _RegisteredTool:
    owner: RegistrationOwner
    identity: RegistrationIdentity
    definition: ToolDefinition
    enabled: bool = True
    source_info: object | None = None


class ToolRegistry:
    def __init__(self, *, execution_host: ToolExecutionHost | None = None) -> None:
        self._tools: dict[str, list[_RegisteredTool]] = {}
        self._order: list[str] = []
        self._legacy_registration_ids: dict[str, str] = {}
        self._legacy_owner = RegistrationOwner(
            owner_kind="runtime",
            owner_id="tool-registry-compatibility",
            runtime_id=uuid4().hex,
            generation=0,
        )
        self._execution_host = execution_host

    def bind_execution_host(self, host: ToolExecutionHost) -> None:
        self._execution_host = host

    def register_tool(
        self,
        tool: ToolDefinition,
        *,
        enabled: bool = True,
        source_info: object | None = None,
    ) -> ToolDefinition:
        """Compatibility facade; live owners should use :meth:`bind_tool`."""

        definition = self._require_definition(tool, operation="register_tool")
        layers = self._tools.get(definition.name)
        if layers is None:
            layers = []
            self._tools[definition.name] = layers
            self._order.append(definition.name)
        previous_id = self._legacy_registration_ids.get(definition.name)
        identity = RegistrationIdentity.create(
            surface="tool",
            public_key=definition.name,
        )
        registered = _RegisteredTool(
            owner=self._legacy_owner,
            identity=identity,
            definition=definition,
            enabled=enabled,
            source_info=source_info,
        )
        previous_index = next(
            (
                index
                for index, existing in enumerate(layers)
                if existing.identity.registration_id == previous_id
            ),
            None,
        )
        if previous_index is None:
            layers.append(registered)
        else:
            layers[previous_index] = registered
        self._legacy_registration_ids[definition.name] = identity.registration_id
        return tool

    def bind_tool(
        self,
        tool: ToolDefinition,
        *,
        owner: RegistrationOwner,
        enabled: bool = True,
        source_info: object | None = None,
    ) -> RegistrationLease:
        """Bind one owner-scoped Tool layer and return its exact disposer."""

        definition = self._require_definition(tool, operation="bind_tool")
        if not isinstance(owner, RegistrationOwner):
            raise TypeError("ToolRegistry.bind_tool owner must be a RegistrationOwner")
        identity = RegistrationIdentity.create(
            surface="tool",
            public_key=definition.name,
        )
        layers = self._tools.get(definition.name)
        if layers is None:
            layers = []
            self._tools[definition.name] = layers
            self._order.append(definition.name)
        layers.append(
            _RegisteredTool(
                owner=owner,
                identity=identity,
                definition=definition,
                enabled=enabled,
                source_info=source_info,
            )
        )
        return RegistrationLease(
            owner=owner,
            identity=identity,
            dispose=lambda: self._remove_bound_tool(
                owner=owner,
                identity=identity,
            ),
        )

    def get_tool(self, name: str) -> AgentTool[Any]:
        return self.materialize_tool(name)

    def get_definition(self, name: str) -> ToolDefinition:
        return self._effective_tool(name).definition

    def get_source_info(self, name: str) -> object | None:
        return self._effective_tool(name).source_info

    def list_tools(self) -> list[AgentTool[Any]]:
        return self.materialize_definitions(self.list_definitions())

    def list_enabled_tools(self) -> list[AgentTool[Any]]:
        return self.materialize_definitions(self.list_enabled_definitions())

    def list_definitions(self) -> list[ToolDefinition]:
        return [self._effective_tool(name).definition for name in self._order]

    def list_enabled_definitions(self) -> list[ToolDefinition]:
        return [
            registered.definition
            for name in self._order
            if (registered := self._effective_tool(name)).enabled
        ]

    def enable_tool(self, name: str) -> None:
        registered = self._effective_tool(name)
        self._tools[name][-1] = _RegisteredTool(
            owner=registered.owner,
            identity=registered.identity,
            definition=registered.definition,
            enabled=True,
            source_info=registered.source_info,
        )

    def disable_tool(self, name: str) -> None:
        registered = self._effective_tool(name)
        self._tools[name][-1] = _RegisteredTool(
            owner=registered.owner,
            identity=registered.identity,
            definition=registered.definition,
            enabled=False,
            source_info=registered.source_info,
        )

    def materialize_tool(self, name: str) -> AgentTool[Any]:
        return wrap_tool_definition(
            self.get_definition(name),
            execution_host=self._execution_host,
        )

    def materialize_definitions(
        self,
        definitions: list[ToolDefinition],
        *,
        context_provider: ToolContextProvider | None = None,
    ) -> list[AgentTool[Any]]:
        return wrap_tool_definitions(
            definitions,
            execution_host=self._execution_host,
            context_provider=context_provider,
        )

    @staticmethod
    def _require_definition(
        tool: ToolDefinition,
        *,
        operation: str,
    ) -> ToolDefinition:
        if not isinstance(tool, ToolDefinition):
            raise TypeError(
                f"ToolRegistry.{operation} expects an explicitly bound ToolDefinition"
            )
        return tool

    def _effective_tool(self, name: str) -> _RegisteredTool:
        return self._tools[name][-1]

    def _remove_bound_tool(
        self,
        *,
        owner: RegistrationOwner,
        identity: RegistrationIdentity,
    ) -> RegistrationDisposalResult:
        name = identity.public_key
        if name is None:
            return RegistrationDisposalResult(
                state="failed_terminal",
                diagnostic_code="tool_registration_public_key_missing",
            )
        layers = self._tools.get(name)
        if layers is None:
            return RegistrationDisposalResult(state="already_removed")
        for index, registered in enumerate(layers):
            if registered.identity.registration_id != identity.registration_id:
                continue
            if registered.owner != owner:
                return RegistrationDisposalResult(
                    state="failed_terminal",
                    diagnostic_code="tool_registration_owner_mismatch",
                )
            layers.pop(index)
            if not layers:
                del self._tools[name]
                self._order.remove(name)
            return RegistrationDisposalResult(state="removed")
        return RegistrationDisposalResult(state="already_removed")
