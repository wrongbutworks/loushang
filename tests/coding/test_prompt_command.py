from __future__ import annotations

import asyncio
from io import StringIO
from types import SimpleNamespace


def test_prompt_command_renders_stable_transcript_and_worked() -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage
    from loushang.coding.prompt_command import run_prompt_command

    usage = Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={})

    class FakeRuntime:
        def __init__(self) -> None:
            self.dispose_calls = 0

        async def dispose(self) -> None:
            self.dispose_calls += 1

    class FakeSession:
        def __init__(self) -> None:
            self.listeners = []

        def subscribe(self, listener):
            self.listeners.append(listener)

            def unsubscribe() -> None:
                self.listeners.remove(listener)

            return unsubscribe

        async def prompt(self, user_input: str, images=None) -> None:
            del user_input, images
            assistant = AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="done")],
                api="anthropic-messages",
                provider="faux",
                model="faux-model",
                response_id=None,
                usage=usage,
                stop_reason="stop",
                error_message=None,
                timestamp=0.0,
            )
            for listener in list(self.listeners):
                listener(
                    {
                        "type": "tool_execution_start",
                        "tool_call_id": "t1",
                        "tool_name": "bash",
                        "args": {"command": "pwd"},
                    }
                )
                listener(
                    {
                        "type": "tool_execution_end",
                        "tool_call_id": "t1",
                        "tool_name": "bash",
                        "result": {"content": [], "details": {}},
                        "is_error": False,
                    }
                )
                listener({"type": "message_end", "message": assistant})

        async def wait_for_idle(self) -> None:
            return None

    async def scenario() -> None:
        runtime = FakeRuntime()
        stdout = StringIO()
        exit_code = await run_prompt_command(
            runtime=runtime,
            session=FakeSession(),
            prompt="hello",
            stdout=stdout,
            stderr=StringIO(),
        )

        rendered = stdout.getvalue()
        assert exit_code == 0
        assert "› hello\n" in rendered
        assert "• Ran bash pwd\n" in rendered
        assert "• done\n" in rendered
        assert "─ Worked for " in rendered
        assert "[tool:bash" not in rendered
        assert runtime.dispose_calls == 1

    asyncio.run(scenario())


def test_prompt_command_selects_usable_model_before_prompt() -> None:
    from loushang.ai import Model
    from loushang.coding.prompt_command import run_prompt_command
    from loushang.coding.types import ModelSelection

    kimi = Model(
        id="kimi-for-coding",
        provider="moonshot",
        endpoint="kimi-code-anthropic",
    )

    class FakeRuntime:
        pass

    class FakeSession:
        def __init__(self) -> None:
            self.current_model = ModelSelection(provider="unknown", model_id="unknown")
            self.set_model_calls = []
            self.listeners = []
            self.prompt_calls = []

        def get_model_selection(self):
            return self.current_model

        def get_available_model_details(self):
            return [kimi]

        async def set_model(self, selection):
            self.set_model_calls.append(selection)
            self.current_model = ModelSelection(provider=selection.provider_id, model_id=selection.id)

        def subscribe(self, listener):
            self.listeners.append(listener)

            def unsubscribe() -> None:
                self.listeners.remove(listener)

            return unsubscribe

        async def prompt(self, user_input: str, images=None) -> None:
            self.prompt_calls.append((user_input, self.current_model))

        async def wait_for_idle(self) -> None:
            return None

    async def scenario() -> None:
        session = FakeSession()
        exit_code = await run_prompt_command(
            runtime=FakeRuntime(),
            session=session,
            prompt="hello",
            stdout=StringIO(),
            stderr=StringIO(),
        )

        assert exit_code == 0
        assert session.set_model_calls == [kimi]
        assert session.prompt_calls == [("hello", ModelSelection(provider="moonshot", model_id="kimi-for-coding"))]

    asyncio.run(scenario())


def test_prompt_command_work_event_log_records_prompt_turn() -> None:
    from loushang.coding.prompt_command import run_prompt_command
    from loushang.work import InMemoryEventLogBackend

    class FakeRuntime:
        pass

    class FakeSession:
        session_id = "session-1"

        def __init__(self) -> None:
            self.listeners = []

        def get_model_selection(self):
            return None

        def subscribe(self, listener):
            self.listeners.append(listener)

            def unsubscribe() -> None:
                self.listeners.remove(listener)

            return unsubscribe

        async def prompt(self, user_input: str, images=None) -> None:
            del user_input, images
            for listener in list(self.listeners):
                result = listener(
                    {
                        "type": "message_update",
                        "message": {"role": "assistant"},
                        "assistant_message_event": {"type": "text_delta", "text": "done"},
                    }
                )
                if result is not None:
                    await result

        async def wait_for_idle(self) -> None:
            return None

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        exit_code = await run_prompt_command(
            runtime=FakeRuntime(),
            session=FakeSession(),
            prompt="hello",
            stdout=StringIO(),
            stderr=StringIO(),
            work_event_log=event_log,
            method_id="method:task:review",
        )

        assert exit_code == 0
        entries = event_log.query(session_id="session-1")
        assert [entry.payload["kind"] for entry in entries] == [
            "SubmitCodingTurn",
            "WorkRunStarted",
            "ContentDelta",
            "WorkRunCompleted",
        ]
        assert entries[0].payload["payload"]["method_id"] == "method:task:review"
        assert entries[1].payload["payload"]["method_id"] == "method:task:review"
        assert entries[3].payload["payload"]["method_id"] == "method:task:review"

    asyncio.run(scenario())


def test_prompt_command_does_not_render_worked_after_assistant_error() -> None:
    from loushang.coding.prompt_command import run_prompt_command

    class FakeRuntime:
        pass

    class FakeSession:
        def __init__(self) -> None:
            self.listeners = []
            self.messages = []

        def subscribe(self, listener):
            self.listeners.append(listener)

            def unsubscribe() -> None:
                self.listeners.remove(listener)

            return unsubscribe

        async def prompt(self, user_input: str, images=None) -> None:
            del user_input, images
            assistant = SimpleNamespace(
                role="assistant",
                content=[],
                stop_reason="error",
                error_message="Endpoint not found for model: unknown:unknown:unknown",
            )
            self.messages.append(assistant)
            for listener in list(self.listeners):
                listener({"type": "message_end", "message": assistant})

        async def wait_for_idle(self) -> None:
            return None

    async def scenario() -> None:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = await run_prompt_command(
            runtime=FakeRuntime(),
            session=FakeSession(),
            prompt="hello",
            stdout=stdout,
            stderr=stderr,
        )

        rendered = stdout.getvalue()
        assert exit_code == 1
        assert "■ Error: Endpoint not found for model: unknown:unknown:unknown" in rendered
        assert "Worked for" not in rendered
        assert stderr.getvalue() == ""

    asyncio.run(scenario())
