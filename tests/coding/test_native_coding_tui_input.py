from __future__ import annotations

import base64

from loushang.tui import CompletionItem, InputEvent, InputIntent
from loushang.tui.transcript import UserPromptRecord


def test_native_input_router_idle_enter_starts_prompt_and_clears_composer() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.composer.set_text("你好")

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="enter"))

    assert result.prompt_text == "你好"
    assert app.composer.value == ""
    assert app.state.running is True
    assert isinstance(app.state.records[0], UserPromptRecord)
    assert app.state.records[0].text == "你好"


def test_native_input_router_running_enter_queues_steer() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.start_prompt("当前代码有啥？", started_at=10.0)
    app.composer.set_text("请用中文")

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="enter"))

    assert result.prompt_text is None
    assert result.steer_text == "请用中文"
    assert app.composer.value == ""
    assert app.state.pending_steers == ["请用中文"]


def test_native_input_router_running_alt_enter_queues_followup() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.start_prompt("当前代码有啥？", started_at=10.0)
    app.composer.set_text("继续")

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="alt+enter"))

    assert result.followup_text == "继续"
    assert app.composer.value == ""
    assert app.state.pending_followups == ["继续"]


def test_native_input_router_escape_closes_completion_before_running_abort() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.start_prompt("当前代码有啥？", started_at=10.0)
    app.composer.set_text("/he")
    app.composer.set_completion_items((CompletionItem(value="/help", label="/help"),))

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="escape"))

    assert result.abort_requested is False
    assert app.state.running is True
    assert app.composer.value == "/he"
    assert not app.composer.has_completions


def test_native_input_router_restores_queued_messages_to_composer() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.queue_steer("先回答")
    app.queue_followup("再继续")

    NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="alt+up"))

    assert app.state.pending_steers == []
    assert app.state.pending_followups == []
    assert app.composer.value == "先回答\n再继续"


def test_native_input_router_uses_configured_editor_keybindings() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.composer.set_text("ab")
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        keybindings={
            "tui.editor.cursorLeft": ("alt+h",),
            "tui.editor.deleteCharForward": ("alt+x",),
        },
    )

    router.handle(InputEvent(kind="key", key="alt+h"))
    router.handle(InputEvent(kind="key", key="alt+x"))

    assert app.composer.value == "a"


def test_native_input_router_jump_mode_moves_to_next_or_previous_character() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.composer.set_text("abc def abc")
    app.composer.move_to_line_start()
    router = NativeInputRouter(app, should_exit=lambda text: False)

    assert router.handle(InputEvent(kind="key", key="ctrl+]")).render_requested is True
    router.handle(InputEvent(kind="text", text="d"))
    router.handle(InputEvent(kind="key", key="delete"))
    assert app.composer.value == "abc ef abc"

    router.handle(InputEvent(kind="key", key="ctrl+alt+]"))
    router.handle(InputEvent(kind="text", text="a"))
    router.handle(InputEvent(kind="key", key="delete"))
    assert app.composer.value == "bc ef abc"


def test_native_input_router_visual_up_down_uses_configured_width() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter
    from loushang.tui import RenderConstraints

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.composer.set_text("abcd efgh ij")
    router = NativeInputRouter(app, should_exit=lambda text: False, width=7)

    router.handle(InputEvent(kind="key", key="up"))

    result = app.composer.render(RenderConstraints(width=7, max_height=5))
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, 4)


def test_native_input_router_resize_updates_visual_movement_width() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter
    from loushang.tui import RenderConstraints

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 12.0)
    app.composer.set_text("abcd efgh ij")
    router = NativeInputRouter(app, should_exit=lambda text: False)

    router.handle(InputEvent(kind="resize", columns=7, rows=12))
    router.handle(InputEvent(kind="key", key="up"))

    result = app.composer.render(RenderConstraints(width=7, max_height=5))
    assert result.cursor is not None
    assert (result.cursor.row, result.cursor.column) == (1, 4)


def test_native_input_router_pastes_clipboard_image_as_attachment(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import ClipboardImage
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    payload = b"fake png bytes"
    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=lambda: ClipboardImage(bytes=payload, mime_type="image/png"),
        clipboard_image_dir=tmp_path / ".clips",
        clipboard_image_name_factory=lambda: "abc123",
    )

    paste_result = router.handle(InputEvent(kind="key", key="ctrl+v"))

    saved_path = tmp_path / ".clips" / "clipboard-abc123.png"
    assert paste_result.render_requested is True
    assert saved_path.read_bytes() == payload
    assert app.composer.value == "@.clips/clipboard-abc123.png "
    assert app.state.status_message == "Attached clipboard image: .clips/clipboard-abc123.png"

    app.composer.insert_text("describe it")
    submit_result = router.handle(InputEvent(kind="key", key="enter"))

    assert submit_result.prompt_text == "@.clips/clipboard-abc123.png describe it"
    assert submit_result.prompt_images is not None
    assert submit_result.prompt_images[0].mime_type == "image/png"
    assert submit_result.prompt_images[0].data == base64.b64encode(payload).decode("ascii")


def test_native_input_router_reports_empty_clipboard_image_without_editing(tmp_path) -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=lambda: None,
        clipboard_image_dir=tmp_path / ".clips",
    )

    result = router.handle(InputEvent(kind="key", key="ctrl+v"))

    assert result.render_requested is True
    assert app.composer.value == ""
    assert app.state.status_message == "No clipboard image found."
    assert not (tmp_path / ".clips").exists()


