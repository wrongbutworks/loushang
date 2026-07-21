from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from loushang.ai.auth.sources.base import CredentialSource
from loushang.ai.auth.sources.openai_codex import OpenAICodexCredentialSource


class AuthExtensionRegistry:
    """Registry for optional auth capabilities outside generic auth flows."""

    def __init__(self, sources: Iterable[CredentialSource] = ()) -> None:
        self._credential_sources: dict[str, CredentialSource] = {}
        for source in sources:
            self.register_credential_source(source)

    @property
    def credential_sources(self) -> Mapping[str, CredentialSource]:
        return MappingProxyType(dict(self._credential_sources))

    def register_credential_source(
        self,
        source: CredentialSource,
        *,
        replace: bool = False,
    ) -> None:
        _validate_source(source)
        if source.id in self._credential_sources and not replace:
            raise ValueError(f"Credential source already registered: {source.id}")
        self._credential_sources[source.id] = source

    def get_credential_source(self, source_id: str) -> CredentialSource | None:
        return self._credential_sources.get(source_id)

    def find_credential_source(self, model: object) -> CredentialSource | None:
        return next(
            (
                source
                for source in self._credential_sources.values()
                if source.matches(model)
            ),
            None,
        )


def register_credential_source(
    source: CredentialSource,
    *,
    replace: bool = False,
) -> None:
    _default_registry.register_credential_source(source, replace=replace)


def get_credential_source(source_id: str) -> CredentialSource | None:
    return _default_registry.get_credential_source(source_id)


def get_auth_extension_registry() -> AuthExtensionRegistry:
    return _default_registry


def _validate_source(source: CredentialSource) -> None:
    if (
        not isinstance(getattr(source, "id", None), str)
        or not source.id.strip()
        or not isinstance(getattr(source, "description", None), str)
        or not source.description.strip()
        or not isinstance(getattr(source, "experimental", None), bool)
        or not isinstance(getattr(source, "supports_refresh", None), bool)
        or not callable(getattr(source, "matches", None))
        or not callable(getattr(source, "load", None))
        or not callable(getattr(source, "load_file", None))
    ):
        raise TypeError(
            "Credential source must define id, description, experimental, "
            "supports_refresh, matches, load, and load_file"
        )


_default_registry = AuthExtensionRegistry([OpenAICodexCredentialSource()])


__all__ = [
    "AuthExtensionRegistry",
    "get_auth_extension_registry",
    "get_credential_source",
    "register_credential_source",
]
