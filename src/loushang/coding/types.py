from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loushang.coding.control.types import ControlConfig


@dataclass(frozen=True)
class ModelSelection:
    provider: str
    model_id: str


def __getattr__(name: str):
    if name == "ControlConfig":
        from loushang.coding.control.types import ControlConfig

        return ControlConfig
    raise AttributeError(name)


__all__ = ["ControlConfig", "ModelSelection"]
