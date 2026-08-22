from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, cast

from loushang.harnesstui.conversation.attachments import (
    ClipboardImageNameFactory,
    ClipboardImageReader,
    PendingPromptImageRegistry,
    PromptImageAttachment,
    PromptImageAttachmentOutcome,
    new_prompt_image_name_token,
    stage_clipboard_image,
)
from loushang.harnesstui.conversation.input_policy import (
    CONVERSATION_FOLLOW_UP_ACTION,
    DEFAULT_CONVERSATION_INPUT_POLICY,
    ConversationInputPolicy,
    RunningSubmitMode,
    conversation_keybinding_manager,
)
from loushang.harnesstui.conversation.screen_state import ScreenConversationState
from loushang.tui import Composer, SurfaceHost
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

PromptImageAttachmentStager = Callable[[], PromptImageAttachmentOutcome]
ClipboardOutcomePresenter = Callable[[PromptImageAttachmentOutcome], None]


class ConversationScreenInputPort(Protocol):
    """Minimal screen-conversation surface needed by the input router."""

    composer: Composer
    state: ScreenConversationState
    active_surface: object | None
    surface_host: SurfaceHost | None

    def open_transcript_reader(self) -> bool: ...

    def start_prompt(self, text: str) -> None: ...

    def queue_followup(self, text: str) -> None: ...

    def queue_steer(self, text: str) -> None: ...


class ClipboardImageConversationInputPort(ConversationScreenInputPort, Protocol):
    """Conversation input surface capable of presenting clipboard status."""

    def set_status(self, message: str | None) -> None: ...


@dataclass(frozen=True, slots=True)
class ClipboardImageStatusCopy:
    """Caller-supplied copy for neutral clipboard attachment outcomes."""

    empty: str
    read_error_prefix: str
    unsupported_prefix: str
    write_error_prefix: str
    attached_prefix: str
    unknown_type: str

    def message(self, outcome: PromptImageAttachmentOutcome) -> str | None:
        if outcome.kind == "empty":
            return self.empty
        if outcome.kind == "read_error":
            return f"{self.read_error_prefix}{outcome.error_message}"
        if outcome.kind == "unsupported":
            return f"{self.unsupported_prefix}{outcome.mime_type or self.unknown_type}"
        if outcome.kind == "write_error":
            return f"{self.write_error_prefix}{outcome.error_message}"
        if outcome.attachment is not None:
            return f"{self.attached_prefix}{outcome.attachment.display_path}"
        return None


ClipboardImageAppPath = Callable[[ConversationScreenInputPort], Path | str]


@dataclass(frozen=True, slots=True)
class ClipboardImageInputProfile:
    """Product policy injected into app-aware clipboard image routing."""

    directory: ClipboardImageAppPath
    display_root: ClipboardImageAppPath
    status_copy: ClipboardImageStatusCopy


class ClipboardImageInputRouterBuilder(Protocol):
    """Construct a clipboard-enabled router from one bound product profile."""

    def __call__(
        self,
        app: ClipboardImageConversationInputPort,
        should_exit: Callable[[str], bool],
        is_local_command: Callable[[str], bool] = ...,
        keybindings: KeybindingManager | KeybindingConfig | None = ...,
        width: int = ...,
        height: int = ...,
        clipboard_image_reader: ClipboardImageReader = ...,
        clipboard_image_dir: Path | str | None = ...,
        clipboard_image_name_factory: ClipboardImageNameFactory = ...,
    ) -> ConversationInputRouter: ...


