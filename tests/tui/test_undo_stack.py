from __future__ import annotations

import pytest

from loushang.tui.undo_stack import UndoStack


def test_undo_stack_push_pop_and_clear() -> None:
    stack: UndoStack[tuple[str, int]] = UndoStack()

    assert not stack
    assert len(stack) == 0
    assert stack.pop() is None

    stack.push(("a", 1))
    stack.push(("b", 2))

    assert stack
    assert len(stack) == 2
    assert stack.pop() == ("b", 2)
    assert stack.pop() == ("a", 1)
    assert stack.pop() is None

    stack.push(("c", 3))
    stack.clear()

    assert not stack
    assert len(stack) == 0


def test_undo_stack_max_depth_drops_oldest_snapshots() -> None:
    stack: UndoStack[int] = UndoStack(max_depth=3)

    for value in range(5):
        stack.push(value)

    assert len(stack) == 3
    assert stack.pop() == 4
    assert stack.pop() == 3
    assert stack.pop() == 2
    assert stack.pop() is None


def test_undo_stack_max_depth_must_be_positive_when_set() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        UndoStack(max_depth=0)

    with pytest.raises(ValueError, match="max_depth"):
        UndoStack(max_depth=-1)
