from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltInResourcePackage:
    name: str
    package: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("built-in resource package name must not be empty")
        if not self.package.strip():
            raise ValueError("built-in resource package import path must not be empty")


class BuiltInResourceRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, BuiltInResourcePackage] = {}

    def register(self, package: BuiltInResourcePackage) -> BuiltInResourcePackage:
        self._packages[package.name] = package
        return package

    def unregister(self, name: str) -> BuiltInResourcePackage | None:
        return self._packages.pop(name, None)

    def get(self, name: str) -> BuiltInResourcePackage | None:
        return self._packages.get(name)

    def list_packages(self) -> tuple[BuiltInResourcePackage, ...]:
        return tuple(self._packages[name] for name in sorted(self._packages))

    def import_paths(self) -> tuple[str, ...]:
        return tuple(package.package for package in self.list_packages())
