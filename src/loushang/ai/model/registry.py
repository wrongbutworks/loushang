from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from loushang.ai.model.domain import (
    Auth,
    Defaults,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    Provider,
    merge_adapter_config,
)

# 全局
_default_model_registry: ModelRegistry | None = None


def get_default_model_registry() -> "ModelRegistry":
    global _default_model_registry
    if _default_model_registry is None:
        from pathlib import Path

        from loushang.ai.model.loader import load_layered_model_registry

        _default_model_registry = load_layered_model_registry(
            user_dir=Path.home() / ".loushang" / "models",
        )
    return _default_model_registry


def clear_default_model_registry() -> None:
    global _default_model_registry
    _default_model_registry = None


def reload_default_model_registry() -> "ModelRegistry":
    global _default_model_registry
    from pathlib import Path

    from loushang.ai.model.loader import load_layered_model_registry

    _default_model_registry = load_layered_model_registry(
        user_dir=Path.home() / ".loushang" / "models",
    )
    return _default_model_registry


def resolve_model_endpoint(
    model: Model,
    *,
    registry: "ModelRegistry | None" = None,
) -> Endpoint | None:
    if registry is None and has_bound_endpoint_context(model):
        return _endpoint_snapshot_from_model(model)
    resolved_registry = (
        registry if registry is not None else get_default_model_registry()
    )
    return resolved_registry.get_endpoint(model.provider_id, model.endpoint_id)


def has_bound_endpoint_context(model: Model) -> bool:
    model_api = getattr(model, "api", None)
    if not isinstance(model_api, str) or not model_api:
        return False
    if (
        getattr(model, "base_url", None)
        or getattr(model, "base_url_env", None)
        or getattr(model, "region", None)
        or getattr(model, "lane", None)
        or getattr(model, "preferred_endpoint", False)
        or getattr(model, "auth", None) is not None
    ):
        return True
    transport = getattr(model, "transport", None)
    if isinstance(transport, EndpointTransport) and transport.to_raw():
        return True
    routing = getattr(model, "routing", None)
    if isinstance(routing, EndpointRouting) and routing.to_raw():
        return True
    return False


def _endpoint_snapshot_from_model(model: Model) -> Endpoint:
    defaults = getattr(model, "defaults", Defaults())
    if not isinstance(defaults, Defaults):
        defaults = Defaults.from_raw(defaults)
    return Endpoint(
        id=model.endpoint_id,
        provider=model.provider_id,
        api=getattr(model, "api", None) or model.endpoint_id,
        base_url=getattr(model, "base_url", None),
        base_url_env=getattr(model, "base_url_env", None),
        region=getattr(model, "region", None),
        lane=getattr(model, "lane", None),
        preferred=getattr(model, "preferred_endpoint", False),
        auth=getattr(model, "auth", None),
        adapter=getattr(model, "adapter", None),
        defaults=defaults,
        transport=getattr(model, "transport", EndpointTransport()),
        routing=getattr(model, "routing", EndpointRouting()),
        models={model.id: model},
    )


def _normalize_providers(providers: dict[str, Provider]) -> dict[str, Provider]:
    return {
        provider_id: _normalize_provider(provider_id, provider)
        for provider_id, provider in providers.items()
    }


def _normalize_provider(provider_id: str, provider: Provider) -> Provider:
    provider_auth = getattr(provider, "auth", None)
    endpoints = {
        endpoint_id: _normalize_endpoint(
            provider_id,
            endpoint,
            provider_auth=provider_auth,
        )
        for endpoint_id, endpoint in provider.endpoints.items()
    }
    return replace(provider, id=provider_id, endpoints=endpoints)


def _normalize_endpoint(
    provider_id: str,
    endpoint: Endpoint,
    *,
    provider_auth: Auth | None = None,
) -> Endpoint:
    normalized_endpoint = replace(
        endpoint,
        _provider_key=provider_id,
    )
    if not normalized_endpoint.models:
        return normalized_endpoint
    return replace(
        normalized_endpoint,
        models={
            model_id: _model_with_effective_context(
                model,
                normalized_endpoint,
                provider_auth=provider_auth,
            )
            for model_id, model in normalized_endpoint.models.items()
        },
    )


