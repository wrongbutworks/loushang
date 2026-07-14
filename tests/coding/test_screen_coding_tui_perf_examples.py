from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

from markdown_it import MarkdownIt

_EXAMPLE = (
    Path(__file__).parents[2] / "examples" / "tui" / "31_native_coding_markdown_perf.py"
)


def test_markdown_perf_fixture_starts_a_new_block_every_twenty_lines() -> None:
    namespace = runpy.run_path(str(_EXAMPLE))
    markdown_line = namespace["_markdown_line"]
    markdown = "".join(markdown_line(index) for index in range(1, 42))
    tokens = MarkdownIt("commonmark").parse(markdown)

    assert (
        sum(token.type == "heading_open" and token.level == 0 for token in tokens) == 3
    )
    assert (
        sum(token.type == "bullet_list_open" and token.level == 0 for token in tokens)
        == 3
    )


def test_markdown_perf_example_runs_against_screen_tui() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(_EXAMPLE),
            "--script-count",
            "4",
            "--stream-seconds",
            "0",
            "--script-render-interval-ms",
            "0",
            "--script-render-every-n-chunks",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "requested_lines=4" in completed.stdout
    assert "markdown_lines_per_block=20" in completed.stdout
    assert "render_every_n_chunks=2" in completed.stdout
