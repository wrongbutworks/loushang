from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from loushang.ai.types import ImagePart
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.harnesstui.conversation.attachments import (
    ClipboardImageNameFactory,
    ClipboardImageReader,
    PromptImageAttachment,
    PromptImageAttachmentOutcome,
    new_prompt_image_name_token,
    stage_clipboard_image,
)
from loushang.harnesstui.conversation.input import (
    ConversationInputResult,
    ConversationInputRouter,
    RunningSubmitMode,
)
from loushang.tui.clipboard_image import read_clipboard_image
from loushang.tui.input import InputEvent, InputIntent
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager


@dataclass(frozen=True, slots=True)
class ScreenInputResult:
    """Coding result with AI image parts ready for product dispatch."""

    prompt_text: str | None = None
    prompt_images: tuple[ImagePart, ...] | None = None
    local_text: str | None = None
    steer_text: str | None = None
    steer_images: tuple[ImagePart, ...] | None = None
    followup_text: str | None = None
    followup_images: tuple[ImagePart, ...] | None = None
    surface_intent: InputIntent | None = None
    abort_requested: bool = False
    exit_code: int | None = None
    render_requested: bool = True

    @property
    def prompt_attachments(self) -> tuple[ImagePart, ...] | None:
        return self.prompt_images

    @property
    def steer_attachments(self) -> tuple[ImagePart, ...] | None:
        return self.steer_images

    @property
    def followup_attachments(self) -> tuple[ImagePart, ...] | None:
        return self.followup_images


class ScreenInputRouter:
    """Compatibility facade around the shared conversation input router."""

    __slots__ = (
        "_router",
        "clipboard_image_dir",
        "clipboard_image_name_factory",
        "clipboard_image_reader",
    )

    def __init__(
        self,
        app: ScreenCodingTuiApp,
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
    ) -> None:
        self.clipboard_image_reader = clipboard_image_reader
        self.clipboard_image_dir = clipboard_image_dir
        self.clipboard_image_name_factory = clipboard_image_name_factory
        self._router = ConversationInputRouter(
            app=app,
            should_exit=should_exit,
            is_local_command=is_local_command,
            keybindings=keybindings,
            running_submit_mode=running_submit_mode,
            follow_up_keys=follow_up_keys,
            width=width,
            height=height,
            prompt_image_stager=self._stage_clipboard_image,
        )

    @property
    def app(self) -> ScreenCodingTuiApp:
        return cast(ScreenCodingTuiApp, self._router.app)

    @app.setter
    def app(self, value: ScreenCodingTuiApp) -> None:
        self._router.replace_app(value)

    @property
    def should_exit(self) -> Callable[[str], bool]:
        return self._router.should_exit

    @should_exit.setter
    def should_exit(self, value: Callable[[str], bool]) -> None:
        self._router.should_exit = value

    @property
    def is_local_command(self) -> Callable[[str], bool]:
        return self._router.is_local_command

    @is_local_command.setter
    def is_local_command(self, value: Callable[[str], bool]) -> None:
        self._router.is_local_command = value

    @property
    def width(self) -> int:
        return self._router.width

    @width.setter
    def width(self, value: int) -> None:
        self._router.width = value

    @property
    def height(self) -> int:
        return self._router.height

    @height.setter
    def height(self, value: int) -> None:
        self._router.height = value

    @property
    def keybindings(self) -> KeybindingManager | KeybindingConfig | None:
        return self._router.keybindings

    @keybindings.setter
    def keybindings(
        self,
        value: KeybindingManager | KeybindingConfig | None,
    ) -> None:
        self._router.keybindings = value

    @property
    def running_submit_mode(self) -> RunningSubmitMode:
        return self._router.running_submit_mode

    @running_submit_mode.setter
    def running_submit_mode(self, value: RunningSubmitMode) -> None:
        self._router.running_submit_mode = value

    @property
    def follow_up_keys(self) -> tuple[str, ...]:
        return self._router.follow_up_keys

    @follow_up_keys.setter
    def follow_up_keys(self, value: tuple[str, ...]) -> None:
        self._router.follow_up_keys = value

    def handle(self, event: InputEvent) -> ScreenInputResult:
        result = self._router.handle(event)
        self._apply_clipboard_status(result.clipboard_outcome)
        return _screen_input_result(result)

    def _stage_clipboard_image(self) -> PromptImageAttachmentOutcome:
        directory = (
            Path(self.clipboard_image_dir)
            if self.clipboard_image_dir is not None
            else Path(self.app.cwd) / ".loushang" / "clipboard"
        )
        return stage_clipboard_image(
            self.clipboard_image_reader,
            directory=directory,
            display_root=Path(self.app.cwd),
            name_factory=self.clipboard_image_name_factory,
        )

    def _apply_clipboard_status(
        self,
        outcome: PromptImageAttachmentOutcome | None,
    ) -> None:
        if outcome is None:
            return
        if outcome.kind == "empty":
            self.app.set_status("No clipboard image found.")
            return
        if outcome.kind == "read_error":
            self.app.set_status(
                f"Unable to read clipboard image: {outcome.error_message}"
            )
            return
        if outcome.kind == "unsupported":
            self.app.set_status(
                "Unsupported clipboard image type: "
                f"{outcome.mime_type or 'unknown'}"
            )
            return
        if outcome.kind == "write_error":
            self.app.set_status(
                f"Unable to attach clipboard image: {outcome.error_message}"
            )
            return
        attachment = outcome.attachment
        if attachment is None:
            raise RuntimeError("attached clipboard outcome requires an attachment")
        self.app.set_status(
            f"Attached clipboard image: {attachment.display_path}"
        )


def _screen_input_result(result: ConversationInputResult) -> ScreenInputResult:
    return ScreenInputResult(
        prompt_text=result.prompt_text,
        prompt_images=_image_parts(result.prompt_attachments),
        local_text=result.local_text,
        steer_text=result.steer_text,
        steer_images=_image_parts(result.steer_attachments),
        followup_text=result.followup_text,
        followup_images=_image_parts(result.followup_attachments),
        surface_intent=result.surface_intent,
        abort_requested=result.abort_requested,
        exit_code=result.exit_code,
        render_requested=result.render_requested,
    )


def _image_parts(
    attachments: tuple[PromptImageAttachment, ...] | None,
) -> tuple[ImagePart, ...] | None:
    if attachments is None:
        return None
    return tuple(_image_part(attachment) for attachment in attachments)


def _image_part(attachment: PromptImageAttachment) -> ImagePart:
    return ImagePart(
        type="image",
        data=base64.b64encode(attachment.bytes).decode("ascii"),
        mime_type=attachment.mime_type,
    )


__all__ = ["ScreenInputResult", "ScreenInputRouter", "RunningSubmitMode"]
