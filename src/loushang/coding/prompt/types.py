"""Compatibility exports for canonical Harness prompt types."""

from loushang.harness.capabilities.prompt import PreparedPrompt as PreparedPrompt
from loushang.harness.capabilities.prompt import PromptSection as PromptSection
from loushang.harness.capabilities.prompt import PromptTraceEntry as PromptTraceEntry
from loushang.harness.capabilities.prompt_assembly import (
    PromptAssembly as PromptAssembly,
)

__all__ = [
    "PreparedPrompt",
    "PromptAssembly",
    "PromptSection",
    "PromptTraceEntry",
]
