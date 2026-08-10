"""Pure compatibility validation for immutable deployment profiles."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from loushang.ontology.deployment.model import (
    DeploymentProfile,
    SchemaArtifactLock,
    SourceAdapterArtifactLock,
)
from loushang.ontology.schema import CompiledOntologySchema, SchemaIdentity
from loushang.ontology.source.adapter import SourceAdapterManifest
from loushang.ontology.source.model import SourceBinding


class DeploymentProfileValidationError(ValueError):
    """Stable compatibility failure raised before Product composition."""

    def __init__(self, code: str, message: str) -> None:
        self.code = _non_empty_text("code", code)
        super().__init__(message)


def lock_schema_artifact(schema: CompiledOntologySchema) -> SchemaArtifactLock:
    """Create the exact identity and content lock for a compiled schema."""

    if not isinstance(schema, CompiledOntologySchema):
        raise TypeError("schema must be a CompiledOntologySchema")
    return SchemaArtifactLock(
        schema_identity=SchemaIdentity.from_schema(schema),
        content_digest=_sha256_text(schema.to_json()),
    )


def lock_source_adapter_artifact(
    manifest: SourceAdapterManifest,
) -> SourceAdapterArtifactLock:
    """Create the exact identity and content lock for an adapter manifest."""

    if not isinstance(manifest, SourceAdapterManifest):
        raise TypeError("manifest must be a SourceAdapterManifest")
    return SourceAdapterArtifactLock(
        adapter_id=manifest.adapter_id,
        adapter_version=manifest.adapter_version,
        manifest_digest=_sha256_text(manifest.to_json()),
    )


def validate_deployment_profile(
    profile: DeploymentProfile,
    *,
    schema: CompiledOntologySchema,
    adapter_manifests: Iterable[SourceAdapterManifest],
) -> tuple[SourceBinding, ...]:
    """Validate exact artifacts and return the enabled detached bindings."""

    if not isinstance(profile, DeploymentProfile):
        raise TypeError("profile must be a DeploymentProfile")
    if not isinstance(schema, CompiledOntologySchema):
        raise TypeError("schema must be a CompiledOntologySchema")
    manifests = tuple(adapter_manifests)
    if any(not isinstance(item, SourceAdapterManifest) for item in manifests):
        raise TypeError("adapter_manifests must contain SourceAdapterManifest values")

    actual_schema_lock = lock_schema_artifact(schema)
    if profile.schema_lock.schema_identity != actual_schema_lock.schema_identity:
        raise DeploymentProfileValidationError(
            "schema_identity_mismatch",
            "compiled schema identity does not match the deployment lock",
        )
    if profile.schema_lock.content_digest != actual_schema_lock.content_digest:
        raise DeploymentProfileValidationError(
            "schema_digest_mismatch",
            "compiled schema content does not match the deployment lock",
        )

    manifest_by_id: dict[str, SourceAdapterManifest] = {}
    for manifest in manifests:
        if manifest.adapter_id in manifest_by_id:
            raise DeploymentProfileValidationError(
                "duplicate_adapter_manifest",
                f"adapter manifest '{manifest.adapter_id}' was supplied more than once",
            )
        manifest_by_id[manifest.adapter_id] = manifest
    lock_by_id = {item.adapter_id: item for item in profile.adapter_locks}
    if set(lock_by_id) != set(manifest_by_id):
        raise DeploymentProfileValidationError(
            "adapter_set_mismatch",
            "supplied adapter manifests do not match the deployment locks",
        )

    bindings_by_id: dict[str, tuple[str, SourceBinding]] = {}
    adapter_binding_ids: dict[str, set[str]] = {}
    for adapter_id in sorted(lock_by_id):
        lock = lock_by_id[adapter_id]
        manifest = manifest_by_id[adapter_id]
        actual_lock = lock_source_adapter_artifact(manifest)
        if lock.adapter_version != actual_lock.adapter_version:
            raise DeploymentProfileValidationError(
                "adapter_version_mismatch",
                f"adapter '{adapter_id}' version does not match the deployment lock",
            )
        if lock.manifest_digest != actual_lock.manifest_digest:
            raise DeploymentProfileValidationError(
                "adapter_digest_mismatch",
                f"adapter '{adapter_id}' manifest does not match the deployment lock",
            )
        if manifest.target_schema != profile.schema_lock.schema_identity:
            raise DeploymentProfileValidationError(
                "adapter_target_schema_mismatch",
                f"adapter '{adapter_id}' targets a different Ontology schema",
            )
        adapter_binding_ids[adapter_id] = {
            binding.binding_id for binding in manifest.bindings
        }
        for binding in manifest.bindings:
            if binding.binding_id in bindings_by_id:
                raise DeploymentProfileValidationError(
                    "duplicate_binding_id",
                    f"binding '{binding.binding_id}' is declared by multiple adapters",
                )
            bindings_by_id[binding.binding_id] = (adapter_id, binding)

    enabled = set(profile.enabled_binding_ids)
    missing = enabled - set(bindings_by_id)
    if missing:
        raise DeploymentProfileValidationError(
            "enabled_binding_missing",
            "enabled bindings are absent from locked adapter manifests: "
            + ", ".join(sorted(missing)),
        )
    for adapter_id, binding_ids in adapter_binding_ids.items():
        if not enabled.intersection(binding_ids):
            raise DeploymentProfileValidationError(
                "unused_adapter_lock",
                f"adapter '{adapter_id}' contributes no enabled binding",
            )
    return tuple(bindings_by_id[item][1] for item in profile.enabled_binding_ids)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _non_empty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


__all__ = [
    "DeploymentProfileValidationError",
    "lock_schema_artifact",
    "lock_source_adapter_artifact",
    "validate_deployment_profile",
]
