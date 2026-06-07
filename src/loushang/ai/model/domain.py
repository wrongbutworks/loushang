from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import InitVar, dataclass, field, replace
from typing import Literal, cast

Modality = Literal["text", "image", "video", "audio", "vector"]
ALLOWED_MODALITIES: tuple[Modality, ...] = ("text", "image", "video", "audio", "vector")


@dataclass(frozen=True)
class Auth:
    kind: str = "apiKey"
    api_key_env: str | None = None
    api_key_envs: tuple[str, ...] = ()
    header: str = "Authorization"
    prefix: str = "Bearer "
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Auth | None":
        if not raw:
            return None
        return cls(
            kind=str(raw.get("kind", "apiKey")),
            api_key_env=_as_optional_str(raw.get("apiKeyEnv")),
            api_key_envs=_as_str_tuple(raw.get("apiKeyEnvs")),
            header=str(raw.get("header", "Authorization")),
            prefix=str(raw.get("prefix", "Bearer ")),
            extra_headers=_as_str_dict(raw.get("extraHeaders")),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "apiKeyEnv": self.api_key_env,
            "apiKeyEnvs": list(self.api_key_envs),
            "header": self.header,
            "prefix": self.prefix,
            "extraHeaders": dict(self.extra_headers),
        }


@dataclass(frozen=True)
class Pricing:
    currency: str | None = None
    input: float | int = 0
    output: float | int = 0
    cache_read: float | int = 0
    cache_write: float | int = 0

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Pricing":
        raw = raw or {}
        return cls(
            currency=_as_optional_str(raw.get("currency")),
            input=_as_number(raw.get("input")),
            output=_as_number(raw.get("output")),
            cache_read=_as_number(raw.get("cacheRead")),
            cache_write=_as_number(raw.get("cacheWrite")),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "currency": self.currency,
            "input": self.input,
            "output": self.output,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
        }


@dataclass(frozen=True)
class Capabilities:
    input: tuple[Modality, ...] = ("text",)
    output: tuple[Modality, ...] = ("text",)
    context_window: int | None = None
    max_tokens: int | None = None
    reasoning: bool = False
    stream: bool = False
    tool_use: bool = False
    structured_output: bool = False
    attachment: bool = False
    temperature: bool = False

    @property
    def supports_thinking(self) -> bool:
        return self.reasoning

    @property
    def supports_image_input(self) -> bool:
        return "image" in self.input

    @property
    def supports_image_output(self) -> bool:
        return "image" in self.output

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Capabilities":
        raw = raw or {}
        capabilities_raw = raw.get("capabilities")
        if isinstance(capabilities_raw, Mapping):
            raw = capabilities_raw
        return cls(
            input=_parse_modalities(raw.get("input")),
            output=_parse_modalities(raw.get("output")),
            context_window=_as_optional_int(raw.get("contextWindow")),
            max_tokens=_as_optional_int(raw.get("maxTokens")),
            reasoning=bool(raw.get("reasoning", False)),
            stream=bool(raw.get("stream", False)),
            tool_use=bool(raw.get("toolUse", False)),
            structured_output=bool(raw.get("structuredOutput", False)),
            attachment=bool(raw.get("attachment", False)),
            temperature=bool(raw.get("temperature", False)),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "capabilities": {
                "contextWindow": self.context_window,
                "maxTokens": self.max_tokens,
                "input": list(self.input),
                "output": list(self.output),
                "reasoning": self.reasoning,
                "stream": self.stream,
                "toolUse": self.tool_use,
                "structuredOutput": self.structured_output,
                "attachment": self.attachment,
                "temperature": self.temperature,
            }
        }


