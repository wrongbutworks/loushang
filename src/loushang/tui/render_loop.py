from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar, Literal, Protocol

from loushang.tui.cell_width import normalize_terminal_output, visible_width
from loushang.tui.core import CursorDeclaration, RenderConstraints, RenderResult
from loushang.tui.playback import RenderDiagnostics
from loushang.tui.terminal import TerminalOperation, TerminalSize
from loushang.tui.terminal_image import (
    delete_kitty_image,
    extract_kitty_image_ids,
    is_terminal_image_line,
    wrap_tmux_passthrough,
)

ClearScrollbackPolicy = Literal["disabled", "resize", "explicit"]
SEGMENT_RESET = "\x1b[0m\x1b]8;;\x07"


class ScreenRoot(Protocol):
    def render(self, constraints: RenderConstraints) -> RenderResult: ...


class RenderPlanStrategyKind(Enum):
    FIRST_RENDER = auto()
    TRANSCRIPT_WINDOW_TRIMMED_RESET = auto()
    BASELINE_RESET = auto()
    RESIZE_REPAINT = auto()
    UNSAFE_VIEWPORT = auto()
    NO_CHANGE = auto()
    APPEND = auto()
    PROTECTED_APPEND = auto()
    SHRINK_VIEWPORT_REPAINT = auto()
    SHRINK_CLEAR = auto()
    CHANGED_ABOVE_VIEWPORT = auto()
    CHANGED_RANGE = auto()


DEFAULT_STRATEGY_ORDER: tuple[RenderPlanStrategyKind, ...] = (
    RenderPlanStrategyKind.FIRST_RENDER,
    RenderPlanStrategyKind.TRANSCRIPT_WINDOW_TRIMMED_RESET,
    RenderPlanStrategyKind.BASELINE_RESET,
    RenderPlanStrategyKind.RESIZE_REPAINT,
    RenderPlanStrategyKind.UNSAFE_VIEWPORT,
    RenderPlanStrategyKind.NO_CHANGE,
    RenderPlanStrategyKind.APPEND,
    RenderPlanStrategyKind.PROTECTED_APPEND,
    RenderPlanStrategyKind.SHRINK_VIEWPORT_REPAINT,
    RenderPlanStrategyKind.SHRINK_CLEAR,
    RenderPlanStrategyKind.CHANGED_ABOVE_VIEWPORT,
    RenderPlanStrategyKind.CHANGED_RANGE,
)


@dataclass(frozen=True, slots=True)
class RenderPlanContext:
    size: TerminalSize
    result: RenderResult
    raw_current_lines: tuple[str, ...]
    current_lines: tuple[str, ...]
    previous_lines: tuple[str, ...]
    previous_size: TerminalSize | None
    declared_cursor: CursorDeclaration | None
    cursor: CursorDeclaration
    changed_range: tuple[int, int] | None
    first_changed: int | None
    last_changed: int | None
    appended_lines: int
    append_start: int | None
    viewport_top: int
    differential_viewport_top: int
    width_changed: bool
    height_changed: bool
    previous_kitty_delete_sequences: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderPlanRuntime:
    previous_viewport_top: int
    previous_cursor_row: int
    previous_cursor_column: int
    hardware_cursor_row: int
    hardware_cursor_column: int
    working_area_high_water_mark: int
    termux_session: bool
    clear_scrollback_policy: ClearScrollbackPolicy
    baseline_reset_reason: str | None
    unsafe_viewport_reason: str | None
    diagnostics: Callable[..., RenderDiagnostics]
    repaint_diagnostics: Callable[..., RenderDiagnostics]


