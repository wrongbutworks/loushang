from __future__ import annotations

from loushang.ai.types import ImagePart
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import ScreenInputResult, ScreenInputRouter
from loushang.tui import InputEvent
from loushang.tui.keybindings import KeybindingManager


def _app(*, cwd: str = "/repo") -> ScreenCodingTuiApp:
    return ScreenCodingTuiApp(
        model_label="kimi",
        cwd=cwd,
        branch="main",
        session_label="abcd",
        now=lambda: 12.0,
    )


def test_screen_input_result_preserves_images_and_neutral_aliases() -> None:
    image = ImagePart(
        type="image",
        data="cG5n",
        mime_type="image/png",
    )
    result = ScreenInputResult(
        prompt_images=(image,),
        steer_images=(image,),
        followup_images=(image,),
    )

    assert result.prompt_attachments == result.prompt_images
    assert result.steer_attachments == result.steer_images
    assert result.followup_attachments == result.followup_images


def test_screen_input_router_preserves_public_read_write_configuration() -> None:
    def exit_predicate(text: str) -> bool:
        return text == "/bye"

    def local_predicate(text: str) -> bool:
        return text == "/help"

    first_app = _app()
    replacement_app = _app(cwd="/other")
    router = ScreenInputRouter(
        first_app,
        should_exit=lambda text: text == "/quit",
        is_local_command=lambda text: text == "/model",
        width=80,
        height=12,
    )
    keybindings = KeybindingManager(
        {"tui.input.submit": ("alt+s",)},
    )

    router.app = replacement_app
    router.should_exit = exit_predicate
    router.is_local_command = local_predicate
    router.width = 100
    router.height = 20
    router.keybindings = keybindings
    router.running_submit_mode = "follow_up"
    router.follow_up_keys = ("ctrl+enter",)

    assert router.app is replacement_app
    assert router.should_exit is exit_predicate
    assert router.is_local_command is local_predicate
    assert (router.width, router.height) == (100, 20)
    assert router.keybindings is keybindings
    assert router.running_submit_mode == "follow_up"
    assert router.follow_up_keys == ("ctrl+enter",)

    replacement_app.composer.set_text("/bye")
    result = router.handle(InputEvent(kind="key", key="alt+s"))
    assert result.exit_code == 0
