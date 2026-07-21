"""Coding's extension policy binding over the shared Harness runner."""

from __future__ import annotations

from loushang.coding.extensions.loader import ExtensionLoader
from loushang.harness.extensions.runner import (
    ExtensionRunner as _HarnessExtensionRunner,
)
from loushang.harness.extensions.types import ExtensionDescriptor, LoadedExtension


class ExtensionRunner(_HarnessExtensionRunner):
    """Bind Coding's loader and policy while reusing Harness dispatch/runtime."""

    def __init__(
        self, extensions: list[LoadedExtension | ExtensionDescriptor] | None = None
    ) -> None:
        super().__init__(extensions, loader_factory=ExtensionLoader)


__all__ = ["ExtensionRunner"]
