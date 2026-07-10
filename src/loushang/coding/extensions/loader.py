from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from loushang.coding.extensions.api import ExtensionAPI
from loushang.coding.extensions.contributions import surfaces_from_loaded_extension
from loushang.coding.extensions.manifest import parse_extension_manifest
from loushang.coding.extensions.policy import policy_from_manifest
from loushang.coding.extensions.types import LoadedExtension
from loushang.coding.loader import ExtensionDescriptor
from loushang.coding.tools import ToolDefinition
from loushang.harness.resources.diagnostics import ResourceDiagnostic


class ExtensionLoader:
    def __init__(self) -> None:
        self._diagnostics: list[ResourceDiagnostic] = []

    def get_diagnostics(self) -> list[ResourceDiagnostic]:
        return list(self._diagnostics)

    def load_extensions(self, descriptors: list[ExtensionDescriptor]) -> list[LoadedExtension]:
        self._diagnostics = []
        loaded_extensions: list[LoadedExtension] = []
        for descriptor in descriptors:
            loaded = self.load_extension(descriptor)
            if loaded is not None:
                loaded_extensions.append(loaded)
        return loaded_extensions

    def load_extension(self, descriptor: ExtensionDescriptor) -> LoadedExtension | None:
        manifest, manifest_diagnostics = _load_descriptor_manifest(descriptor)
        self._diagnostics.extend(manifest_diagnostics)
        metadata = descriptor.metadata if isinstance(descriptor.metadata, Mapping) else {}
        if "extension" in metadata:
            try:
                return _finalize_loaded_extension(
                    _with_descriptor_source_info(
                        _adapt_legacy_extension_object(
                            descriptor=descriptor,
                            entry_path=descriptor.entry_path or descriptor.source_path,
                            extension_object=metadata["extension"],
                        ),
                        descriptor,
                    ),
                    manifest=manifest,
                    enabled=descriptor.enabled,
                )
            except Exception as exc:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_load_failed",
                        message=f"Legacy metadata extension adaptation failed: {exc}",
                        source_path=descriptor.source_path,
                    )
                )
                return None

        entry_path = descriptor.entry_path
        if entry_path is None or not entry_path.is_file():
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="missing_extension_entry",
                    message="Extension descriptor does not point to a valid entry file.",
                    source_path=entry_path or descriptor.source_path,
                )
            )
            return None

        try:
            module = _load_extension_module(entry_path)
        except Exception as exc:
            self._diagnostics.append(
                ResourceDiagnostic(
                    code="extension_load_failed",
                    message=f"Failed to load extension module: {exc}",
                    source_path=entry_path,
                )
            )
            return None

        api = ExtensionAPI(name=descriptor.name, source_path=descriptor.source_path, entry_path=entry_path)
        register = getattr(module, "register", None)
        if callable(register):
            try:
                loaded = _register_with_api(register, api, entry_path)
            except Exception as exc:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_load_failed",
                        message=f"Extension register(api) failed: {exc}",
                        source_path=entry_path,
                    )
                )
                return None
            if loaded is not None:
                return _finalize_loaded_extension(
                    _with_descriptor_source_info(loaded, descriptor),
                    manifest=manifest,
                    enabled=descriptor.enabled,
                )
            return None

        builder = getattr(module, "build_extension", None)
        if callable(builder):
            try:
                extension_object = builder()
            except Exception as exc:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_load_failed",
                        message=f"Extension factory failed: {exc}",
                        source_path=entry_path,
                    )
                )
                return None
            if inspect.isawaitable(extension_object):
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="unsupported_async_extension_factory",
                        message="Async extension factories are not supported in v1.",
                        source_path=entry_path,
                    )
                )
                return None
            try:
                return _finalize_loaded_extension(
                    _with_descriptor_source_info(
                        _adapt_legacy_extension_object(
                            descriptor=descriptor,
                            entry_path=entry_path,
                            extension_object=extension_object,
                        ),
                        descriptor,
                    ),
                    manifest=manifest,
                    enabled=descriptor.enabled,
                )
            except Exception as exc:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_load_failed",
                        message=f"Legacy build_extension() adaptation failed: {exc}",
                        source_path=entry_path,
                    )
                )
                return None

        if hasattr(module, "EXTENSION"):
            try:
                return _finalize_loaded_extension(
                    _with_descriptor_source_info(
                        _adapt_legacy_extension_object(
                            descriptor=descriptor,
                            entry_path=entry_path,
                            extension_object=getattr(module, "EXTENSION"),
                        ),
                        descriptor,
                    ),
                    manifest=manifest,
                    enabled=descriptor.enabled,
                )
            except Exception as exc:
                self._diagnostics.append(
                    ResourceDiagnostic(
                        code="extension_load_failed",
                        message=f"Legacy EXTENSION adaptation failed: {exc}",
                        source_path=entry_path,
                    )
                )
                return None

        self._diagnostics.append(
            ResourceDiagnostic(
                code="invalid_extension_export",
                message="Extension modules must export register(api), build_extension(), or EXTENSION.",
                source_path=entry_path,
            )
        )
        return None


