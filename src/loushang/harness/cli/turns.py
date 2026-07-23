"""Reusable execution of prepared Product turns through keyword-based hosts."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeAlias

CliKeywordRunner: TypeAlias = Callable[..., int | Awaitable[int]]
CliTurnBatchRunner: TypeAlias = Callable[..., Awaitable[int]]
_LIFECYCLE_ARGUMENTS = frozenset(
    {"images", "follow_up_messages", "dispose"}
)


@dataclass(frozen=True, slots=True)
class CliPreparedTurn:
    """One Product-prepared turn and its explicit runner arguments."""

    input_text: str
    arguments: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        conflicts = _LIFECYCLE_ARGUMENTS.intersection(self.arguments)
        if conflicts:
            raise ValueError(
                "prepared turn arguments cannot replace lifecycle values: "
                f"{sorted(conflicts)!r}"
            )


async def run_keyword_cli_turns(
    turns: Sequence[CliPreparedTurn],
    *,
    run_turns: CliTurnBatchRunner,
    runner: CliKeywordRunner,
    input_argument: str,
    fixed_arguments: Mapping[str, object],
    images: object | None = None,
    follow_up_messages: Sequence[str] = (),
    dispose_candidates: Sequence[object] = (),
) -> int:
    """Run prepared turns while applying first/last lifecycle values once."""

    if not input_argument or input_argument in _LIFECYCLE_ARGUMENTS:
        raise ValueError("input argument must be a non-lifecycle keyword")
    if input_argument in fixed_arguments:
        raise ValueError("fixed arguments cannot replace the turn input")
    conflicts = _LIFECYCLE_ARGUMENTS.intersection(fixed_arguments)
    if conflicts:
        raise ValueError(
            "fixed arguments cannot replace lifecycle values: "
            f"{sorted(conflicts)!r}"
        )

    async def invoke(
        turn: CliPreparedTurn,
        is_first_turn: bool,
        is_last_turn: bool,
    ) -> int:
        arguments = {
            **fixed_arguments,
            input_argument: turn.input_text,
            **turn.arguments,
            "images": images if is_first_turn else None,
            "follow_up_messages": tuple(follow_up_messages)
            if is_last_turn
            else (),
            "dispose": is_last_turn,
        }
        result = runner(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    return await run_turns(
        tuple(turns),
        run_turn=invoke,
        dispose_candidates=tuple(dispose_candidates),
    )


__all__ = [
    "CliKeywordRunner",
    "CliPreparedTurn",
    "CliTurnBatchRunner",
    "run_keyword_cli_turns",
]
