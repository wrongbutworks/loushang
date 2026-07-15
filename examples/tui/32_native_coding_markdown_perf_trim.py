from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, TextIO, cast

from loushang.tui import (
    FakeTerminalPort,
    RenderConstraints,
    RenderLoop,
    TerminalSize,
    TuiRuntime,
)

_PERF31_PATH = Path(__file__).with_name("31_native_coding_markdown_perf.py")


def _load_perf31() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_native_coding_markdown_perf31", _PERF31_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_PERF31_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_perf31 = _load_perf31()


async def run_script(
    *,
    stdout: TextIO,
    count: int,
    rounds: int,
    width: int,
    height: int,
    stream_seconds: float,
    render_interval_ms: int,
    active_line_budget: int,
    trace_memory: bool,
    show_final: bool,
) -> int:
    if trace_memory and not _perf31.tracemalloc.is_tracing():
        _perf31.tracemalloc.start()
    app = _perf31.PerfScreenCodingTuiApp(
        model_label="fake-model",
        cwd="/repo",
        branch="markdown-perf-trim",
        session_label="script",
    )
    app.active_transcript_line_budget = active_line_budget
    app.set_status("scripted fake render with trim")
    terminal = FakeTerminalPort(
        size=TerminalSize(columns=width, rows=height),
        flush_history_limit=1,
        frame_history_limit=1,
    )
    runtime = TuiRuntime(render_loop=RenderLoop(app), terminal=terminal)
    stdout.write("Native coding markdown perf trim script\n")
    stdout.write(f"requested_markdown_lines={count}\n")
    stdout.write(f"rounds={rounds}\n")
    stdout.write(f"stream_seconds={stream_seconds:.3f}\n")
    stdout.write(f"active_line_budget={active_line_budget}\n\n")

    for round_index in range(1, rounds + 1):
        summary = await _perf31._drive_script_round(
            app=app,
            runtime=runtime,
            count=count,
            stream_seconds=stream_seconds,
            render_interval_ms=render_interval_ms,
        )
        stdout.write(_perf31._script_round_line(round_index, app=app, summary=summary))
        trim_step, trim_changed = _trim_and_render(app=app, runtime=runtime)
        stdout.write(
            _trim_round_line(
                round_index, app=app, trim_step=trim_step, trim_changed=trim_changed
            )
        )

    if show_final:
        final = app.render(
            RenderConstraints(width=width, max_height=height, visible_height=height)
        )
        stdout.write("\n")
        stdout.write(f"rendered_line_count={len(final.lines)}\n")
        for line in final.lines:
            stdout.write(_perf31.strip_control_sequences(line.text) + "\n")
    return 0


def _trim_and_render(*, app: Any, runtime: TuiRuntime) -> tuple[Any, bool]:
    before_generation = app.state.transcript_window_generation
    before_evicted = app.state.evicted_prefix_record_count
    app.trim_active_transcript_window()
    step = runtime.render_now()
    trim_changed = (
        app.state.transcript_window_generation != before_generation
        or app.state.evicted_prefix_record_count != before_evicted
    )
    return step, trim_changed


def _trim_round_line(
    round_index: int, *, app: Any, trim_step: Any, trim_changed: bool
) -> str:
    diagnostics = trim_step.diagnostics
    current_lines = diagnostics.current_logical_lines
    previous_lines = diagnostics.previous_rendered_lines
    active_stats = _perf31._active_state_stats(app)
    cache_stats = _perf31._transcript_cache_stats(app)
    return (
        f"trim_round={round_index} "
        f"trim_changed={str(trim_changed).lower()} "
        f"trim_operation_class={diagnostics.operation_class} "
        f"trim_repaint_reason={diagnostics.repaint_reason or 'none'} "
        f"post_trim_records={len(app.state.records)} "
        f"post_trim_lines={len(current_lines)} "
        f"post_trim_line_chars={sum(len(line) for line in current_lines)} "
        f"post_trim_previous_lines={len(previous_lines)} "
        f"post_trim_previous_chars={sum(len(line) for line in previous_lines)} "
        f"post_trim_viewport_top={diagnostics.viewport_top} "
        f"post_trim_changed_range={_perf31._format_range(diagnostics.changed_line_range)} "
        f"post_trim_evicted_prefix_records={app.state.evicted_prefix_record_count} "
        f"post_trim_generation={app.state.transcript_window_generation} "
        f"post_trim_active_text_chars={active_stats['active_text_chars']} "
        f"post_trim_stable_cache_entries={cache_stats['stable_cache_entries']} "
        f"post_trim_stable_cache_lines={cache_stats['stable_cache_lines']} "
        f"post_trim_stable_cache_chars={cache_stats['stable_cache_chars']}\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scripted fake-model Markdown performance harness with per-round active transcript trimming."
    )
    parser.add_argument(
        "--script-count",
        type=int,
        required=True,
        help="run fake prompts with this line count",
    )
    parser.add_argument(
        "--script-rounds",
        type=int,
        default=1,
        help="number of scripted fake prompts to run",
    )
    parser.add_argument(
        "--active-line-budget",
        type=int,
        default=320,
        help="active transcript line budget applied after every round",
    )
    parser.add_argument(
        "--show-final",
        action="store_true",
        help="print the final rendered snapshot after script stats",
    )
    parser.add_argument(
        "--stream-seconds",
        type=float,
        default=cast(float, _perf31.DEFAULT_STREAM_SECONDS),
        help="target fake stream duration",
    )
    parser.add_argument(
        "--script-render-interval-ms",
        type=int,
        default=80,
        help="script render coalescing interval; use 0 to render every chunk",
    )
    parser.add_argument(
        "--trace-memory",
        action="store_true",
        help="enable tracemalloc current/peak memory stats",
    )
    parser.add_argument("--width", type=int, default=100, help="script snapshot width")
    parser.add_argument("--height", type=int, default=32, help="script snapshot height")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(
        run_script(
            stdout=sys.stdout,
            count=max(1, args.script_count),
            rounds=max(1, args.script_rounds),
            width=args.width,
            height=args.height,
            stream_seconds=max(0.05, args.stream_seconds),
            render_interval_ms=args.script_render_interval_ms,
            active_line_budget=max(1, args.active_line_budget),
            trace_memory=args.trace_memory,
            show_final=args.show_final,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