def _model_with_effective_context(
    model: Model,
    endpoint: Endpoint,
    *,
    provider_auth: Auth | None = None,
) -> Model:
    transport = EndpointTransport.from_raw(
        _deep_merge_raw_mapping(endpoint.transport.to_raw(), model.transport.to_raw())
    )
    routing = EndpointRouting.from_raw(
        _deep_merge_raw_mapping(endpoint.routing.to_raw(), model.routing.to_raw())
    )
    adapter = merge_adapter_config(endpoint.adapter, model.adapter)
    return replace(
        model,
        _endpoint_key=endpoint.endpoint_key,
        api=endpoint.api,
        base_url=endpoint.base_url,
        base_url_env=endpoint.base_url_env,
        region=endpoint.region,
        lane=endpoint.lane,
        preferred_endpoint=endpoint.preferred,
        auth=model.auth if model.auth is not None else endpoint.auth or provider_auth,
        adapter=adapter,
        defaults=endpoint.defaults.merged(model.defaults),
        transport=transport,
        routing=routing,
    )


def _deep_merge_raw_mapping(
    base: Mapping[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge_raw_mapping(current, value)
            continue
        merged[key] = value
    return merged


def _infer_endpoint_auth_explicit(
    providers: dict[str, Provider],
) -> set[tuple[str, str]]:
    explicit: set[tuple[str, str]] = set()
    for provider_id, provider in providers.items():
        known = getattr(provider, "_auth_scope_known", False)
        explicit_endpoint_ids: frozenset[str] = getattr(
            provider,
            "_explicit_endpoint_auth",
            frozenset(),
        )
        for endpoint_id, endpoint in provider.endpoints.items():
            if known:
                if endpoint_id in explicit_endpoint_ids:
                    explicit.add((provider_id, endpoint_id))
                continue
            if endpoint.auth is not None:
                explicit.add((provider_id, endpoint_id))
    return explicit


def _infer_model_auth_explicit(
    providers: dict[str, Provider],
) -> set[tuple[str, str, str]]:
    explicit: set[tuple[str, str, str]] = set()
    for provider_id, provider in providers.items():
        known = getattr(provider, "_auth_scope_known", False)
        explicit_model_refs: frozenset[tuple[str, str]] = getattr(
            provider,
            "_explicit_model_auth",
            frozenset(),
        )
        for endpoint_id, endpoint in provider.endpoints.items():
            for model_id, model in endpoint.models.items():
                if known:
                    if (endpoint_id, model_id) in explicit_model_refs:
                        explicit.add((provider_id, endpoint_id, model_id))
                    continue
                if model.auth is not None:
                    explicit.add((provider_id, endpoint_id, model_id))
    return explicit


def _attach_auth_scope_metadata(
    providers: dict[str, Provider],
    *,
    endpoint_auth_explicit: set[tuple[str, str]],
    model_auth_explicit: set[tuple[str, str, str]],
) -> dict[str, Provider]:
    return {
        provider_id: replace(
            provider,
            _auth_scope_known=True,
            _explicit_endpoint_auth=frozenset(
                endpoint_id
                for explicit_provider_id, endpoint_id in endpoint_auth_explicit
                if explicit_provider_id == provider_id
            ),
            _explicit_model_auth=frozenset(
                (endpoint_id, model_id)
                for explicit_provider_id, endpoint_id, model_id in model_auth_explicit
                if explicit_provider_id == provider_id
            ),
        )
        for provider_id, provider in providers.items()
    }


def resolve_model_api(
    model: Model,
    *,
    registry: "ModelRegistry | None" = None,
) -> str:
    model_api = getattr(model, "api", None)
    if isinstance(model_api, str) and model_api:
        return model_api
    endpoint = resolve_model_endpoint(model, registry=registry)
    if endpoint is None:
        raise ValueError(
            f"Endpoint not found for model: {model.provider_id}:{model.endpoint_id}:{model.id}"
        )
    return endpoint.api


def format_model_ref(model: Model) -> str:
    return f"{model.provider_id}:{model.endpoint_id}:{model.id}"


def _parse_explicit_model_ref(ref: str) -> tuple[str, str, str] | None:
    if ref.count(":") < 2:
        return None
    provider, rest = ref.split(":", 1)
    endpoint, model_id = rest.rsplit(":", 1)
    if not provider or not endpoint or not model_id:
        return None
    return provider, endpoint, model_id


class AmbiguousModelReference(ValueError):
    def __init__(self, ref: str, candidates: list[Model]) -> None:
        self.ref = ref
        self.candidates = tuple(format_model_ref(model) for model in candidates)
        message = f"Ambiguous model reference {ref!r}; use one of: " + ", ".join(
            self.candidates
        )
        super().__init__(message)


class AmbiguousPreferredModelReference(ValueError):
    def __init__(self, ref: str, candidates: list[Model]) -> None:
        self.ref = ref
        self.candidates = tuple(format_model_ref(model) for model in candidates)
        message = (
            f"Ambiguous preferred endpoint for model reference {ref!r}; "
            "catalog marks multiple preferred endpoints: " + ", ".join(self.candidates)
        )
        super().__init__(message)


def resolve_model_ref(
    registry: "ModelRegistry",
    ref: str,
    *,
    provider: str | None = None,
    endpoint: str | None = None,
    api: str | None = None,
) -> Model:
    if explicit_ref := _parse_explicit_model_ref(ref):
        p, e, mid = explicit_ref
        return registry.get_model(p, e, mid)
    if "/" in ref and provider is None and endpoint is None:
        p, mid = ref.split("/", 1)
        if p and mid:
            return _resolve_provider_model_ref(registry, p, mid)
    if provider and endpoint:
        return registry.get_model(provider, endpoint, ref)
    if provider:
        return _resolve_provider_model_ref(registry, provider, ref)
    if api:
        candidates = [
            model
            for model in registry.list_models(model_id=ref)
            if resolve_model_api(model, registry=registry) == api
        ]
        return _resolve_candidates(registry, ref, candidates)
    return registry.get_model(ref)


def _resolve_provider_model_ref(
    registry: "ModelRegistry",
    provider: str,
    model_id: str,
) -> Model:
    candidates = registry.list_models(provider=provider, model_id=model_id)
    return _resolve_candidates(registry, f"{provider}/{model_id}", candidates)


def _resolve_candidates(
    registry: "ModelRegistry",
    ref: str,
    candidates: list[Model],
) -> Model:
    if not candidates:
        raise KeyError(ref)
    if len(candidates) == 1:
        return candidates[0]
    preferred = [
        model
        for model in candidates
        if (endpoint := registry.get_endpoint(model.provider_id, model.endpoint_id))
        is not None
        and endpoint.preferred
    ]
    if len(preferred) == 1:
        return preferred[0]
    if len(preferred) > 1:
        raise AmbiguousPreferredModelReference(ref, preferred)
    raise AmbiguousModelReference(ref, candidates)


class ModelRegistry:
    def __init__(
        self,
        providers: dict[str, Provider] | None = None,
        *,
        endpoint_auth_explicit: set[tuple[str, str]] | None = None,
        model_auth_explicit: set[tuple[str, str, str]] | None = None,
    ) -> None:
        raw_providers = dict(providers or {})
        resolved_endpoint_auth_explicit = (
            set(endpoint_auth_explicit)
            if endpoint_auth_explicit is not None
            else _infer_endpoint_auth_explicit(raw_providers)
        )
        resolved_model_auth_explicit = (
            set(model_auth_explicit)
            if model_auth_explicit is not None
            else _infer_model_auth_explicit(raw_providers)
        )
        self._providers = _attach_auth_scope_metadata(
            _normalize_providers(raw_providers),
            endpoint_auth_explicit=resolved_endpoint_auth_explicit,
            model_auth_explicit=resolved_model_auth_explicit,
        )
        self._endpoints: dict[tuple[str, str], Endpoint] = {}
        self._models: dict[tuple[str, str, str], Model] = {}
        self._endpoint_auth_explicit = resolved_endpoint_auth_explicit
        self._model_auth_explicit = resolved_model_auth_explicit
        self._rebuild_index()

    @property
    def providers(self) -> dict[str, Provider]:
        return dict(self._providers)

    @classmethod
    def from_providers(
        cls,
        providers: dict[str, Provider],
        *,
        endpoint_auth_explicit: set[tuple[str, str]] | None = None,
        model_auth_explicit: set[tuple[str, str, str]] | None = None,
    ) -> "ModelRegistry":
        return cls(
            providers=providers,
            endpoint_auth_explicit=endpoint_auth_explicit,
            model_auth_explicit=model_auth_explicit,
        )

    def replace_providers(self, providers: dict[str, Provider]) -> None:
        self._replace_providers(providers)

    def _replace_providers(
        self,
        providers: dict[str, Provider],
        *,
        endpoint_auth_explicit: set[tuple[str, str]] | None = None,
        model_auth_explicit: set[tuple[str, str, str]] | None = None,
    ) -> None:
        raw_providers = dict(providers)
        self._endpoint_auth_explicit = (
            set(endpoint_auth_explicit)
            if endpoint_auth_explicit is not None
            else _infer_endpoint_auth_explicit(raw_providers)
        )
        self._model_auth_explicit = (
            set(model_auth_explicit)
            if model_auth_explicit is not None
            else _infer_model_auth_explicit(raw_providers)
        )
        self._providers = _attach_auth_scope_metadata(
            _normalize_providers(raw_providers),
            endpoint_auth_explicit=self._endpoint_auth_explicit,
            model_auth_explicit=self._model_auth_explicit,
        )
        self._rebuild_index()

    def register_provider(self, provider: Provider) -> None:
        providers = dict(self._providers)
        providers[provider.id] = provider
        self.replace_providers(providers)

    def unregister_provider(self, provider_id: str) -> None:
        providers = dict(self._providers)
        providers.pop(provider_id, None)
        self.replace_providers(providers)

    def register_endpoint(self, provider_id: str, endpoint: Endpoint) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            provider = Provider(id=provider_id)

        endpoints = dict(provider.endpoints)
        endpoints[endpoint.id] = endpoint
        providers = dict(self._providers)
        providers[provider_id] = replace(provider, endpoints=endpoints)
        endpoint_auth_explicit = {
            entry
            for entry in self._endpoint_auth_explicit
            if entry != (provider_id, endpoint.id)
        }
        model_auth_explicit = {
            entry
            for entry in self._model_auth_explicit
            if entry[0] != provider_id or entry[1] != endpoint.id
        }
        if endpoint.auth is not None:
            endpoint_auth_explicit.add((provider_id, endpoint.id))
        for model_id, model in endpoint.models.items():
            if (
                model.auth is not None
                and (provider_id, endpoint.id, model_id) in self._model_auth_explicit
            ):
                model_auth_explicit.add((provider_id, endpoint.id, model_id))
                continue
            if model.auth is not None and not has_bound_endpoint_context(model):
                model_auth_explicit.add((provider_id, endpoint.id, model_id))
        self._replace_providers(
            providers,
            endpoint_auth_explicit=endpoint_auth_explicit,
            model_auth_explicit=model_auth_explicit,
        )

    def register_model(self, model: Model) -> None:
        provider = self._providers.get(model.provider_id)
        if provider is None:
            provider = Provider(id=model.provider_id)

        endpoint = provider.endpoints.get(model.endpoint_id)
        if endpoint is None:
            endpoint = Endpoint(
                id=model.endpoint_id,
                provider=model.provider_id,
                api=model.endpoint_id,
            )

        models = dict(endpoint.models)
        models[model.id] = model
        endpoint = replace(endpoint, models=models)
        endpoints = dict(provider.endpoints)
        endpoints[endpoint.id] = endpoint
        providers = dict(self._providers)
        providers[model.provider_id] = replace(provider, endpoints=endpoints)
        model_auth_explicit = set(self._model_auth_explicit)
        model_auth_explicit.discard((model.provider_id, endpoint.id, model.id))
        if model.auth is not None:
            model_auth_explicit.add((model.provider_id, endpoint.id, model.id))
        self._replace_providers(
            providers,
            endpoint_auth_explicit=set(self._endpoint_auth_explicit),
            model_auth_explicit=model_auth_explicit,
        )

    def get_provider(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[Provider]:
        return sorted(self._providers.values(), key=lambda item: item.id)

    def get_providers(self) -> list[str]:
        return [provider.id for provider in self.list_providers()]

    def get_endpoint(self, provider_id: str, endpoint_id: str) -> Endpoint | None:
        return self._endpoints.get((provider_id, endpoint_id))

    def list_endpoints(self, *, provider: str | None = None) -> list[Endpoint]:
        if provider is not None:
            resolved_provider = self.get_provider(provider)
            if resolved_provider is None:
                return []
            return resolved_provider.list_endpoints()
        return sorted(
            self._endpoints.values(),
            key=lambda item: (item.provider_id, item.id),
        )

    def get_model(self, *args: str) -> Model:
        if len(args) == 1:
            matches = self.list_models(model_id=args[0])
            if not matches:
                raise KeyError(args[0])
            if len(matches) > 1:
                raise ValueError(
                    f"Ambiguous model_id {args[0]!r}; use (provider, endpoint, model_id)"
                )
            return matches[0]
        if len(args) != 3:
            raise TypeError(
                "get_model expects either (model_id) or (provider, endpoint, model_id)"
            )
        provider_id, endpoint_id, model_id = args
        try:
            return self._models[(provider_id, endpoint_id, model_id)]
        except KeyError as error:
            raise KeyError((provider_id, endpoint_id, model_id)) from error

    def find_model(self, *args: str) -> Model | None:
        if len(args) == 1:
            matches = self.list_models(model_id=args[0])
            if len(matches) == 1:
                return matches[0]
            return None
        if len(args) != 3:
            raise TypeError(
                "find_model expects either (model_id) or (provider, endpoint, model_id)"
            )
        provider_id, endpoint_id, model_id = args
        return self._models.get((provider_id, endpoint_id, model_id))

    def has_explicit_endpoint_auth(self, provider_id: str, endpoint_id: str) -> bool:
        return (provider_id, endpoint_id) in self._endpoint_auth_explicit

    def has_explicit_model_auth(
        self,
        provider_id: str,
        endpoint_id: str,
        model_id: str,
    ) -> bool:
        return (provider_id, endpoint_id, model_id) in self._model_auth_explicit

    def list_models(
        self,
        *,
        provider: str | None = None,
        endpoint: str | None = None,
        model_id: str | None = None,
    ) -> list[Model]:
        models = sorted(
            self._models.values(),
            key=lambda item: (item.provider_id, item.endpoint_id, item.id),
        )
        if provider is not None:
            models = [model for model in models if model.provider_id == provider]
        if endpoint is not None:
            models = [model for model in models if model.endpoint_id == endpoint]
        if model_id is None:
            return models
        return [model for model in models if model.id == model_id]

    def _rebuild_index(self) -> None:
        self._endpoints = {}
        self._models = {}
        for provider in self._providers.values():
            for endpoint in provider.endpoints.values():
                self._endpoints[(provider.id, endpoint.id)] = endpoint
                for model in endpoint.models.values():
                    self._models[(provider.id, endpoint.id, model.id)] = model
