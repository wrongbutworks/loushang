"""Product-neutral presentation of a command that resumes a conversation."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class ConversationResumeHint:
    """Prepared copy and command arguments for one resume hint."""

    heading: str
    command: tuple[str, ...]


def render_conversation_resume_hint(hint: ConversationResumeHint) -> str:
    """Render a prepared resume hint without knowing product session policy."""

    return f"\n{hint.heading}\n{shlex.join(hint.command)}\n"


def write_clean_exit_resume_hint(
    *,
    stdout: TextIO,
    exit_code: int,
    hint: ConversationResumeHint | None,
) -> None:
    """Write and flush a prepared hint only after a successful exit."""

    if exit_code != 0 or hint is None:
        return
    stdout.write(render_conversation_resume_hint(hint))
    stdout.flush()


__all__ = [
    "ConversationResumeHint",
    "render_conversation_resume_hint",
    "write_clean_exit_resume_hint",
]
