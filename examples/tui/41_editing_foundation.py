from __future__ import annotations

from loushang.tui import (
    Composer,
    InputEvent,
    InputRouter,
    RenderConstraints,
    TextInput,
    strip_control_sequences,
)


def main() -> int:
    print("Loushang TUI editing foundation")
    print("")
    _text_input_walkthrough()
    print("")
    _composer_walkthrough()
    return 0


def _text_input_walkthrough() -> None:
    field = TextInput(prompt="Search: ", placeholder="type to filter")
    field.focus()
    field.handle_input(InputEvent(kind="text", text="hello world"))
    field.handle_input(InputEvent(kind="key", key="ctrl+shift+left"))
    selected = field.selected_range
    selected_text = _slice_text(field.value, selected)
    field.handle_input(InputEvent(kind="text", text="loushang"))
    replaced = field.value
    field.handle_input(InputEvent(kind="key", key="ctrl+-"))
    undone = field.value
    field.handle_input(InputEvent(kind="key", key="ctrl+shift+z"))

    print("## TextInput")
    print(f"selection: {selected!r} -> {selected_text!r}")
    print(f"replace:   {replaced!r}")
    print(f"undo:      {undone!r}")
    print(f"redo:      {field.value!r}")
    _print_rendered(field.render(RenderConstraints(width=40, max_height=1)))


def _composer_walkthrough() -> None:
    composer = Composer(prompt="> ")
    router = InputRouter(composer, width=72, height=12)
    router.route(InputEvent(kind="text", text="alpha beta"))
    router.route(InputEvent(kind="key", key="shift+left"))
    selected = composer.selected_range
    router.route(InputEvent(kind="key", key="ctrl+k"))
    killed = composer.value
    kill_ring = composer.kill_ring
    router.route(InputEvent(kind="key", key="ctrl+y"))
    yanked = composer.value
    router.route(InputEvent(kind="key", key="ctrl+-"))
    undo = composer.value
    router.route(InputEvent(kind="key", key="ctrl+shift+z"))
    redo = composer.value
    router.route(InputEvent(kind="text", text=" "))
    router.route(
        InputEvent(
            kind="paste", text="\n".join(f"line {index}" for index in range(1, 11))
        )
    )

    print("## Composer")
    print(f"selection: {selected!r}")
    print(f"kill:      {killed!r}")
    print(f"kill ring: {kill_ring!r}")
    print(f"yank:      {yanked!r}")
    print(f"undo:      {undo!r}")
    print(f"redo:      {redo!r}")
    print(f"paste:     {composer.value!r}")
    _print_rendered(composer.render(RenderConstraints(width=72, max_height=6)))


def _slice_text(text: str, selected_range: tuple[int, int] | None) -> str:
    if selected_range is None:
        return ""
    start, end = selected_range
    return text[start:end]


def _print_rendered(result: object) -> None:
    print("render:")
    for line in getattr(result, "lines"):
        print(f"  {strip_control_sequences(line.text)}")


if __name__ == "__main__":
    raise SystemExit(main())