class RenderPlanStrategy(Protocol):
    kind: ClassVar[RenderPlanStrategyKind]
    name: ClassVar[str]

    def match(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> bool: ...

    def plan(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> RenderDiagnostics: ...


@dataclass(frozen=True, slots=True)
class FirstRenderStrategy:
    kind: ClassVar[RenderPlanStrategyKind] = RenderPlanStrategyKind.FIRST_RENDER
    name: ClassVar[str] = "first_render"

    def match(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> bool:
        return context.previous_size is None

    def plan(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> RenderDiagnostics:
        return runtime.diagnostics(
            current_lines=context.current_lines,
            previous_lines=context.previous_lines,
            size=context.size,
            operation_class="first_render",
            operations=_full_write_operations(
                context.current_lines,
                cursor=context.declared_cursor,
                viewport_top=context.viewport_top,
            ),
            changed_range=context.changed_range,
            viewport_top=context.viewport_top,
            cursor=context.cursor,
            hardware_cursor_row=_hardware_row_after_write(context.current_lines, cursor=context.declared_cursor),
            hardware_cursor_column=context.cursor.column,
        )


@dataclass(frozen=True, slots=True)
class ResizeRepaintStrategy:
    kind: ClassVar[RenderPlanStrategyKind] = RenderPlanStrategyKind.RESIZE_REPAINT
    name: ClassVar[str] = "resize_repaint"

    def match(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> bool:
        return context.width_changed or (context.height_changed and not runtime.termux_session)

    def plan(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> RenderDiagnostics:
        return runtime.repaint_diagnostics(
            current_lines=context.current_lines,
            previous_lines=context.previous_lines,
            size=context.size,
            changed_range=context.changed_range,
            cursor=context.cursor,
            declared_cursor=context.declared_cursor,
            operation_class="resize_repaint",
            repaint_kind="resize",
            repaint_reason="terminal_size_changed",
            width_changed=context.width_changed,
            height_changed=context.height_changed,
            delete_kitty_image_sequences=context.previous_kitty_delete_sequences,
        )


@dataclass(frozen=True, slots=True)
class UnsafeViewportStrategy:
    kind: ClassVar[RenderPlanStrategyKind] = RenderPlanStrategyKind.UNSAFE_VIEWPORT
    name: ClassVar[str] = "unsafe_viewport"

    def match(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> bool:
        return runtime.unsafe_viewport_reason is not None

    def plan(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> RenderDiagnostics:
        if runtime.unsafe_viewport_reason is None:
            raise AssertionError("unsafe viewport strategy planned without a reason")
        return runtime.repaint_diagnostics(
            current_lines=context.current_lines,
            previous_lines=context.previous_lines,
            size=context.size,
            changed_range=context.changed_range,
            cursor=context.cursor,
            declared_cursor=context.declared_cursor,
            operation_class="recovery_repaint",
            repaint_kind="recovery",
            repaint_reason=runtime.unsafe_viewport_reason,
            delete_kitty_image_sequences=context.previous_kitty_delete_sequences,
        )


@dataclass(frozen=True, slots=True)
class NoChangeStrategy:
    kind: ClassVar[RenderPlanStrategyKind] = RenderPlanStrategyKind.NO_CHANGE
    name: ClassVar[str] = "no_change"

    def match(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> bool:
        return context.changed_range is None

    def plan(self, context: RenderPlanContext, *, runtime: RenderPlanRuntime) -> RenderDiagnostics:
        if (context.cursor.row, context.cursor.column) != (
            runtime.previous_cursor_row,
            runtime.previous_cursor_column,
        ):
            return runtime.diagnostics(
                current_lines=context.current_lines,
                previous_lines=context.previous_lines,
                size=context.size,
                operation_class="cursor_update",
                operations=_cursor_update_operations(
                    context.cursor,
                    viewport_top=context.viewport_top,
                    hardware_cursor_row=runtime.hardware_cursor_row,
                ),
                viewport_top=context.viewport_top,
                width_changed=context.width_changed,
                height_changed=context.height_changed,
                cursor=context.cursor,
                hardware_cursor_row=context.cursor.row,
                hardware_cursor_column=context.cursor.column,
            )
        return runtime.diagnostics(
            current_lines=context.current_lines,
            previous_lines=context.previous_lines,
            size=context.size,
            operation_class="noop",
            operations=(),
            viewport_top=context.viewport_top,
            width_changed=context.width_changed,
            height_changed=context.height_changed,
            cursor=context.cursor,
            hardware_cursor_row=runtime.hardware_cursor_row,
            hardware_cursor_column=runtime.hardware_cursor_column,
        )


FIRST_RENDER_STRATEGY = FirstRenderStrategy()
POST_BASELINE_SIMPLE_STRATEGIES: tuple[RenderPlanStrategy, ...] = (
    ResizeRepaintStrategy(),
    UnsafeViewportStrategy(),
    NoChangeStrategy(),
)


@dataclass(slots=True)
class RenderLoop:
    screen_root: ScreenRoot
    clear_scrollback_policy: ClearScrollbackPolicy = "resize"
    termux_session: bool = False
    previous_rendered_lines: tuple[str, ...] = ()
    previous_raw_lines: tuple[str, ...] = ()
    previous_size: TerminalSize | None = None
    previous_viewport_top: int = 0
    hardware_cursor_row: int = 0
    hardware_cursor_column: int = 0
    working_area_high_water_mark: int = 0
    previous_cursor_row: int = 0
    previous_cursor_column: int = 0
    _unsafe_viewport_reason: str | None = None
    _baseline_reset_reason: str | None = None
    _planned_raw_lines: tuple[str, ...] = ()

    def mark_viewport_unsafe(self, reason: str) -> None:
        self._unsafe_viewport_reason = reason

    def reset_baseline(self, reason: str = "baseline_reset") -> None:
        self._baseline_reset_reason = reason

    def _build_plan_context(self, size: TerminalSize) -> RenderPlanContext:
        result = self.screen_root.render(
            RenderConstraints(width=size.columns, max_height=1_000_000, visible_height=size.rows)
        )
        raw_current_lines = tuple(line.text for line in result.lines)
        self._planned_raw_lines = raw_current_lines
        current_lines = _finalize_rendered_lines(
            raw_current_lines,
            previous_raw_lines=self.previous_raw_lines,
            previous_finalized_lines=self.previous_rendered_lines,
        )
        cursor = _cursor_or_line_end(result.cursor, current_lines)
        previous_lines = self.previous_rendered_lines
        previous_size = self.previous_size
        width_changed = previous_size is not None and previous_size.columns != size.columns
        height_changed = previous_size is not None and previous_size.rows != size.rows
        changed_range = _expand_changed_range_for_kitty_images(
            previous_lines,
            _changed_line_range(previous_lines, current_lines),
        )
        first_changed: int | None = None
        last_changed: int | None = None
        appended_lines = max(0, len(current_lines) - len(previous_lines))
        append_start: int | None = None
        if changed_range is not None:
            first_changed, last_changed = changed_range
            append_start = (
                first_changed
                if appended_lines > 0 and first_changed == len(previous_lines) and first_changed > 0
                else None
            )
        viewport_top = _viewport_top(current_lines, size)
        differential_viewport_top = _differential_viewport_top(
            previous_viewport_top=self.previous_viewport_top,
            natural_viewport_top=viewport_top,
            previous_line_count=len(previous_lines),
            current_line_count=len(current_lines),
        )
        previous_kitty_delete_sequences = _kitty_delete_sequences(previous_lines)
        return RenderPlanContext(
            size=size,
            result=result,
            raw_current_lines=raw_current_lines,
            current_lines=current_lines,
            previous_lines=previous_lines,
            previous_size=previous_size,
            declared_cursor=result.cursor,
            cursor=cursor,
            changed_range=changed_range,
            first_changed=first_changed,
            last_changed=last_changed,
            appended_lines=appended_lines,
            append_start=append_start,
            viewport_top=viewport_top,
            differential_viewport_top=differential_viewport_top,
            width_changed=width_changed,
            height_changed=height_changed,
            previous_kitty_delete_sequences=previous_kitty_delete_sequences,
        )

    def _plan_runtime(self) -> RenderPlanRuntime:
        return RenderPlanRuntime(
            previous_viewport_top=self.previous_viewport_top,
            previous_cursor_row=self.previous_cursor_row,
            previous_cursor_column=self.previous_cursor_column,
            hardware_cursor_row=self.hardware_cursor_row,
            hardware_cursor_column=self.hardware_cursor_column,
            working_area_high_water_mark=self.working_area_high_water_mark,
            termux_session=self.termux_session,
            clear_scrollback_policy=self.clear_scrollback_policy,
            baseline_reset_reason=self._baseline_reset_reason,
            unsafe_viewport_reason=self._unsafe_viewport_reason,
            diagnostics=self._diagnostics,
            repaint_diagnostics=self._repaint_diagnostics,
        )

    def plan(self, size: TerminalSize) -> RenderDiagnostics:
        context = self._build_plan_context(size)
        runtime = self._plan_runtime()
        result = context.result
        current_lines = context.current_lines
        cursor = context.cursor
        previous_lines = context.previous_lines
        changed_range = context.changed_range
        viewport_top = context.viewport_top
        previous_kitty_delete_sequences = context.previous_kitty_delete_sequences

        if FIRST_RENDER_STRATEGY.match(context, runtime=runtime):
            return FIRST_RENDER_STRATEGY.plan(context, runtime=runtime)

        if self._baseline_reset_reason is not None:
            if self._baseline_reset_reason.startswith("transcript_window_trimmed:"):
                return self._managed_viewport_repaint_diagnostics(
                    current_lines=current_lines,
                    previous_lines=previous_lines,
                    size=size,
                    changed_range=changed_range,
                    cursor=cursor,
                    declared_cursor=result.cursor,
                    repaint_reason=self._baseline_reset_reason,
                    delete_kitty_image_sequences=previous_kitty_delete_sequences,
                )
            return self._repaint_diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                changed_range=changed_range,
                cursor=cursor,
                declared_cursor=result.cursor,
                operation_class="baseline_repaint",
                repaint_kind="recovery",
                repaint_reason=self._baseline_reset_reason,
                delete_kitty_image_sequences=previous_kitty_delete_sequences,
            )

        for strategy in POST_BASELINE_SIMPLE_STRATEGIES:
            if strategy.match(context, runtime=runtime):
                return strategy.plan(context, runtime=runtime)

        first_changed = context.first_changed
        last_changed = context.last_changed
        appended_lines = context.appended_lines
        append_start = context.append_start
        if first_changed is None or last_changed is None:
            raise AssertionError("changed range facts missing for changed render plan")
        if append_start is not None:
            return self._diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                operation_class="append_update",
                operations=_append_operations(
                    current_lines[append_start:],
                    append_start=append_start,
                    hardware_cursor_row=self.hardware_cursor_row,
                    cursor=result.cursor,
                    viewport_top=viewport_top,
                ),
                changed_range=changed_range,
                viewport_top=viewport_top,
                append_start=append_start,
                appended_lines=appended_lines,
                render_end=last_changed,
                cursor=cursor,
                hardware_cursor_row=_hardware_row_after_write(current_lines, cursor=result.cursor),
                hardware_cursor_column=cursor.column,
            )

        protected_append = _protected_append_plan(
            current_lines=current_lines,
            previous_lines=previous_lines,
            first_changed=first_changed,
            appended_lines=appended_lines,
            cursor=result.cursor,
            size=size,
        )
        if protected_append is not None:
            inserted_start, inserted_end, protected_start = protected_append
            return self._diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                operation_class="protected_append_update",
                operations=_protected_append_operations(
                    current_lines=current_lines,
                    inserted_range=(inserted_start, inserted_end),
                    protected_start=protected_start,
                    cursor=result.cursor,
                    viewport_top=viewport_top,
                    size=size,
                    delete_kitty_image_sequences=_kitty_delete_sequences(previous_lines[inserted_start:]),
                ),
                changed_range=changed_range,
                viewport_top=viewport_top,
                append_start=inserted_start,
                appended_lines=appended_lines,
                render_end=len(current_lines) - 1,
                cursor=cursor,
                hardware_cursor_row=cursor.row,
                hardware_cursor_column=cursor.column,
            )

        differential_viewport_top = context.differential_viewport_top
        if len(current_lines) < len(previous_lines) and viewport_top < self.previous_viewport_top:
            return self._managed_viewport_repaint_diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                changed_range=changed_range,
                cursor=cursor,
                declared_cursor=result.cursor,
                repaint_reason="viewport_top_decreased_after_shrink",
                delete_kitty_image_sequences=previous_kitty_delete_sequences,
            )

        if first_changed >= len(current_lines) and len(previous_lines) > len(current_lines):
            target_row = max(0, len(current_lines) - 1)
            return self._diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                operation_class="shrink_clear",
                operations=_shrink_clear_operations(
                    previous_lines=previous_lines,
                    current_lines=current_lines,
                    target_row=target_row,
                    hardware_cursor_row=self.hardware_cursor_row,
                    delete_kitty_image_sequences=_kitty_delete_sequences_in_range(previous_lines, first_changed, last_changed),
                ),
                changed_range=changed_range,
                viewport_top=differential_viewport_top,
                render_end=target_row,
                cursor=cursor,
                hardware_cursor_row=target_row,
                hardware_cursor_column=cursor.column,
            )

        if first_changed < self.previous_viewport_top:
            return self._managed_viewport_repaint_diagnostics(
                current_lines=current_lines,
                previous_lines=previous_lines,
                size=size,
                changed_range=changed_range,
                cursor=cursor,
                declared_cursor=result.cursor,
                repaint_reason="changed_range_above_viewport",
                delete_kitty_image_sequences=previous_kitty_delete_sequences,
            )

        render_end = min(last_changed, len(current_lines) - 1)
        hardware_cursor_row, hardware_cursor_column = _changed_range_hardware_cursor(
            current_lines=current_lines,
            previous_lines=previous_lines,
            render_end=render_end,
            declared_cursor=result.cursor,
            size=size,
        )
        return self._diagnostics(
            current_lines=current_lines,
            previous_lines=previous_lines,
            size=size,
            operation_class="changed_range_update",
            operations=_changed_range_operations(
                current_lines=current_lines,
                previous_lines=previous_lines,
                changed_range=changed_range,
                previous_viewport_top=self.previous_viewport_top,
                hardware_cursor_row=self.hardware_cursor_row,
                cursor=result.cursor,
                viewport_top=differential_viewport_top,
                delete_kitty_image_sequences=_kitty_delete_sequences_in_range(previous_lines, first_changed, last_changed),
            ),
            changed_range=changed_range,
            viewport_top=differential_viewport_top,
            render_end=render_end,
            cursor=cursor,
            hardware_cursor_row=hardware_cursor_row,
            hardware_cursor_column=hardware_cursor_column,
        )

    def _managed_viewport_repaint_diagnostics(
        self,
        *,
        current_lines: tuple[str, ...],
        previous_lines: tuple[str, ...],
        size: TerminalSize,
        changed_range: tuple[int, int] | None,
        cursor: CursorDeclaration,
        declared_cursor: CursorDeclaration | None,
        repaint_reason: str,
        delete_kitty_image_sequences: tuple[str, ...] = (),
    ) -> RenderDiagnostics:
        viewport_top = _viewport_top(current_lines, size)
        return self._diagnostics(
            current_lines=current_lines,
            previous_lines=previous_lines,
            size=size,
            operation_class="managed_viewport_repaint",
            operations=_managed_viewport_repaint_operations(
                current_lines,
                cursor=declared_cursor,
                viewport_top=viewport_top,
                size=size,
                hardware_cursor_row=self.hardware_cursor_row,
                delete_kitty_image_sequences=delete_kitty_image_sequences,
            ),
            changed_range=changed_range,
            viewport_top=viewport_top,
            repaint_kind="recovery",
            repaint_reason=repaint_reason,
            cursor=cursor,
            hardware_cursor_row=_hardware_row_after_write(current_lines, cursor=declared_cursor),
            hardware_cursor_column=cursor.column,
        )

    def commit(self, diagnostics: RenderDiagnostics, *, size: TerminalSize) -> None:
        self.previous_rendered_lines = diagnostics.current_logical_lines
        self.previous_raw_lines = self._planned_raw_lines
        self.previous_size = size
        self.previous_viewport_top = diagnostics.viewport_top
        self.hardware_cursor_row = diagnostics.hardware_cursor_row
        self.hardware_cursor_column = diagnostics.hardware_cursor_column
        self.previous_cursor_row = diagnostics.logical_cursor_row
        self.previous_cursor_column = diagnostics.logical_cursor_column
        self.working_area_high_water_mark = max(
            self.working_area_high_water_mark, len(diagnostics.current_logical_lines)
        )
        self._unsafe_viewport_reason = None
        self._baseline_reset_reason = None

    def _repaint_diagnostics(
        self,
        *,
        current_lines: tuple[str, ...],
        previous_lines: tuple[str, ...],
        size: TerminalSize,
        changed_range: tuple[int, int] | None,
        cursor: CursorDeclaration,
        declared_cursor: CursorDeclaration | None = None,
        operation_class: str,
        repaint_kind: str,
        repaint_reason: str,
        width_changed: bool = False,
        height_changed: bool = False,
        delete_kitty_image_sequences: tuple[str, ...] = (),
    ) -> RenderDiagnostics:
        return self._diagnostics(
            current_lines=current_lines,
            previous_lines=previous_lines,
            size=size,
            operation_class=operation_class,
            operations=_repaint_operations(
                current_lines,
                clear_scrollback=_should_clear_scrollback(
                    policy=self.clear_scrollback_policy,
                    repaint_kind=repaint_kind,
                ),
                cursor=declared_cursor,
                viewport_top=_viewport_top(current_lines, size),
                delete_kitty_image_sequences=delete_kitty_image_sequences,
            ),
            changed_range=changed_range,
            viewport_top=_viewport_top(current_lines, size),
            repaint_kind=repaint_kind,
            repaint_reason=repaint_reason,
            width_changed=width_changed,
            height_changed=height_changed,
            cursor=cursor,
            hardware_cursor_row=_hardware_row_after_write(current_lines, cursor=declared_cursor),
            hardware_cursor_column=cursor.column,
        )

    def _diagnostics(
        self,
        *,
        current_lines: tuple[str, ...],
        previous_lines: tuple[str, ...],
        size: TerminalSize,
        operation_class: str,
        operations: tuple[TerminalOperation, ...],
        changed_range: tuple[int, int] | None = None,
        viewport_top: int = 0,
        append_start: int | None = None,
        appended_lines: int = 0,
        render_end: int | None = None,
        repaint_kind: str | None = None,
        repaint_reason: str | None = None,
        width_changed: bool = False,
        height_changed: bool = False,
        cursor: CursorDeclaration | None = None,
        hardware_cursor_row: int | None = None,
        hardware_cursor_column: int | None = None,
    ) -> RenderDiagnostics:
        clear_scrollback_emitted = any(operation.kind == "clear_scrollback" for operation in operations)
        logical_cursor = cursor if cursor is not None else _cursor_or_line_end(None, current_lines)
        terminal_cursor_row = logical_cursor.row if hardware_cursor_row is None else hardware_cursor_row
        terminal_cursor_column = logical_cursor.column if hardware_cursor_column is None else hardware_cursor_column
        return RenderDiagnostics(
            current_logical_lines=current_lines,
            previous_rendered_lines=previous_lines,
            changed_line_range=changed_range,
            operation_class=operation_class,
            append_start=append_start,
            appended_lines=appended_lines,
            render_end=render_end,
            viewport_top=viewport_top,
            previous_viewport_top=self.previous_viewport_top,
            logical_cursor_row=logical_cursor.row,
            logical_cursor_column=logical_cursor.column,
            hardware_cursor_row=terminal_cursor_row,
            hardware_cursor_column=terminal_cursor_column,
            working_area_high_water_mark=max(self.working_area_high_water_mark, len(current_lines)),
            width_changed=width_changed,
            height_changed=height_changed,
            operations=operations,
            repaint_kind=repaint_kind,
            repaint_reason=repaint_reason,
            clear_scrollback_policy=self.clear_scrollback_policy,
            clear_scrollback_emitted=clear_scrollback_emitted,
        )


def _changed_line_range(previous_lines: tuple[str, ...], current_lines: tuple[str, ...]) -> tuple[int, int] | None:
    first_changed = -1
    last_changed = -1
    for index in range(max(len(previous_lines), len(current_lines))):
        old_line = previous_lines[index] if index < len(previous_lines) else ""
        new_line = current_lines[index] if index < len(current_lines) else ""
        if old_line == new_line:
            continue
        if first_changed == -1:
            first_changed = index
        last_changed = index
    if first_changed == -1:
        return None
    return first_changed, last_changed


def _expand_changed_range_for_kitty_images(
    previous_lines: tuple[str, ...],
    changed_range: tuple[int, int] | None,
) -> tuple[int, int] | None:
    if changed_range is None:
        return None
    first_changed, last_changed = changed_range
    for index in range(first_changed, len(previous_lines)):
        if extract_kitty_image_ids(previous_lines[index]):
            last_changed = max(last_changed, index)
    return first_changed, last_changed


def _kitty_delete_sequences(lines: tuple[str, ...]) -> tuple[str, ...]:
    deletes: list[str] = []
    seen: set[int] = set()
    for line in lines:
        tmux_passthrough = _line_uses_tmux_passthrough(line)
        for image_id in extract_kitty_image_ids(line):
            if image_id in seen:
                continue
            seen.add(image_id)
            delete_sequence = delete_kitty_image(image_id)
            if tmux_passthrough:
                delete_sequence = wrap_tmux_passthrough(delete_sequence)
            deletes.append(delete_sequence)
    return tuple(deletes)


def _kitty_delete_sequences_in_range(lines: tuple[str, ...], first: int, last: int) -> tuple[str, ...]:
    if last < first or first >= len(lines):
        return ()
    return _kitty_delete_sequences(lines[max(0, first) : min(last + 1, len(lines))])


def _kitty_delete_operations(delete_sequences: tuple[str, ...]) -> tuple[TerminalOperation, ...]:
    return tuple(TerminalOperation.write(sequence) for sequence in delete_sequences)


def _line_uses_tmux_passthrough(line: str) -> bool:
    return "\x1bPtmux;" in line


def _finalize_rendered_lines(
    lines: tuple[str, ...],
    *,
    previous_raw_lines: tuple[str, ...] = (),
    previous_finalized_lines: tuple[str, ...] = (),
) -> tuple[str, ...]:
    finalized: list[str] = []
    reusable_count = min(len(lines), len(previous_raw_lines), len(previous_finalized_lines))
    for index, line in enumerate(lines):
        if index < reusable_count and line == previous_raw_lines[index]:
            finalized.append(previous_finalized_lines[index])
            continue
        finalized.append(_finalize_rendered_line(line))
    return tuple(finalized)


def _finalize_rendered_line(line: str) -> str:
    if is_terminal_image_line(line):
        return line
    normalized = normalize_terminal_output(line)
    if "\x1b" not in normalized:
        return normalized
    if normalized.endswith(SEGMENT_RESET):
        return normalized
    return normalized + SEGMENT_RESET


def _viewport_top(lines: tuple[str, ...], size: TerminalSize) -> int:
    return max(0, len(lines) - size.rows)


def _differential_viewport_top(
    *,
    previous_viewport_top: int,
    natural_viewport_top: int,
    previous_line_count: int,
    current_line_count: int,
) -> int:
    if current_line_count < previous_line_count:
        return max(previous_viewport_top, natural_viewport_top)
    return natural_viewport_top


def _full_write_operations(
    lines: tuple[str, ...], *, cursor: CursorDeclaration | None, viewport_top: int
) -> tuple[TerminalOperation, ...]:
    return _render_then_position_cursor(
        _write_lines(lines),
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=max(0, len(lines) - 1),
    )


def _repaint_operations(
    lines: tuple[str, ...],
    *,
    clear_scrollback: bool,
    cursor: CursorDeclaration | None,
    viewport_top: int,
    delete_kitty_image_sequences: tuple[str, ...] = (),
) -> tuple[TerminalOperation, ...]:
    operations: list[TerminalOperation] = [
        *_kitty_delete_operations(delete_kitty_image_sequences),
        TerminalOperation.clear_screen(),
    ]
    if clear_scrollback:
        operations.append(TerminalOperation.clear_scrollback())
    operations.extend(_write_lines(lines))
    return _render_then_position_cursor(
        tuple(operations),
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=max(0, len(lines) - 1),
    )


def _managed_viewport_repaint_operations(
    lines: tuple[str, ...],
    *,
    cursor: CursorDeclaration | None,
    viewport_top: int,
    size: TerminalSize,
    hardware_cursor_row: int,
    delete_kitty_image_sequences: tuple[str, ...] = (),
) -> tuple[TerminalOperation, ...]:
    visible_lines = lines[viewport_top : viewport_top + size.rows]
    operations: list[TerminalOperation] = list(_kitty_delete_operations(delete_kitty_image_sequences))
    line_delta = viewport_top - hardware_cursor_row
    if line_delta != 0:
        operations.append(TerminalOperation.move_relative(lines=line_delta))
    operations.append(TerminalOperation.carriage_return())
    for index in range(size.rows):
        if index > 0:
            operations.append(TerminalOperation.newline())
        operations.append(TerminalOperation.clear_line())
        if index < len(visible_lines):
            operations.append(TerminalOperation.write(visible_lines[index]))
    return _render_then_position_cursor(
        tuple(operations),
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=viewport_top + max(0, len(visible_lines) - 1),
    )


def _append_operations(
    lines: tuple[str, ...],
    *,
    append_start: int,
    hardware_cursor_row: int,
    cursor: CursorDeclaration | None,
    viewport_top: int,
) -> tuple[TerminalOperation, ...]:
    move_target_row = append_start - 1
    operations: list[TerminalOperation] = []
    line_delta = move_target_row - hardware_cursor_row
    if line_delta != 0:
        operations.append(TerminalOperation.move_relative(lines=line_delta))
    operations.append(TerminalOperation.newline())
    for index, line in enumerate(lines):
        if index > 0:
            operations.append(TerminalOperation.newline())
        operations.append(TerminalOperation.write(line))
    return _render_then_position_cursor(
        tuple(operations),
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=append_start + len(lines) - 1,
    )


def _protected_append_plan(
    *,
    current_lines: tuple[str, ...],
    previous_lines: tuple[str, ...],
    first_changed: int,
    appended_lines: int,
    cursor: CursorDeclaration | None,
    size: TerminalSize,
) -> tuple[int, int, int] | None:
    if cursor is None or appended_lines <= 0:
        return None
    if len(current_lines) < size.rows:
        return None
    inserted_start = first_changed
    inserted_end = inserted_start + appended_lines
    if inserted_start <= 0 or inserted_end >= len(current_lines):
        return None
    if inserted_start > len(previous_lines):
        return None
    protected_start = inserted_end
    protected_height = len(current_lines) - protected_start
    if protected_height <= 0 or protected_height >= size.rows:
        return None
    if cursor.row < protected_start:
        return None
    if previous_lines[:inserted_start] != current_lines[:inserted_start]:
        return None
    return inserted_start, inserted_end, protected_start


def _protected_append_operations(
    *,
    current_lines: tuple[str, ...],
    inserted_range: tuple[int, int],
    protected_start: int,
    cursor: CursorDeclaration | None,
    viewport_top: int,
    size: TerminalSize,
    delete_kitty_image_sequences: tuple[str, ...] = (),
) -> tuple[TerminalOperation, ...]:
    inserted_start, inserted_end = inserted_range
    inserted_lines = current_lines[inserted_start:inserted_end]
    protected_lines = current_lines[protected_start:]
    protected_height = len(protected_lines)
    scroll_bottom = max(0, size.rows - protected_height - 1)
    protected_screen_start = scroll_bottom + 1

    operations: list[TerminalOperation] = [
        TerminalOperation.hide_cursor(),
        TerminalOperation.begin_synchronized_update(),
        *_kitty_delete_operations(delete_kitty_image_sequences),
        TerminalOperation.set_scroll_region(top=0, bottom=scroll_bottom),
        TerminalOperation.move_cursor(row=scroll_bottom, column=0),
    ]
    for line in inserted_lines:
        operations.append(TerminalOperation.newline())
        operations.append(TerminalOperation.carriage_return())
        operations.append(TerminalOperation.clear_line())
        operations.append(TerminalOperation.write(line))
    operations.append(TerminalOperation.reset_scroll_region())
    for offset, line in enumerate(protected_lines):
        operations.append(TerminalOperation.move_cursor(row=protected_screen_start + offset, column=0))
        operations.append(TerminalOperation.clear_line())
        operations.append(TerminalOperation.write(line))
    operations.append(TerminalOperation.end_synchronized_update())
    if cursor is not None:
        operations.append(TerminalOperation.move_cursor(row=max(0, cursor.row - viewport_top), column=cursor.column))
        operations.append(TerminalOperation.show_cursor())
    return tuple(operations)


def _cursor_update_operations(
    cursor: CursorDeclaration,
    *,
    viewport_top: int,
    hardware_cursor_row: int,
) -> tuple[TerminalOperation, ...]:
    return _hide_position_and_show_cursor(
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=hardware_cursor_row,
    )


def _shrink_clear_operations(
    *,
    previous_lines: tuple[str, ...],
    current_lines: tuple[str, ...],
    target_row: int,
    hardware_cursor_row: int,
    delete_kitty_image_sequences: tuple[str, ...] = (),
) -> tuple[TerminalOperation, ...]:
    extra_lines = len(previous_lines) - len(current_lines)
    operations: list[TerminalOperation] = list(_kitty_delete_operations(delete_kitty_image_sequences))
    line_delta = target_row - hardware_cursor_row
    if line_delta != 0:
        operations.append(TerminalOperation.move_relative(lines=line_delta))
    operations.append(TerminalOperation.carriage_return())
    if extra_lines > 0:
        operations.append(TerminalOperation.newline())
    for index in range(extra_lines):
        operations.append(TerminalOperation.clear_line())
        if index < extra_lines - 1:
            operations.append(TerminalOperation.newline())
    if extra_lines > 0:
        operations.append(TerminalOperation.move_relative(lines=-extra_lines))
    return _wrap_synchronized(tuple(operations))


def _changed_range_operations(
    *,
    current_lines: tuple[str, ...],
    previous_lines: tuple[str, ...],
    changed_range: tuple[int, int],
    previous_viewport_top: int,
    hardware_cursor_row: int,
    cursor: CursorDeclaration | None,
    viewport_top: int,
    delete_kitty_image_sequences: tuple[str, ...] = (),
) -> tuple[TerminalOperation, ...]:
    first_changed, last_changed = changed_range
    line_delta = first_changed - hardware_cursor_row
    operations: list[TerminalOperation] = list(_kitty_delete_operations(delete_kitty_image_sequences))
    if line_delta != 0:
        operations.append(TerminalOperation.move_relative(lines=line_delta))
    operations.append(TerminalOperation.carriage_return())
    render_end = min(last_changed, len(current_lines) - 1)
    for line_index in range(first_changed, render_end + 1):
        if line_index > first_changed:
            operations.append(TerminalOperation.newline())
        operations.append(TerminalOperation.clear_line())
        operations.append(TerminalOperation.write(current_lines[line_index]))
    cleared_extra_lines = max(0, len(previous_lines) - len(current_lines))
    if len(previous_lines) > len(current_lines):
        for _ in range(cleared_extra_lines):
            operations.append(TerminalOperation.newline())
            operations.append(TerminalOperation.clear_line())
    return _render_then_position_cursor(
        tuple(operations),
        cursor=cursor,
        viewport_top=viewport_top,
        current_row=render_end + cleared_extra_lines,
    )


def _write_lines(lines: tuple[str, ...]) -> tuple[TerminalOperation, ...]:
    operations: list[TerminalOperation] = []
    for index, line in enumerate(lines):
        if index > 0:
            operations.append(TerminalOperation.newline())
        operations.append(TerminalOperation.write(line))
    return tuple(operations)


def _wrap_synchronized(operations: tuple[TerminalOperation, ...]) -> tuple[TerminalOperation, ...]:
    return (
        TerminalOperation.begin_synchronized_update(),
        *operations,
        TerminalOperation.end_synchronized_update(),
    )


def _render_then_position_cursor(
    operations: tuple[TerminalOperation, ...],
    *,
    cursor: CursorDeclaration | None,
    viewport_top: int,
    current_row: int,
) -> tuple[TerminalOperation, ...]:
    render_operations = _wrap_synchronized(operations)
    if cursor is None:
        return render_operations
    return (
        TerminalOperation.hide_cursor(),
        *render_operations,
        *_cursor_position_operations(cursor=cursor, viewport_top=viewport_top, current_row=current_row),
        TerminalOperation.show_cursor(),
    )


def _hide_position_and_show_cursor(
    *,
    cursor: CursorDeclaration,
    viewport_top: int,
    current_row: int,
) -> tuple[TerminalOperation, ...]:
    return (
        TerminalOperation.hide_cursor(),
        *_cursor_position_operations(cursor=cursor, viewport_top=viewport_top, current_row=current_row),
        TerminalOperation.show_cursor(),
    )


def _cursor_position_operations(
    *,
    cursor: CursorDeclaration,
    viewport_top: int,
    current_row: int,
) -> tuple[TerminalOperation, ...]:
    del viewport_top
    line_delta = cursor.row - current_row
    operations: list[TerminalOperation] = []
    if line_delta != 0:
        operations.append(TerminalOperation.move_relative(lines=line_delta))
    operations.append(TerminalOperation.move_column(column=cursor.column))
    return tuple(operations)


def _cursor_or_line_end(cursor: CursorDeclaration | None, lines: tuple[str, ...]) -> CursorDeclaration:
    if cursor is not None:
        return cursor
    row = max(0, len(lines) - 1)
    column = visible_width(lines[row]) if lines else 0
    return CursorDeclaration(row=row, column=column)


def _changed_range_hardware_cursor(
    *,
    current_lines: tuple[str, ...],
    previous_lines: tuple[str, ...],
    render_end: int,
    declared_cursor: CursorDeclaration | None,
    size: TerminalSize,
) -> tuple[int, int]:
    if declared_cursor is not None:
        return declared_cursor.row, declared_cursor.column
    cleared_extra_lines = max(0, len(previous_lines) - len(current_lines))
    if cleared_extra_lines:
        return render_end + cleared_extra_lines, 0
    if not current_lines:
        return 0, 0
    return render_end, min(visible_width(current_lines[render_end]), size.columns - 1)


def _should_clear_scrollback(*, policy: ClearScrollbackPolicy, repaint_kind: str) -> bool:
    if policy == "explicit":
        return True
    if policy == "resize":
        return repaint_kind == "resize"
    return False


def _hardware_row_after_write(lines: tuple[str, ...], *, cursor: CursorDeclaration | None) -> int:
    if cursor is not None:
        return cursor.row
    return max(0, len(lines) - 1)
