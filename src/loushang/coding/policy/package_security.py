"""Compatibility import for the shared package source security policy."""

from loushang.harness.resources.packages.security import (
    PackageSecurityPolicy,
    PackageSourceSecurityReport,
)

__all__ = ["PackageSecurityPolicy", "PackageSourceSecurityReport"]
