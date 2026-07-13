from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loushang.harness.resources.packages.materializer import (
    GitPackageMaterializerBackend,
    PackageMaterializationLifecycle,
    PackageMaterializationRecord,
    PackageMaterializerBackend,
    PackageProgressEvent,
    PackageSourcePolicy,
    PythonPackageInstallerBackend,
)
from loushang.harness.resources.packages.materializer import (
    PackageMaterializer as HarnessPackageMaterializer,
)


class PackageMaterializer(HarnessPackageMaterializer):
    """Coding facade that injects the product package-security defaults."""

    def __init__(
        self,
        *,
        install_root: str | Path,
        backend: PackageMaterializerBackend | None = None,
        python_backend: PackageMaterializerBackend | None = None,
        security_policy: PackageSourcePolicy | None = None,
        lockfile_path: str | Path | None = None,
        update_concurrency: int = 4,
        check_concurrency: int = 4,
        update_check_timeout_seconds: float = 10.0,
        progress_callback: Callable[[PackageProgressEvent], None] | None = None,
    ) -> None:
        if security_policy is None:
            from loushang.coding.policy.package_security import PackageSecurityPolicy

            security_policy = PackageSecurityPolicy()
        super().__init__(
            install_root=install_root,
            backend=backend,
            python_backend=python_backend,
            security_policy=security_policy,
            lockfile_path=lockfile_path,
            update_concurrency=update_concurrency,
            check_concurrency=check_concurrency,
            update_check_timeout_seconds=update_check_timeout_seconds,
            progress_callback=progress_callback,
        )


__all__ = [
    "GitPackageMaterializerBackend",
    "PackageMaterializationLifecycle",
    "PackageMaterializationRecord",
    "PackageMaterializer",
    "PackageMaterializerBackend",
    "PackageProgressEvent",
    "PackageSourcePolicy",
    "PythonPackageInstallerBackend",
]
