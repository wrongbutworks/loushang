from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence

from loushang.harness.extensions.registry import source_info_from_extension
from loushang.harness.extensions.types import (
    InputEvent,
    InputEventResult,
    LoadedExtension,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic

ExtensionContextFactory = Callable[[LoadedExtension], object]
ExtensionRuntimeErrorHandler = Callable[[LoadedExtension, str, Exception], None]


class ExtensionDispatcher:
    """Ordered, failure-contained dispatch for product-neutral extension hooks."""

    def __init__(
        self,
        extensions: Sequence[LoadedExtension],
        *,
        context_factory: ExtensionContextFactory,
        diagnostics: list[ResourceDiagnostic],
        runtime_error_handler: ExtensionRuntimeErrorHandler | None = None,
    ) -> None:
        self._extensions = tuple(extensions)
        self._context_factory = context_factory
        self._diagnostics = diagnostics
        self._runtime_error_handler = runtime_error_handler

    def has_handlers(self, event_name: str) -> bool:
        return any(extension.hooks.get(event_name) for extension in self._extensions)

    async def dispatch(self, event_name: str, event: object) -> tuple[object, ...]:
        results: list[object] = []
        for extension in self._extensions:
            context = self._context_factory(extension)
            for handler in extension.hooks.get(event_name, ()):
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._record_error(extension, event_name, exc)
                    continue
                if result is not None:
                    results.append(result)
        return tuple(results)

    async def dispatch_first_truthy(
        self, event_name: str, event: object
    ) -> object | None:
        for extension in self._extensions:
            context = self._context_factory(extension)
            for handler in extension.hooks.get(event_name, ()):
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._record_error(extension, event_name, exc)
                    continue
                if result:
                    return result
        return None

    async def dispatch_input(
        self,
        text: str,
        images: list[object] | None = None,
        *,
        source: str = "interactive",
    ) -> InputEventResult:
        current_text = text
        current_images = images
        transformed = False
        for extension in self._extensions:
            context = self._context_factory(extension)
            for handler in extension.hooks.get("input", ()):
                event = InputEvent(
                    text=current_text,
                    images=current_images,
                    source=_normalize_input_source(source),
                )
                try:
                    result = handler(event, context)
                    if inspect.isawaitable(result):
                        result = await result
                except Exception as exc:
                    self._record_error(extension, "input", exc)
                    continue
                action, result_text, result_images = _coerce_input_result(result)
                if action in {None, "continue"}:
                    continue
                if action == "handled":
                    return InputEventResult(
                        action="handled",
                        text=current_text,
                        images=current_images,
                    )
                if action == "transform":
                    if result_text is None:
                        self._diagnostics.append(
                            _invalid_input_diagnostic(
                                extension,
                                "input transform results must include string text.",
                            )
                        )
                        continue
                    current_text = result_text
                    if result_images is not None:
                        current_images = result_images
                    transformed = True
                    continue
                self._diagnostics.append(
                    _invalid_input_diagnostic(
                        extension,
                        (
                            "input hooks must return action 'continue', 'transform', "
                            "'handled', or None."
                        ),
                    )
                )
        if transformed or current_text != text or current_images is not images:
            return InputEventResult(
                action="transform",
                text=current_text,
                images=current_images,
            )
        return InputEventResult(
            action="continue",
            text=current_text,
            images=current_images,
        )

    def _record_error(
        self,
        extension: LoadedExtension,
        event_name: str,
        error: Exception,
    ) -> None:
        source_info = source_info_from_extension(extension)
        self._diagnostics.append(
            ResourceDiagnostic(
                code=f"extension_{event_name}_failed",
                message=f"Extension hook '{event_name}' failed: {error}",
                source_path=extension.source_path,
                metadata={
                    "extension_name": extension.name,
                    "hook": event_name,
                    "source": source_info.source,
                    "scope": source_info.scope,
                    "origin": source_info.origin,
                    "base_dir": (
                        source_info.base_dir.as_posix()
                        if source_info.base_dir is not None
                        else extension.source_path.parent.as_posix()
                    ),
                },
            )
        )
        if self._runtime_error_handler is not None:
            self._runtime_error_handler(extension, event_name, error)


def _normalize_input_source(source: str) -> str:
    return source if source in {"interactive", "rpc", "extension"} else "interactive"


def _coerce_input_result(
    result: object,
) -> tuple[str | None, str | None, list[object] | None]:
    if result is None:
        return None, None, None
    if isinstance(result, InputEventResult):
        return result.action, result.text, result.images
    if isinstance(result, dict):
        action = result.get("action")
        text = result.get("text")
        images = result.get("images")
        return (
            action if isinstance(action, str) else None,
            text if isinstance(text, str) else None,
            images if isinstance(images, list) else None,
        )
    return None, None, None


def _invalid_input_diagnostic(
    extension: LoadedExtension,
    message: str,
) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        code="invalid_extension_input_result",
        message=message,
        source_path=extension.source_path,
    )


__all__ = [
    "ExtensionContextFactory",
    "ExtensionDispatcher",
    "ExtensionRuntimeErrorHandler",
]
