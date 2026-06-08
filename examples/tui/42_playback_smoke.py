from __future__ import annotations

import json
from pathlib import Path

from loushang.tui import (
    FakeTerminalPort,
    PlaybackEvent,
    PlaybackFrameBudget,
    PlaybackHarness,
    PlaybackResult,
    RenderDiagnostics,
    TerminalOperation,
    TerminalSize,
)


def main() -> int:
    state = {"text": "ready"}

    def render(
        event: PlaybackEvent,
        size: TerminalSize,
        previous: RenderDiagnostics | None,
    ) -> RenderDiagnostics:
        if event.kind == "input":
            state["text"] = f"input: {event.payload}"
        elif event.kind == "resize":
            state["text"] = f"resized to {size.columns}x{size.rows}"

        previous_lines = previous.current_logical_lines if previous is not None else ()
        line = state["text"][: size.columns]
        return RenderDiagnostics(
            current_logical_lines=(line,),
            previous_rendered_lines=previous_lines,
            changed_line_range=(0, 0),
            logical_cursor_row=0,
            logical_cursor_column=len(line),
            hardware_cursor_row=0,
            hardware_cursor_column=len(line),
            operations=(
                TerminalOperation.move_cursor(row=0, column=0),
                TerminalOperation.clear_line(),
                TerminalOperation.write(line),
            ),
        )

    port = FakeTerminalPort(size=TerminalSize(columns=40, rows=8))
    harness = PlaybackHarness(render=render, port=port)
    result = PlaybackResult(
        steps=harness.play(
            [
                PlaybackEvent("render"),
                PlaybackEvent.input("hello"),
                PlaybackEvent.resize(columns=32, rows=6),
            ]
        ),
        port=port,
    )

    PlaybackFrameBudget(max_operations=3).assert_result(result)

    artifacts = result.write_artifacts(
        Path("/tmp/loushang-public-playback-smoke"),
        basename="public-playback-smoke",
        include_frames=True,
    )
    print(
        json.dumps(
            {
                "visible": result.visible_text,
                "artifacts": [str(artifacts.trace), str(artifacts.screen)],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
