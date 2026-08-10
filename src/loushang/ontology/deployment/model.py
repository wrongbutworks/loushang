"""Strict immutable values selecting one Ontology deployment cut."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

from loushang.foundation.json import JSONValue, dump_json_value, require_json_mapping
from loushang.ontology.schema.identity import SchemaIdentity

DEPLOYMENT_PROFILE_FORMAT = "loushang.ontology.deployment-profile/v1"


@dataclass(frozen=True, slots=True)
class SchemaArtifactLock:
    """Exact compiled Ontology schema selected by one deployment."""

    schema_identity: SchemaIdentity
    content_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.schema_identity, SchemaIdentity):
            raise TypeError("schema_identity must be a SchemaIdentity")
        _require_digest("content_digest", self.content_digest)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_identity": self.schema_identity.to_dict(),
            "content_digest": self.content_digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> SchemaArtifactLock:
        document = _exact_document(
            value,
            name="schema artifact lock",
            keys={"schema_identity", "content_digest"},
        )
        identity_document = _exact_document(
            document["schema_identity"],
            name="schema identity",
            keys={"package_id", "namespace", "version"},
        )
        return cls(
            schema_identity=SchemaIdentity.from_dict(identity_document),
            content_digest=_document_text(document, "content_digest"),
        )


@dataclass(frozen=True, slots=True)
class SourceAdapterArtifactLock:
    """Exact source-adapter manifest selected by one deployment."""

    adapter_id: str
    adapter_version: str
    manifest_digest: str

    def __post_init__(self) -> None:
        _non_empty_text("adapter_id", self.adapter_id)
        _non_empty_text("adapter_version", self.adapter_version)
        _require_digest("manifest_digest", self.manifest_digest)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "manifest_digest": self.manifest_digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> SourceAdapterArtifactLock:
        document = _exact_document(
            value,
            name="source adapter artifact lock",
            keys={"adapter_id", "adapter_version", "manifest_digest"},
        )
        return cls(
            adapter_id=_document_text(document, "adapter_id"),
            adapter_version=_document_text(document, "adapter_version"),
            manifest_digest=_document_text(document, "manifest_digest"),
        )


@dataclass(frozen=True, slots=True)
class DeploymentProfile:
    """Content-addressed artifact selection; contains no runtime credentials."""

    deployment_id: str
    schema_lock: SchemaArtifactLock
    adapter_locks: tuple[SourceAdapterArtifactLock, ...] | list[
        SourceAdapterArtifactLock
    ]
    enabled_binding_ids: tuple[str, ...] | list[str]
    fact_store_ref: str
    projection_store_ref: str
    format: str = DEPLOYMENT_PROFILE_FORMAT

    def __post_init__(self) -> None:
        _non_empty_text("deployment_id", self.deployment_id)
        if not isinstance(self.schema_lock, SchemaArtifactLock):
            raise TypeError("schema_lock must be a SchemaArtifactLock")
        locks = tuple(self.adapter_locks)
        if any(not isinstance(item, SourceAdapterArtifactLock) for item in locks):
            raise TypeError(
                "adapter_locks must contain SourceAdapterArtifactLock values"
            )
        locks = tuple(sorted(locks, key=lambda item: item.adapter_id))
        adapter_ids = [item.adapter_id for item in locks]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("deployment profile contains duplicate adapter IDs")
        object.__setattr__(self, "adapter_locks", locks)

        binding_ids = tuple(sorted(self.enabled_binding_ids))
        if any(not isinstance(item, str) or not item.strip() for item in binding_ids):
            raise ValueError("enabled_binding_ids must contain non-empty strings")
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("deployment profile contains duplicate binding IDs")
        object.__setattr__(self, "enabled_binding_ids", binding_ids)
        _non_empty_text("fact_store_ref", self.fact_store_ref)
        _non_empty_text("projection_store_ref", self.projection_store_ref)
        if self.format != DEPLOYMENT_PROFILE_FORMAT:
            raise ValueError("unsupported deployment profile format")

    @property
    def profile_digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "format": self.format,
            "deployment_id": self.deployment_id,
            "schema_lock": self.schema_lock.to_dict(),
            "adapter_locks": [item.to_dict() for item in self.adapter_locks],
            "enabled_binding_ids": list(self.enabled_binding_ids),
            "fact_store_ref": self.fact_store_ref,
            "projection_store_ref": self.projection_store_ref,
        }

    def to_json(self) -> str:
        return dump_json_value(
            self.to_dict(),
            name="deployment profile",
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, payload: str) -> DeploymentProfile:
        try:
            document = _exact_document(
                json.loads(payload),
                name="deployment profile",
                keys={
                    "format",
                    "deployment_id",
                    "schema_lock",
                    "adapter_locks",
                    "enabled_binding_ids",
                    "fact_store_ref",
                    "projection_store_ref",
                },
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid deployment profile JSON: {exc}") from exc
        if document["format"] != DEPLOYMENT_PROFILE_FORMAT:
            raise ValueError("unsupported deployment profile format")
        raw_adapter_locks = _document_list(document, "adapter_locks")
        raw_binding_ids = _document_list(document, "enabled_binding_ids")
        if any(not isinstance(item, str) for item in raw_binding_ids):
            raise ValueError(
                "deployment profile enabled_binding_ids must be a string list"
            )
        return cls(
            deployment_id=_document_text(document, "deployment_id"),
            schema_lock=SchemaArtifactLock.from_dict(document["schema_lock"]),
            adapter_locks=[
                SourceAdapterArtifactLock.from_dict(item)
                for item in raw_adapter_locks
            ],
            enabled_binding_ids=cast(list[str], raw_binding_ids),
            fact_store_ref=_document_text(document, "fact_store_ref"),
            projection_store_ref=_document_text(document, "projection_store_ref"),
        )


def _exact_document(
    value: object,
    *,
    name: str,
    keys: set[str],
) -> dict[str, JSONValue]:
    document = require_json_mapping(value, name=name)
    if set(document) != keys:
        raise ValueError(f"{name} fields do not match the supported format")
    return document


def _non_empty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_digest(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _document_text(document: dict[str, JSONValue], name: str) -> str:
    try:
        return _non_empty_text(name, document[name])
    except KeyError as exc:  # pragma: no cover - exact fields report first
        raise ValueError(f"deployment profile is missing {name}") from exc


def _document_list(
    document: dict[str, JSONValue],
    name: str,
) -> list[JSONValue]:
    value = document[name]
    if not isinstance(value, list):
        raise ValueError(f"deployment profile {name} must be a list")
    return value


__all__ = [
    "DEPLOYMENT_PROFILE_FORMAT",
    "DeploymentProfile",
    "SchemaArtifactLock",
    "SourceAdapterArtifactLock",
]