def test_native_input_router_reports_clipboard_image_read_failure_without_crashing(tmp_path) -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    def fail_to_read_clipboard_image():
        raise RuntimeError("clipboard command failed")

    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=fail_to_read_clipboard_image,
        clipboard_image_dir=tmp_path / ".clips",
    )

    result = router.handle(InputEvent(kind="key", key="ctrl+v"))

    assert result.render_requested is True
    assert app.composer.value == ""
    assert app.state.status_message == "Unable to read clipboard image: clipboard command failed"
    assert not (tmp_path / ".clips").exists()


def test_native_input_router_reports_clipboard_image_write_failure_without_crashing(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import ClipboardImage
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    blocked_path = tmp_path / "not-a-directory"
    blocked_path.write_text("file", encoding="utf-8")
    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=lambda: ClipboardImage(bytes=b"PNG", mime_type="image/png"),
        clipboard_image_dir=blocked_path,
    )

    result = router.handle(InputEvent(kind="key", key="ctrl+v"))

    assert result.render_requested is True
    assert app.composer.value == ""
    assert app.state.status_message.startswith("Unable to attach clipboard image:")


def test_native_input_router_sanitizes_clipboard_image_filename_token(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import ClipboardImage
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    payload = b"PNG"
    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=lambda: ClipboardImage(bytes=payload, mime_type="image/png"),
        clipboard_image_dir=tmp_path / ".clips",
        clipboard_image_name_factory=lambda: "../bad name:\n",
    )

    result = router.handle(InputEvent(kind="key", key="ctrl+v"))

    saved_path = tmp_path / ".clips" / "clipboard-bad_name.png"
    assert result.render_requested is True
    assert saved_path.read_bytes() == payload
    assert app.composer.value == "@.clips/clipboard-bad_name.png "
    assert app.state.status_message == "Attached clipboard image: .clips/clipboard-bad_name.png"


def test_native_input_router_orders_clipboard_images_by_marker_position(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import ClipboardImage
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    images = iter(
        [
            ClipboardImage(bytes=b"first", mime_type="image/png"),
            ClipboardImage(bytes=b"second", mime_type="image/png"),
        ]
    )
    names = iter(["first", "second"])
    app = NativeCodingTuiApp(model_label="kimi", cwd=str(tmp_path), branch="main", session_label="abcd", now=lambda: 12.0)
    router = NativeInputRouter(
        app,
        should_exit=lambda text: False,
        clipboard_image_reader=lambda: next(images),
        clipboard_image_dir=tmp_path / ".clips",
        clipboard_image_name_factory=lambda: next(names),
    )

    router.handle(InputEvent(kind="key", key="ctrl+v"))
    router.handle(InputEvent(kind="key", key="ctrl+v"))
    app.composer.set_text("@.clips/clipboard-second.png @.clips/clipboard-first.png compare")

    submit_result = router.handle(InputEvent(kind="key", key="enter"))

    assert submit_result.prompt_images is not None
    assert [image.data for image in submit_result.prompt_images] == [
        base64.b64encode(b"second").decode("ascii"),
        base64.b64encode(b"first").decode("ascii"),
    ]


def test_native_input_router_exit_command_returns_exit_code_without_transcript() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.composer.set_text("/quit")

    result = NativeInputRouter(app, should_exit=lambda text: text in {"/quit", "/exit"}).handle(InputEvent(kind="key", key="enter"))

    assert result.exit_code == 0
    assert app.state.records == []


def test_native_input_router_routes_local_slash_command_without_starting_prompt() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.composer.set_text("/model")

    result = NativeInputRouter(app, should_exit=lambda text: False, is_local_command=lambda text: text == "/model").handle(
        InputEvent(kind="key", key="enter")
    )

    assert result.local_text == "/model"
    assert app.composer.value == ""
    assert app.state.records == []
    assert app.state.running is False


def test_native_input_router_routes_active_surface_before_composer() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter

    class Surface:
        def handle_input(self, event: InputEvent) -> InputIntent | None:
            assert event.key == "enter"
            return InputIntent(kind="select", text="chosen")

        def render(self, _constraints):
            raise AssertionError("not rendered")

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.active_surface = Surface()
    app.composer.set_text("draft")

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="enter"))

    assert result.surface_intent == InputIntent(kind="select", text="chosen")
    assert app.composer.value == "draft"
    assert app.state.records == []


def test_native_input_router_routes_runtime_overlay_before_composer() -> None:
    from loushang.coding.ui.native_app import NativeCodingTuiApp
    from loushang.coding.ui.native_input import NativeInputRouter
    from loushang.coding.ui.native_surfaces import NativeSurfaceView
    from loushang.tui import CommandSurface, SelectItem, Surface, SurfaceHost

    app = NativeCodingTuiApp(model_label="kimi", cwd="/repo", branch="main", session_label="abcd", now=lambda: 10.0)
    app.surface_host = SurfaceHost()
    view = NativeSurfaceView(
        title="Commands",
        purpose="command",
        content=CommandSurface([SelectItem("/model", value="/model")]),
    )
    app.surface_host.open_surface(Surface(renderable=view, focus_target=view))
    app.composer.set_text("draft")

    result = NativeInputRouter(app, should_exit=lambda text: False).handle(InputEvent(kind="key", key="enter"))

    assert result.surface_intent == InputIntent(kind="command", text="/model")
    assert app.composer.value == "draft"
    assert app.state.records == []