@dataclass(frozen=True, init=False)
class Compat(Mapping[str, object]):
    items_by_key: dict[str, object] = field(default_factory=dict)

    def __init__(
        self,
        *,
        items_by_key: Mapping[str, object] | None = None,
        values: Mapping[str, object] | None = None,
    ) -> None:
        if items_by_key is not None and values is not None:
            raise TypeError("Compat accepts either items_by_key or values, not both.")
        source = items_by_key if items_by_key is not None else values
        object.__setattr__(self, "items_by_key", dict(source or {}))

    def __getitem__(self, key: str) -> object:
        return self.items_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.items_by_key)

    def __len__(self) -> int:
        return len(self.items_by_key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.items_by_key.get(key, default)

    def merged(self, other: Mapping[str, object] | None = None) -> "Compat":
        merged = dict(self.items_by_key)
        if other is not None:
            merged.update(dict(other))
        return Compat(items_by_key=merged)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Compat":
        return cls(items_by_key=dict(raw or {}))

    def to_raw(self) -> dict[str, object]:
        return dict(self.items_by_key)


@dataclass(frozen=True)
class Defaults(Mapping[str, object]):
    items_by_key: dict[str, object] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        return self.items_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.items_by_key)

    def __len__(self) -> int:
        return len(self.items_by_key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.items_by_key.get(key, default)

    def merged(self, other: Mapping[str, object] | None = None) -> "Defaults":
        merged = dict(self.items_by_key)
        if other is not None:
            merged.update(dict(other))
        return Defaults(items_by_key=merged)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Defaults":
        return cls(items_by_key=dict(raw or {}))

    def to_raw(self) -> dict[str, object]:
        return dict(self.items_by_key)


@dataclass(frozen=True)
class Model:
    id: str
    _endpoint_key: str = ""
    provider: InitVar[str | None] = None
    endpoint: InitVar[str | None] = None
    api: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    auth: Auth | None = None
    _auth_inherited: bool = False
    name: str | None = None
    family: str | None = None
    alias: str | None = None
    knowledge: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    capabilities: Capabilities = field(default_factory=Capabilities)
    pricing: Pricing = field(default_factory=Pricing)
    compat: Compat = field(default_factory=Compat)
    defaults: Defaults = field(default_factory=Defaults)

    def __post_init__(self, provider: str | None, endpoint: str | None) -> None:
        if self._endpoint_key:
            return
        if provider is None or endpoint is None:
            return
        object.__setattr__(
            self, "_endpoint_key", build_endpoint_key(provider, endpoint)
        )

    @property
    def provider_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[0]

    @property
    def endpoint_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[1]

    @property
    def input(self) -> tuple[Modality, ...]:
        return self.capabilities.input

    @property
    def output(self) -> tuple[Modality, ...]:
        return self.capabilities.output

    @property
    def context_window(self) -> int | None:
        return self.capabilities.context_window

    @property
    def max_tokens(self) -> int | None:
        return self.capabilities.max_tokens

    @property
    def reasoning(self) -> bool:
        return self.capabilities.reasoning

    @property
    def supports_tool_use(self) -> bool:
        return self.capabilities.tool_use

    @property
    def supports_structured_output(self) -> bool:
        return self.capabilities.structured_output

    @property
    def supports_attachment(self) -> bool:
        return self.capabilities.attachment

    @property
    def supports_temperature(self) -> bool:
        return self.capabilities.temperature

    @property
    def supports_stream(self) -> bool:
        return self.capabilities.stream

    @property
    def supports_thinking(self) -> bool:
        return self.capabilities.supports_thinking

    @property
    def supports_image_input(self) -> bool:
        return self.capabilities.supports_image_input

    @property
    def supports_image_output(self) -> bool:
        return self.capabilities.supports_image_output

    def with_endpoint(self, endpoint: "Endpoint") -> "Model":
        inherits_auth = self.auth is None or self._auth_inherited
        auth = endpoint.auth if inherits_auth else self.auth
        return replace(
            self,
            _endpoint_key=endpoint.endpoint_key,
            api=endpoint.api,
            base_url=endpoint.base_url,
            base_url_env=endpoint.base_url_env,
            region=endpoint.region,
            auth=auth,
            _auth_inherited=inherits_auth and auth is not None,
            compat=endpoint.compat.merged(self.compat),
            defaults=endpoint.defaults.merged(self.defaults),
        )

    async def stream(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream

        return await stream(self, context, options=options, registry=registry)

    async def complete(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete

        return await complete(self, context, options=options, registry=registry)

    async def stream_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream_simple

        return await stream_simple(self, context, options=options, registry=registry)

    async def complete_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete_simple

        return await complete_simple(self, context, options=options, registry=registry)

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "displayName": self.name,
            "family": self.family,
            "alias": self.alias,
            "knowledge": self.knowledge,
            "releaseDate": self.release_date,
            "lastUpdated": self.last_updated,
            "pricing": self.pricing.to_raw(),
            "compat": self.compat.to_raw(),
            "defaults": self.defaults.to_raw(),
        }
        raw.update(self.capabilities.to_raw())
        if self.auth is not None and not self._auth_inherited:
            raw["auth"] = self.auth.to_raw()
        return {key: value for key, value in raw.items() if value is not None}


@dataclass(frozen=True)
class Endpoint:
    id: str
    api: str
    _provider_key: str = ""
    provider: InitVar[str | None] = None
    name: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    lane: str | None = None
    docs: str | None = None
    auth: Auth | None = None
    compat: Compat = field(default_factory=Compat)
    defaults: Defaults = field(default_factory=Defaults)
    models: dict[str, Model] = field(default_factory=dict)

    def __post_init__(self, provider: str | None) -> None:
        if self._provider_key:
            return
        if provider is None:
            return
        object.__setattr__(self, "_provider_key", provider)

    @property
    def provider_id(self) -> str:
        return self._provider_key

    @property
    def endpoint_key(self) -> str:
        return build_endpoint_key(self.provider_id, self.id)

    def get_model(self, model_id: str) -> Model | None:
        return self.models.get(model_id)

    def list_models(self) -> list[Model]:
        return sorted(self.models.values(), key=lambda item: item.id)

    def bind_model(self, model: Model) -> Model:
        return model.with_endpoint(self)

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "api": self.api,
            "compat": self.compat.to_raw(),
            "defaults": self.defaults.to_raw(),
            "models": {
                model_id: model.to_raw() for model_id, model in self.models.items()
            },
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.base_url is not None:
            raw["baseUrl"] = self.base_url
        if self.base_url_env is not None:
            raw["baseUrlEnv"] = self.base_url_env
        if self.region is not None:
            raw["region"] = self.region
        if self.lane is not None:
            raw["lane"] = self.lane
        if self.docs is not None:
            raw["docs"] = self.docs
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        return raw


@dataclass(frozen=True)
class Provider:
    id: str
    name: str | None = None
    website: str | None = None
    auth: Auth | None = None
    endpoints: dict[str, Endpoint] = field(default_factory=dict)

    def get_endpoint(self, endpoint_id: str) -> Endpoint | None:
        return self.endpoints.get(endpoint_id)

    def list_endpoints(self) -> list[Endpoint]:
        return sorted(self.endpoints.values(), key=lambda item: item.id)

    def get_model(self, endpoint_id: str, model_id: str) -> Model | None:
        endpoint = self.get_endpoint(endpoint_id)
        if endpoint is None:
            return None
        return endpoint.get_model(model_id)

    def list_models(self) -> list[Model]:
        models: list[Model] = []
        for endpoint in self.list_endpoints():
            models.extend(endpoint.list_models())
        return models

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "endpoints": {
                endpoint_id: endpoint.to_raw()
                for endpoint_id, endpoint in self.endpoints.items()
            }
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.website is not None:
            raw["website"] = self.website
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        return raw


def _parse_modalities(raw: object) -> tuple[Modality, ...]:
    if isinstance(raw, str):
        values = tuple(
            value.strip()
            for value in raw.split(",")
            if value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    if isinstance(raw, (list, tuple)):
        values = tuple(
            value.strip()
            for value in raw
            if isinstance(value, str) and value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    return ("text",)


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_number(value: object) -> float | int:
    return value if isinstance(value, int | float) else 0


def _as_str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, entry in value.items():
        if isinstance(key, str) and isinstance(entry, str):
            result[key] = entry
    return result


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _coerce_modalities(values: tuple[str, ...]) -> tuple[Modality, ...]:
    return tuple(
        cast(Modality, value) for value in values if value in ALLOWED_MODALITIES
    ) or ("text",)


def build_endpoint_key(provider_id: str, endpoint_id: str) -> str:
    return f"{provider_id}:{endpoint_id}"


def parse_endpoint_key(endpoint_key: str) -> tuple[str, str]:
    if ":" not in endpoint_key:
        return "", endpoint_key
    provider_id, endpoint_id = endpoint_key.split(":", 1)
    return provider_id, endpoint_id
