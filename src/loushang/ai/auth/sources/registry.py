from __future__ import annotations

from loushang.ai.auth.sources.base import CredentialSource
from loushang.ai.auth.sources.openai_codex import OpenAICodexCredentialSource

_credential_sources: dict[str, CredentialSource] = {
    OpenAICodexCredentialSource.id: OpenAICodexCredentialSource(),
}


def register_credential_source(
    source: CredentialSource,
    *,
    replace: bool = False,
) -> None:
    _validate_source(source)
    if source.id in _credential_sources and not replace:
        raise ValueError(f"Credential source already registered: {source.id}")
    _credential_sources[source.id] = source


def get_credential_source(source_id: str) -> CredentialSource | None:
    return _credential_sources.get(source_id)


def _validate_source(source: CredentialSource) -> None:
    if (
        not isinstance(getattr(source, "id", None), str)
        or not source.id.strip()
        or not callable(getattr(source, "load", None))
        or not callable(getattr(source, "load_file", None))
    ):
        raise TypeError("Credential source must define id, load, and load_file")


__all__ = ["get_credential_source", "register_credential_source"]
