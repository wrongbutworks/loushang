"""Compatibility imports for package materialization.

Package lifecycle types live in `loushang.coding.package.materializer`.
"""

from loushang.coding.package.materializer import (
    GitPackageMaterializerBackend,
    PackageMaterializationLifecycle,
    PackageMaterializationRecord,
    PackageMaterializer,
    PackageMaterializerBackend,
    PackageSourcePolicy,
)

__all__ = [
    "GitPackageMaterializerBackend",
    "PackageMaterializationLifecycle",
    "PackageMaterializationRecord",
    "PackageMaterializer",
    "PackageMaterializerBackend",
    "PackageSourcePolicy",
]
