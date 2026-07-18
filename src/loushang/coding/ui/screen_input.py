from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loushang.ai.types import ImagePart
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.harnesstui.conversation.attachments import (
    ClipboardImageNameFactory,
    ClipboardImageReader,
    PendingPromptImageRegistry,
    PromptImageAttachment,
    new_prompt_image_name_token,
    stage_clipboard_image,
)
from loushang.tui.clipboard_image import read_clipboard_image
from loushang.tui.input import (
    ComposerInputTarget,
    InputEvent,
    InputIntent,
    route_editor_editing_key,
    route_editor_selection_key,
    route_prompt_completion_key,
)
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager

RunningSubmitMode = Literal["steer", "follow_up"]


@dataclass(frozen=True, slots=True)
class ScreenInputResult:
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


@dataclass(slots=True)
class ScreenInputRouter:
    app: ScreenCodingTuiApp
    should_exit: Callable[[str], bool]
    is_local_command: Callable[[str], bool] = lambda _text: False
    keybindings: KeybindingManager | KeybindingConfig | None = None
    running_submit_mode: RunningSubmitMode = "steer"
    follow_up_keys: tuple[str, ...] = ("alt+enter",)
    width: int = 80
    height: int = 12
    clipboard_image_reader: ClipboardImageReader = read_clipboard_image
    clipboard_image_dir: Path | str | None = None
    clipboard_image_name_factory: ClipboardImageNameFactory = (
        new_prompt_image_name_token
    )
    _jump_mode: Literal["forward", "backward"] | None = None
    _pending_clipboard_images: PendingPromptImageRegistry = field(
        default_factory=PendingPromptImageRegistry,
        init=False,
        repr=False,
    )
    _composer_target: ComposerInputTarget = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.keybindings, KeybindingManager):
            self.keybindings = KeybindingManager(self.keybindings)
        self._composer_target = ComposerInputTarget(self.app.composer)

    def handle(self, event: InputEvent) -> ScreenInputResult:
        if event.kind == "key" and event.event_type == "release":
            return ScreenInputResult(render_requested=False)
        if self._runtime_surface_active():
            return self._route_runtime_surface(event)
        if self.app.active_surface is not None:
            return self._route_active_surface(event)
        if event.kind == "text":
            if self._jump_mode is not None:
                self.app.composer.jump_to_char(event.text, direction=self._jump_mode)
                self._jump_mode = None
                return ScreenInputResult()
            self.app.composer.insert_text(event.text)
            return ScreenInputResult()
        if event.kind == "paste":
            self._jump_mode = None
            self.app.composer.paste(event.text)
            return ScreenInputResult()
        if event.kind == "resize":
            if event.columns:
                self.width = event.columns
            if event.rows:
                self.height = event.rows
            return ScreenInputResult()
        if event.kind != "key":
            return ScreenInputResult(render_requested=False)

        keybindings = self._keybindings()
        if self._jump_mode is not None:
            if keybindings.matches(event.key, "tui.editor.jumpForward") or keybindings.matches(
                event.key,
                "tui.editor.jumpBackward",
            ):
                self._jump_mode = None
                return ScreenInputResult()
            self._jump_mode = None
        if keybindings.matches(event.key, "tui.queue.editLast"):
            self._restore_queued_messages()
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.transcript.open"):
            return ScreenInputResult(render_requested=self.app.open_transcript_reader())
        if route_editor_selection_key(self._composer_target, event.key, keybindings=keybindings):
            return ScreenInputResult()
        if self.app.composer.has_completions and keybindings.matches(event.key, "tui.input.submit"):
            return self._submit_selected_completion()
        if self.app.composer.has_completions and self._route_completion_key(event, keybindings):
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.select.cancel"):
            return self._abort_or_clear()
        if keybindings.matches(event.key, "tui.input.tab"):
            self.app.composer.refresh_completions(force=True, explicit=True)
            if self.app.composer.has_completions:
                self.app.composer.apply_selected_completion()
            return ScreenInputResult()
        if keybindings.matches(event.key, "app.clipboard.pasteImage"):
            return self._paste_clipboard_image()
        if keybindings.matches(event.key, "tui.editor.jumpForward"):
            self._jump_mode = "forward"
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.editor.jumpBackward"):
            self._jump_mode = "backward"
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.editor.cursorUp"):
            if self.app.composer.browsing_history:
                self.app.composer.history_previous()
            elif not self.app.composer.value or not self.app.composer.move_visual_up(width=self.width):
                self.app.composer.history_previous()
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.editor.cursorDown"):
            if self.app.composer.browsing_history:
                self.app.composer.history_next()
            elif not self.app.composer.value or not self.app.composer.move_visual_down(width=self.width):
                self.app.composer.history_next()
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.editor.pageUp"):
            self.app.composer.move_visual_page_up(width=self.width, visible_lines=self._composer_page_lines())
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.editor.pageDown"):
            self.app.composer.move_visual_page_down(width=self.width, visible_lines=self._composer_page_lines())
            return ScreenInputResult()
        if self.app.state.running and event.key in self.follow_up_keys:
            return self._submit_running(mode="follow_up")
        if keybindings.matches(event.key, "tui.input.newLine"):
            self.app.composer.insert_newline()
            return ScreenInputResult()
        if keybindings.matches(event.key, "tui.input.submit"):
            return self._submit()
        if route_editor_editing_key(self._composer_target, event.key, keybindings=keybindings):
            return ScreenInputResult()
        return ScreenInputResult(render_requested=False)

    def _route_completion_key(self, event: InputEvent, keybindings: KeybindingManager) -> bool:
        return route_prompt_completion_key(self._composer_target, event.key, keybindings=keybindings)

    def _submit_selected_completion(self) -> ScreenInputResult:
        should_submit_after_completion = self.app.composer.value.lstrip().startswith("/")
        self.app.composer.apply_selected_completion()
        if should_submit_after_completion:
            return self._submit()
        return ScreenInputResult()

    def _abort_or_clear(self) -> ScreenInputResult:
        if self.app.state.running:
            return ScreenInputResult(abort_requested=True)
        if self.app.state.pending_steers:
            pending_steer = self.app.state.pending_steers.pop(0)
            return ScreenInputResult(steer_text=pending_steer)
        if self.app.composer.value:
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ScreenInputResult()
        return ScreenInputResult(render_requested=False)

    def _restore_queued_messages(self) -> None:
        text = self.app.state.restore_queued_to_text()
        if text:
            self.app.composer.set_text(text)

    def _submit(self) -> ScreenInputResult:
        text = self.app.composer.value
        if not text.strip():
            return ScreenInputResult(render_requested=False)
        if self.should_exit(text.strip()):
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ScreenInputResult(exit_code=0)
        if self.app.state.running:
            return self._submit_running(mode=self.running_submit_mode)
        if self.is_local_command(text.strip()):
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ScreenInputResult(local_text=text.strip())
        images = self._prompt_images_for_text(text)
        self.app.start_prompt(text)
        self._clear_prompt_attachments()
        return ScreenInputResult(prompt_text=text, prompt_images=images)

    def _submit_running(self, *, mode: RunningSubmitMode) -> ScreenInputResult:
        text = self.app.composer.value
        if not text.strip():
            return ScreenInputResult(render_requested=False)
        images = self._prompt_images_for_text(text)
        self.app.composer.add_history(text)
        self.app.composer.clear()
        self._clear_prompt_attachments()
        if mode == "follow_up":
            self.app.queue_followup(text)
            return ScreenInputResult(followup_text=text, followup_images=images)
        self.app.queue_steer(text)
        return ScreenInputResult(steer_text=text, steer_images=images)

    def _keybindings(self) -> KeybindingManager:
        return self.keybindings if isinstance(self.keybindings, KeybindingManager) else KeybindingManager(self.keybindings)

    def _composer_page_lines(self) -> int:
        return max(2, min(10, self.height))

    def _route_active_surface(self, event: InputEvent) -> ScreenInputResult:
        handler = getattr(self.app.active_surface, "handle_input", None)
        if not callable(handler):
            return ScreenInputResult(render_requested=False)
        intent = handler(event)
        if isinstance(intent, InputIntent):
            if intent.kind == "consumed":
                return ScreenInputResult()
            return ScreenInputResult(surface_intent=intent)
        return ScreenInputResult()

    def _runtime_surface_active(self) -> bool:
        surface_host = self.app.surface_host
        return surface_host is not None and bool(surface_host.entries)

    def _route_runtime_surface(self, event: InputEvent) -> ScreenInputResult:
        surface_host = self.app.surface_host
        if surface_host is None:
            return ScreenInputResult(render_requested=False)
        intents = surface_host.route_input(event, close_on_intents=("surface_close", "dialog_cancel"))
        for intent in intents:
            if isinstance(intent, InputIntent):
                if intent.kind == "consumed":
                    return ScreenInputResult()
                return ScreenInputResult(surface_intent=intent)
        return ScreenInputResult()

    def _paste_clipboard_image(self) -> ScreenInputResult:
        directory = (
            Path(self.clipboard_image_dir)
            if self.clipboard_image_dir is not None
            else Path(self.app.cwd) / ".loushang" / "clipboard"
        )
        outcome = stage_clipboard_image(
            self.clipboard_image_reader,
            directory=directory,
            display_root=Path(self.app.cwd),
            name_factory=self.clipboard_image_name_factory,
        )
        if outcome.kind == "empty":
            self.app.set_status("No clipboard image found.")
            return ScreenInputResult()
        if outcome.kind == "read_error":
            self.app.set_status(
                f"Unable to read clipboard image: {outcome.error_message}"
            )
            return ScreenInputResult()
        if outcome.kind == "unsupported":
            self.app.set_status(
                f"Unsupported clipboard image type: {outcome.mime_type or 'unknown'}"
            )
            return ScreenInputResult()
        if outcome.kind == "write_error":
            self.app.set_status(
                f"Unable to attach clipboard image: {outcome.error_message}"
            )
            return ScreenInputResult()
        attachment = outcome.attachment
        if attachment is None:
            raise RuntimeError("attached clipboard outcome requires an attachment")
        self.app.composer.paste(f"{attachment.marker} ")
        self._pending_clipboard_images.add(attachment)
        self.app.set_status(f"Attached clipboard image: {attachment.display_path}")
        return ScreenInputResult()

    def _prompt_images_for_text(self, text: str) -> tuple[ImagePart, ...] | None:
        attachments = self._pending_clipboard_images.select_for_text(text)
        images = tuple(_image_part(attachment) for attachment in attachments)
        return images or None

    def _clear_prompt_attachments(self) -> None:
        self._pending_clipboard_images.clear()


def _image_part(attachment: PromptImageAttachment) -> ImagePart:
    return ImagePart(
        type="image",
        data=base64.b64encode(attachment.bytes).decode("ascii"),
        mime_type=attachment.mime_type,
    )


__all__ = ["ScreenInputResult", "ScreenInputRouter", "RunningSubmitMode"]