def _register_with_api(register, api: ExtensionAPI, entry_path: Path) -> LoadedExtension | None:
    result = register(api)
    if inspect.isawaitable(result):
        raise TypeError(f"Async register(api) is not supported in v1: {entry_path}")
    return api.build_loaded_extension()


def _with_descriptor_source_info(loaded: LoadedExtension, descriptor: ExtensionDescriptor) -> LoadedExtension:
    return replace(
        loaded,
        source=descriptor.source,
        source_kind=descriptor.source_kind,
        source_scope=descriptor.source_scope,
        source_root=descriptor.source_root,
    )


def _finalize_loaded_extension(
    loaded: LoadedExtension,
    *,
    manifest,
    enabled: bool,
) -> LoadedExtension:
    with_policy = replace(
        loaded,
        manifest=manifest,
        policy=policy_from_manifest(manifest, enabled=enabled),
    )
    return replace(with_policy, contributions=list(surfaces_from_loaded_extension(with_policy)))


def _load_descriptor_manifest(descriptor: ExtensionDescriptor):
    manifest_path = _descriptor_manifest_path(descriptor)
    if manifest_path is None:
        return None, []
    result = parse_extension_manifest(manifest_path)
    return result.manifest, result.diagnostics


def _descriptor_manifest_path(descriptor: ExtensionDescriptor) -> Path | None:
    candidates: list[Path] = []
    if descriptor.source_path.is_dir():
        candidates.append(descriptor.source_path / "loushang-extension.toml")
    if descriptor.entry_path is not None:
        candidates.append(descriptor.entry_path.parent / "loushang-extension.toml")
    if descriptor.source_path.is_file():
        candidates.append(descriptor.source_path.with_name("loushang-extension.toml"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _adapt_legacy_extension_object(
    *,
    descriptor: ExtensionDescriptor,
    entry_path: Path,
    extension_object: object,
) -> LoadedExtension:
    api = ExtensionAPI(name=descriptor.name, source_path=descriptor.source_path, entry_path=entry_path)
    for event_name in (
        "session_start",
        "session_refresh",
        "before_agent_start",
        "session_shutdown",
        "resources_discover",
        "context",
        "tool_call",
        "tool_result",
    ):
        handler = getattr(extension_object, event_name, None)
        if callable(handler):
            api.on(event_name, _wrap_legacy_handler(handler))

    get_tools = getattr(extension_object, "get_tools", None)
    if callable(get_tools):
        tools = get_tools()
        if inspect.isawaitable(tools):
            raise TypeError("Async get_tools() is not supported in v1.")
        for tool in list(tools or []):
            if not isinstance(tool, ToolDefinition):
                raise TypeError("Legacy get_tools() must return ToolDefinition objects in v1.")
            api.register_tool(tool)

    return api.build_loaded_extension()


def _wrap_legacy_handler(handler):
    def _wrapped(event, ctx):
        return handler(event)

    return _wrapped


def _load_extension_module(entry_path: Path):
    module_name = f"loushang_coding_extension_loader_{hashlib.sha1(str(entry_path).encode('utf-8')).hexdigest()}"
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {entry_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
