from __future__ import annotations

from pathlib import Path


def test_coding_source_info_paths_preserve_harness_owner_identity() -> None:
    from loushang.coding.extensions import SourceInfo as ExtensionSourceInfo
    from loushang.coding.extensions.types import SourceInfo as ExtensionTypesSourceInfo
    from loushang.coding.source_info import SourceInfo as CodingSourceInfo
    from loushang.coding.source_info import create_source_info
    from loushang.harness.resources.source import SourceInfo as HarnessSourceInfo

    assert CodingSourceInfo is ExtensionSourceInfo is ExtensionTypesSourceInfo is HarnessSourceInfo
    assert HarnessSourceInfo.__module__ == "loushang.harness.resources.source"

    command_info = create_source_info(Path("/tmp/project/prompts/review.md"))
    extension_info = ExtensionSourceInfo(path=Path("/tmp/project/extensions/demo.py"))

    assert command_info.path == "/tmp/project/prompts/review.md"
    assert extension_info.path == Path("/tmp/project/extensions/demo.py")


def test_coding_resource_diagnostic_paths_preserve_harness_owner_identity() -> None:
    from loushang.coding.loader import ResourceDiagnostic as LoaderResourceDiagnostic
    from loushang.coding.loader.types import (
        ResourceDiagnostic as LoaderTypesResourceDiagnostic,
    )
    from loushang.harness.resources.diagnostics import (
        ResourceDiagnostic as HarnessResourceDiagnostic,
    )

    assert LoaderResourceDiagnostic is LoaderTypesResourceDiagnostic is HarnessResourceDiagnostic
    assert HarnessResourceDiagnostic.__module__ == "loushang.harness.resources.diagnostics"
