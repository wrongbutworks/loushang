from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from loushang.harnesstui.conversation.attachments import (
    ClipboardImageNameFactory,
    ClipboardImageReader,
    PromptImageAttachmentOutcome,
    new_prompt_image_name_token,
    stage_clipboard_image,
)
from loushang.harnesstui.conversation.input import (
    ConversationInputRouter,
    ConversationScreenInputPort,
    RunningSubmitMode,
)
from loushang.tui.clipboard_image import read_clipboard_image
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager


class CodingScreenInputPort(ConversationScreenInputPort, Protocol):
    cwd: str

    def set_status(self, message: str | None) -> None: ...


def build_screen_input_router(
    app: CodingScreenInputPort,
    should_exit: Callable[[str], bool],
    is_local_command: Callable[[str], bool] = lambda _text: False,
    keybindings: KeybindingManager | KeybindingConfig | None = None,
    running_submit_mode: RunningSubmitMode = "steer",
    follow_up_keys: tuple[str, ...] = ("alt+enter",),
    width: int = 80,
    height: int = 12,
    clipboard_image_reader: ClipboardImageReader = read_clipboard_image,
    clipboard_image_dir: Path | str | None = None,
    clipboard_image_name_factory: ClipboardImageNameFactory = (
        new_prompt_image_name_token
    ),
) -> ConversationInputRouter:
    """Bind Coding clipboard policy to the canonical conversation router."""

    router: ConversationInputRouter

    def current_app() -> CodingScreenInputPort:
        return cast(CodingScreenInputPort, router.app)

    def stage_image() -> PromptImageAttachmentOutcome:
        bound_app = current_app()
        directory = (
            Path(clipboard_image_dir)
            if clipboard_image_dir is not None
            else Path(bound_app.cwd) / ".loushang" / "clipboard"
        )
        return stage_clipboard_image(
            clipboard_image_reader,
            directory=directory,
            display_root=Path(bound_app.cwd),
            name_factory=clipboard_image_name_factory,
        )

    router = ConversationInputRouter(
        app=app,
        should_exit=should_exit,
        is_local_command=is_local_command,
        keybindings=keybindings,
        running_submit_mode=running_submit_mode,
        follow_up_keys=follow_up_keys,
        width=width,
        height=height,
        prompt_image_stager=stage_image,
        clipboard_outcome_presenter=lambda outcome: _present_clipboard_outcome(
            current_app(), outcome
        ),
    )
    return router


def _present_clipboard_outcome(
    app: CodingScreenInputPort,
    outcome: PromptImageAttachmentOutcome,
) -> None:
    if outcome.kind == "empty":
        app.set_status("No clipboard image found.")
    elif outcome.kind == "read_error":
        app.set_status(f"Unable to read clipboard image: {outcome.error_message}")
    elif outcome.kind == "unsupported":
        app.set_status(
            "Unsupported clipboard image type: "
            f"{outcome.mime_type or 'unknown'}"
        )
    elif outcome.kind == "write_error":
        app.set_status(
            f"Unable to attach clipboard image: {outcome.error_message}"
        )
    elif outcome.attachment is not None:
        app.set_status(
            f"Attached clipboard image: {outcome.attachment.display_path}"
        )


__all__ = [
    "CodingScreenInputPort",
    "build_screen_input_router",
]