@dataclass(frozen=True, slots=True)
class ConversationInputHandled:
    """An input event changed local interaction state and needs a render."""

    kind: Literal["handled"] = field(default="handled", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationInputIgnored:
    """An input event produced no state change and needs no render."""

    kind: Literal["ignored"] = field(default="ignored", init=False)
    render_requested: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ConversationPromptResult:
    """Start one idle conversation prompt."""

    text: str
    attachments: tuple[object, ...] | None = None
    kind: Literal["prompt"] = field(default="prompt", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationLocalResult:
    """Dispatch one product-local command."""

    text: str
    kind: Literal["local"] = field(default="local", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationSteerResult:
    """Steer the active conversation run."""

    text: str
    attachments: tuple[object, ...] | None = None
    kind: Literal["steer"] = field(default="steer", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationFollowupResult:
    """Queue one follow-up behind the active conversation run."""

    text: str
    attachments: tuple[object, ...] | None = None
    kind: Literal["follow_up"] = field(default="follow_up", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationSurfaceResult:
    """Forward one intent emitted by an active surface."""

    intent: InputIntent
    kind: Literal["surface"] = field(default="surface", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationClipboardResult:
    """Report one clipboard-image staging outcome."""

    outcome: PromptImageAttachmentOutcome
    kind: Literal["clipboard"] = field(default="clipboard", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationAbortResult:
    """Request cancellation of the active conversation run."""

    kind: Literal["abort"] = field(default="abort", init=False)
    render_requested: bool = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class ConversationExitResult:
    """Exit the conversation screen with one process status."""

    exit_code: int
    kind: Literal["exit"] = field(default="exit", init=False)
    render_requested: bool = field(default=True, init=False)


ConversationInputResult: TypeAlias = (
    ConversationInputHandled
    | ConversationInputIgnored
    | ConversationPromptResult
    | ConversationLocalResult
    | ConversationSteerResult
    | ConversationFollowupResult
    | ConversationSurfaceResult
    | ConversationClipboardResult
    | ConversationAbortResult
    | ConversationExitResult
)


@dataclass(slots=True)
class ConversationInputRouter:
    """Route terminal input through surfaces and a conversation composer."""

    app: ConversationScreenInputPort
    should_exit: Callable[[str], bool]
    is_local_command: Callable[[str], bool] = lambda _text: False
    keybindings: KeybindingManager | KeybindingConfig | None = None
    policy: ConversationInputPolicy = DEFAULT_CONVERSATION_INPUT_POLICY
    width: int = 80
    height: int = 12
    prompt_image_stager: PromptImageAttachmentStager | None = None
    clipboard_outcome_presenter: ClipboardOutcomePresenter | None = None
    _jump_mode: Literal["forward", "backward"] | None = None
    _pending_prompt_images: PendingPromptImageRegistry = field(
        default_factory=PendingPromptImageRegistry,
        init=False,
        repr=False,
    )
    _composer_target: ComposerInputTarget = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.keybindings = conversation_keybinding_manager(self.keybindings)
        self._composer_target = ComposerInputTarget(self.app.composer)

    def replace_app(self, app: ConversationScreenInputPort) -> None:
        """Rebind the router and its composer target to another screen port."""

        self.app = app
        self._composer_target = ComposerInputTarget(app.composer)

    def handle(self, event: InputEvent) -> ConversationInputResult:
        if event.kind == "key" and event.event_type == "release":
            return ConversationInputIgnored()
        if self._runtime_surface_active():
            return self._route_runtime_surface(event)
        if self.app.active_surface is not None:
            return self._route_active_surface(event)
        if event.kind == "text":
            if self._jump_mode is not None:
                self.app.composer.jump_to_char(
                    event.text,
                    direction=self._jump_mode,
                )
                self._jump_mode = None
                return ConversationInputHandled()
            self.app.composer.insert_text(event.text)
            return ConversationInputHandled()
        if event.kind == "paste":
            self._jump_mode = None
            self.app.composer.paste(event.text)
            return ConversationInputHandled()
        if event.kind == "resize":
            if event.columns:
                self.width = event.columns
            if event.rows:
                self.height = event.rows
            return ConversationInputHandled()
        if event.kind != "key":
            return ConversationInputIgnored()

        keybindings = self._keybindings()
        if self._jump_mode is not None:
            if keybindings.matches(
                event.key,
                "tui.editor.jumpForward",
            ) or keybindings.matches(
                event.key,
                "tui.editor.jumpBackward",
            ):
                self._jump_mode = None
                return ConversationInputHandled()
            self._jump_mode = None
        if keybindings.matches(event.key, "tui.queue.editLast"):
            self._restore_queued_messages()
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.transcript.open"):
            return (
                ConversationInputHandled()
                if self.app.open_transcript_reader()
                else ConversationInputIgnored()
            )
        if route_editor_selection_key(
            self._composer_target,
            event.key,
            keybindings=keybindings,
        ):
            return ConversationInputHandled()
        if self.app.composer.has_completions and keybindings.matches(
            event.key,
            "tui.input.submit",
        ):
            return self._submit_selected_completion()
        if self.app.composer.has_completions and self._route_completion_key(
            event,
            keybindings,
        ):
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.select.cancel"):
            return self._abort_or_clear()
        if keybindings.matches(event.key, "tui.input.tab"):
            self.app.composer.refresh_completions(force=True, explicit=True)
            if self.app.composer.has_completions:
                self.app.composer.apply_selected_completion()
            return ConversationInputHandled()
        if keybindings.matches(event.key, "app.clipboard.pasteImage"):
            return self._paste_clipboard_image()
        if keybindings.matches(event.key, "tui.editor.jumpForward"):
            self._jump_mode = "forward"
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.editor.jumpBackward"):
            self._jump_mode = "backward"
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.editor.cursorUp"):
            if self.app.composer.browsing_history:
                self.app.composer.history_previous()
            elif (
                not self.app.composer.value
                or not self.app.composer.move_visual_up(width=self.width)
            ):
                self.app.composer.history_previous()
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.editor.cursorDown"):
            if self.app.composer.browsing_history:
                self.app.composer.history_next()
            elif (
                not self.app.composer.value
                or not self.app.composer.move_visual_down(width=self.width)
            ):
                self.app.composer.history_next()
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.editor.pageUp"):
            self.app.composer.move_visual_page_up(
                width=self.width,
                visible_lines=self._composer_page_lines(),
            )
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.editor.pageDown"):
            self.app.composer.move_visual_page_down(
                width=self.width,
                visible_lines=self._composer_page_lines(),
            )
            return ConversationInputHandled()
        if self.app.state.running and keybindings.matches(
            event.key, CONVERSATION_FOLLOW_UP_ACTION
        ):
            return self._submit_running(mode="follow_up")
        if keybindings.matches(event.key, "tui.input.newLine"):
            self.app.composer.insert_newline()
            return ConversationInputHandled()
        if keybindings.matches(event.key, "tui.input.submit"):
            return self._submit()
        if route_editor_editing_key(
            self._composer_target,
            event.key,
            keybindings=keybindings,
        ):
            return ConversationInputHandled()
        return ConversationInputIgnored()

    def _route_completion_key(
        self,
        event: InputEvent,
        keybindings: KeybindingManager,
    ) -> bool:
        return route_prompt_completion_key(
            self._composer_target,
            event.key,
            keybindings=keybindings,
        )

    def _submit_selected_completion(self) -> ConversationInputResult:
        should_submit_after_completion = self.app.composer.value.lstrip().startswith(
            "/"
        )
        self.app.composer.apply_selected_completion()
        if should_submit_after_completion:
            return self._submit()
        return ConversationInputHandled()

    def _abort_or_clear(self) -> ConversationInputResult:
        if self.app.state.running:
            return ConversationAbortResult()
        if self.app.state.pending_steers:
            pending_steer = self.app.state.pending_steers.pop(0)
            return ConversationSteerResult(text=pending_steer)
        if self.app.composer.value:
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ConversationInputHandled()
        return ConversationInputIgnored()

    def _restore_queued_messages(self) -> None:
        text = self.app.state.restore_queued_to_text()
        if text:
            self.app.composer.set_text(text)

    def _submit(self) -> ConversationInputResult:
        text = self.app.composer.value
        if not text.strip():
            return ConversationInputIgnored()
        if self.should_exit(text.strip()):
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ConversationExitResult(exit_code=0)
        if self.is_local_command(text.strip()):
            self.app.composer.clear()
            self._clear_prompt_attachments()
            return ConversationLocalResult(text=text.strip())
        if self.app.state.running:
            mode = self.policy.resolve_running_submit(self.app.state.input_capabilities)
            return (
                ConversationInputIgnored()
                if mode is None
                else self._submit_running(mode=mode)
            )
        attachments = self._prompt_attachments_for_text(text)
        self.app.start_prompt(text)
        self._clear_prompt_attachments()
        return ConversationPromptResult(
            text=text,
            attachments=attachments,
        )

    def _submit_running(
        self,
        *,
        mode: RunningSubmitMode,
    ) -> ConversationInputResult:
        if not self.app.state.input_capabilities.supports(mode):
            return ConversationInputIgnored()
        text = self.app.composer.value
        if not text.strip():
            return ConversationInputIgnored()
        attachments = self._prompt_attachments_for_text(text)
        self.app.composer.add_history(text)
        self.app.composer.clear()
        self._clear_prompt_attachments()
        if mode == "follow_up":
            self.app.queue_followup(text)
            return ConversationFollowupResult(
                text=text,
                attachments=attachments,
            )
        self.app.queue_steer(text)
        return ConversationSteerResult(
            text=text,
            attachments=attachments,
        )

    def _keybindings(self) -> KeybindingManager:
        if isinstance(self.keybindings, KeybindingManager):
            return self.keybindings
        return KeybindingManager(self.keybindings)

    def _composer_page_lines(self) -> int:
        return max(2, min(10, self.height))

    def _route_active_surface(self, event: InputEvent) -> ConversationInputResult:
        handler = getattr(self.app.active_surface, "handle_input", None)
        if not callable(handler):
            return ConversationInputIgnored()
        intent = handler(event)
        if isinstance(intent, InputIntent):
            if intent.kind == "consumed":
                return ConversationInputHandled()
            return ConversationSurfaceResult(intent=intent)
        return ConversationInputHandled()

    def _runtime_surface_active(self) -> bool:
        surface_host = self.app.surface_host
        return surface_host is not None and bool(surface_host.entries)

    def _route_runtime_surface(
        self,
        event: InputEvent,
    ) -> ConversationInputResult:
        surface_host = self.app.surface_host
        if surface_host is None:
            return ConversationInputIgnored()
        intents = surface_host.route_input(
            event,
            close_on_intents=("surface_close", "dialog_cancel"),
        )
        for intent in intents:
            if isinstance(intent, InputIntent):
                if intent.kind == "consumed":
                    return ConversationInputHandled()
                return ConversationSurfaceResult(intent=intent)
        return ConversationInputHandled()

    def _paste_clipboard_image(self) -> ConversationInputResult:
        if self.prompt_image_stager is None:
            return ConversationInputIgnored()
        outcome = self.prompt_image_stager()
        attachment = outcome.attachment
        if outcome.kind != "attached":
            self._present_clipboard_outcome(outcome)
            return ConversationClipboardResult(outcome=outcome)
        if attachment is None:
            raise RuntimeError("attached clipboard outcome requires an attachment")
        self.app.composer.paste(f"{attachment.marker} ")
        self._pending_prompt_images.add(attachment)
        self._present_clipboard_outcome(outcome)
        return ConversationClipboardResult(outcome=outcome)

    def _present_clipboard_outcome(
        self,
        outcome: PromptImageAttachmentOutcome,
    ) -> None:
        if self.clipboard_outcome_presenter is not None:
            self.clipboard_outcome_presenter(outcome)

    def _prompt_attachments_for_text(
        self,
        text: str,
    ) -> tuple[PromptImageAttachment, ...] | None:
        attachments = self._pending_prompt_images.select_for_text(text)
        return attachments or None

    def _clear_prompt_attachments(self) -> None:
        self._pending_prompt_images.clear()


def bind_clipboard_image_input_router(
    profile: ClipboardImageInputProfile,
    *,
    policy: ConversationInputPolicy = DEFAULT_CONVERSATION_INPUT_POLICY,
) -> ClipboardImageInputRouterBuilder:
    """Bind app-aware staging and status presentation to a router builder.

    The callbacks resolve the router's current app at event time. Replacing the
    app therefore also replaces the workspace and status destination without
    rebuilding the router.
    """

    def build(
        app: ClipboardImageConversationInputPort,
        should_exit: Callable[[str], bool],
        is_local_command: Callable[[str], bool] = lambda _text: False,
        keybindings: KeybindingManager | KeybindingConfig | None = None,
        width: int = 80,
        height: int = 12,
        clipboard_image_reader: ClipboardImageReader = read_clipboard_image,
        clipboard_image_dir: Path | str | None = None,
        clipboard_image_name_factory: ClipboardImageNameFactory = (
            new_prompt_image_name_token
        ),
    ) -> ConversationInputRouter:
        router: ConversationInputRouter

        def current_app() -> ClipboardImageConversationInputPort:
            return cast(ClipboardImageConversationInputPort, router.app)

        def stage_image() -> PromptImageAttachmentOutcome:
            bound_app = current_app()
            return stage_clipboard_image(
                clipboard_image_reader,
                directory=(
                    clipboard_image_dir
                    if clipboard_image_dir is not None
                    else profile.directory(bound_app)
                ),
                display_root=profile.display_root(bound_app),
                name_factory=clipboard_image_name_factory,
            )

        def present_outcome(outcome: PromptImageAttachmentOutcome) -> None:
            message = profile.status_copy.message(outcome)
            if message is not None:
                current_app().set_status(message)

        router = ConversationInputRouter(
            app=app,
            should_exit=should_exit,
            is_local_command=is_local_command,
            keybindings=keybindings,
            policy=policy,
            width=width,
            height=height,
            prompt_image_stager=stage_image,
            clipboard_outcome_presenter=present_outcome,
        )
        return router

    return build


__all__ = [
    "ClipboardImageConversationInputPort",
    "ClipboardImageInputProfile",
    "ClipboardImageInputRouterBuilder",
    "ClipboardImageStatusCopy",
    "ClipboardOutcomePresenter",
    "ConversationAbortResult",
    "ConversationClipboardResult",
    "ConversationExitResult",
    "ConversationFollowupResult",
    "ConversationInputHandled",
    "ConversationInputIgnored",
    "ConversationInputResult",
    "ConversationInputRouter",
    "ConversationInputPolicy",
    "ConversationLocalResult",
    "ConversationPromptResult",
    "ConversationScreenInputPort",
    "ConversationSteerResult",
    "ConversationSurfaceResult",
    "PromptImageAttachmentStager",
    "RunningSubmitMode",
    "bind_clipboard_image_input_router",
]
