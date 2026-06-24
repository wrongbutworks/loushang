from __future__ import annotations

from dataclasses import replace

from loushang.ai.model.domain import (
    Defaults,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    Provider,
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
    if not getattr(model, "api", None):
        return False
    if isinstance(getattr(model, "_endpoint_ref", None), Endpoint):
        return True
    if (
        getattr(model, "base_url", None)
        or getattr(model, "base_url_env", None)
        or getattr(model, "region", None)
        or getattr(model, "lane", None)
        or getattr(model, "preferred_endpoint", False)
        or getattr(model, "_auth_inherited", False)
    ):
        return True
    return False


def _endpoint_snapshot_from_model(model: Model) -> Endpoint:
    endpoint = getattr(model, "_endpoint_ref", None)
    if isinstance(endpoint, Endpoint):
        return endpoint
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
    def __init__(self, providers: dict[str, Provider] | None = None) -> None:
        self._providers = dict(providers or {})
        self._endpoints: dict[tuple[str, str], Endpoint] = {}
        self._models: dict[tuple[str, str, str], Model] = {}
        self._rebuild_index()

    @property
    def providers(self) -> dict[str, Provider]:
        return dict(self._providers)

    @classmethod
    def from_providers(cls, providers: dict[str, Provider]) -> "ModelRegistry":
        return cls(providers=providers)

    def replace_providers(self, providers: dict[str, Provider]) -> None:
        self._providers = dict(providers)
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

        normalized_endpoint = replace(endpoint, _provider_key=provider_id)
        if normalized_endpoint.models:
            normalized_endpoint = replace(
                normalized_endpoint,
                models={
                    model_id: normalized_endpoint.bind_model(model)
                    for model_id, model in normalized_endpoint.models.items()
                },
            )

        endpoints = dict(provider.endpoints)
        endpoints[normalized_endpoint.id] = normalized_endpoint
        self.register_provider(replace(provider, endpoints=endpoints))

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
        models[model.id] = endpoint.bind_model(model)
        self.register_endpoint(
            model.provider_id,
            replace(
                endpoint,
                models=models,
            ),
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
                    bound_model = endpoint.bind_model(model)
                    self._models[(provider.id, endpoint.id, model.id)] = bound_model
