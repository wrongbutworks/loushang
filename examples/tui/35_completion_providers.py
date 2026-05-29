from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from loushang.tui import (
    CombinedCompletionProvider,
    Composer,
    CompletionItem,
    CompletionProvider,
    PathCompletionProvider,
    RenderConstraints,
)


@dataclass(frozen=True, slots=True)
class Scenario:
    title: str
    text: str
    force: bool = False


SCENARIOS = (
    Scenario("Slash command", "/h"),
    Scenario("At-file attachment", "@REA"),
    Scenario("Relative directory", "open ./s"),
    Scenario("Quoted path with spaces", 'attach @"notes folder/d'),
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="loushang-tui-completion-") as tmp:
        demo_root = Path(tmp)
        _write_demo_tree(demo_root)
        provider = CombinedCompletionProvider(
            (
                CompletionProvider(
                    (
                        CompletionItem(value="/help", label="/help", description="Show help"),
                        CompletionItem(value="/model", label="/model", description="Select model"),
                    )
                ),
                PathCompletionProvider(base_path=demo_root),
            )
        )

        print("Loushang TUI completion providers")
        print(f"demo_root={demo_root}")
        print("")
        for scenario in SCENARIOS:
            _run_scenario(provider, scenario)
    return 0


def _write_demo_tree(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "notes folder").mkdir()
    (root / "notes folder" / "daily note.md").write_text("Notes\n", encoding="utf-8")


def _run_scenario(provider: CombinedCompletionProvider, scenario: Scenario) -> None:
    composer = Composer(prompt="> ")
    composer.set_completion_provider(provider)
    composer.insert_text(scenario.text)
    if scenario.force:
        composer.refresh_completions(force=True)

    before = _render_lines(composer)
    composer.apply_selected_completion()
    after = _render_lines(composer)

    print(f"## {scenario.title}")
    print(f"input:  {scenario.text}")
    print("before:")
    for line in before:
        print(f"  {line}")
    print(f"output: {composer.value}")
    print("after:")
    for line in after:
        print(f"  {line}")
    print("")


def _render_lines(composer: Composer) -> tuple[str, ...]:
    result = composer.render(RenderConstraints(width=72, max_height=6))
    return tuple(line.text for line in result.lines)


if __name__ == "__main__":
    raise SystemExit(main())
