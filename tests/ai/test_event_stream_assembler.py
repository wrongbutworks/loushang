from __future__ import annotations

import asyncio

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.types import AssistantMessage, Usage


def test_raw_assembler_uses_real_content_index_for_thinking_only_stream() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api="openai-responses",
        provider="openai",
        model="gpt-test",
    )

    assembler.feed({"type": "response_start", "response_id": "resp_1"})
    assembler.feed({"type": "thinking_delta", "text": "plan"})
    assembler.feed(
        {
            "type": "thinking_signature_delta",
            "signature": '{"type":"reasoning","id":"rs_1","summary":[]}',
        }
    )
    assembler.feed({"type": "response_done"})

    events = asyncio.run(_collect_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "done",
    ]
    assert events[1]["content_index"] == 0
    assert events[-1]["message"].content[0].type == "thinking"
    assert events[-1]["message"].content[0].thinking == "plan"


def test_raw_assembler_uses_real_content_index_for_toolcall_only_stream() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api="openai-completions",
        provider="openai",
        model="gpt-test",
    )

    assembler.feed({"type": "response_start", "response_id": "resp_1"})
    assembler.feed({"type": "tool_call_start", "id": "call_1", "name": "calc"})
    assembler.feed({"type": "tool_call_args_delta", "delta": '{"x":1}'})
    assembler.feed({"type": "tool_call_done"})
    assembler.feed({"type": "response_done"})

    events = asyncio.run(_collect_events(stream))

    assert [event["type"] for event in events] == [
        "start",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_end",
        "done",
    ]
    assert events[1]["content_index"] == 0
    assert events[2]["content_index"] == 0
    assert events[3]["content_index"] == 0
    assert events[-1]["message"].content[0].type == "toolCall"
    assert events[-1]["message"].content[0].arguments == {"x": 1}


def test_raw_assembler_preserves_content_order_across_block_types() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api="openai-responses",
        provider="openai",
        model="gpt-test",
    )

    assembler.feed({"type": "response_start", "response_id": "resp_1"})
    assembler.feed({"type": "thinking_delta", "text": "plan"})
    assembler.feed({"type": "text_delta", "text": "answer"})
    assembler.feed({"type": "tool_call_start", "id": "call_1", "name": "calc"})
    assembler.feed({"type": "tool_call_args_delta", "delta": '{"x":1}'})
    assembler.feed({"type": "tool_call_done"})
    assembler.feed({"type": "response_done"})

    events = asyncio.run(_collect_events(stream))

    assert events[1]["type"] == "thinking_start"
    assert events[1]["content_index"] == 0
    assert events[3]["type"] == "text_start"
    assert events[3]["content_index"] == 1
    assert events[5]["type"] == "toolcall_start"
    assert events[5]["content_index"] == 2
    assert events[8]["type"] == "thinking_end"
    assert events[8]["content_index"] == 0
    assert events[9]["type"] == "text_end"
    assert events[9]["content_index"] == 1
    assert [part.type for part in events[-1]["message"].content] == [
        "thinking",
        "text",
        "toolCall",
    ]


async def _collect_events(stream: AssistantMessageEventStream) -> list[dict]:
    return [event async for event in stream]


def test_event_stream_cancels_producer_when_consumer_stops() -> None:
    async def scenario() -> bool:
        stream = AssistantMessageEventStream()
        cancelled = asyncio.Event()
        message = AssistantMessage(
            role="assistant",
            content=[],
            api="openai-responses",
            provider="openai",
            model="gpt-test",
            response_id=None,
            usage=Usage(
                input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
            ),
            stop_reason="stop",
            error_message=None,
            timestamp=0.0,
        )

        async def producer() -> None:
            try:
                stream.push({"type": "start", "partial": message})
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        task = asyncio.create_task(producer())
        stream.attach_task(task)
        async for _event in stream:
            break
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        return task.cancelled()

    assert asyncio.run(scenario())


def test_event_stream_result_preserves_producer_exception() -> None:
    async def scenario() -> None:
        stream = AssistantMessageEventStream()

        async def producer() -> None:
            raise ValueError("boom")

        stream.attach_task(asyncio.create_task(producer()))
        await stream.result()

    try:
        asyncio.run(scenario())
    except RuntimeError as exc:
        assert "producer failed" in str(exc)
        assert isinstance(exc.__cause__, ValueError)
    else:  # pragma: no cover
        raise AssertionError("expected producer exception")


def test_raw_assembler_preserves_typed_error_fields() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api="openai-responses",
        provider="openai",
        model="gpt-test",
    )

    assembler.feed(
        {
            "type": "response_error",
            "message": "rate limited",
            "code": "rate_limit",
            "source": "openai-responses",
            "retryable": True,
        }
    )

    events = asyncio.run(_collect_events(stream))

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "rate_limit"
    assert events[-1]["source"] == "openai-responses"
    assert events[-1]["retryable"] is True


def test_raw_assembler_derives_total_tokens_when_provider_omits_total() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(stream=stream, api="test", provider="test", model="test-model")

    assembler.feed({"type": "response_start", "response_id": "resp-1"})
    assembler.feed({"type": "usage_delta", "input": 10, "output": 4, "cache_read": 3, "cache_write": 2})
    assembler.feed({"type": "response_done"})

    message = asyncio.run(stream.result())

    assert message.usage.input == 10
    assert message.usage.output == 4
    assert message.usage.cache_read == 3
    assert message.usage.cache_write == 2
    assert message.usage.total_tokens == 19


def test_raw_assembler_recomputes_total_tokens_for_incremental_usage_without_total() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(stream=stream, api="test", provider="test", model="test-model")

    assembler.feed({"type": "response_start", "response_id": "resp-1"})
    assembler.feed({"type": "usage_delta", "input": 10, "output": 1, "total_tokens": 11})
    assembler.feed({"type": "usage_delta", "output": 4})
    assembler.feed({"type": "response_done"})

    message = asyncio.run(stream.result())

    assert message.usage.input == 10
    assert message.usage.output == 4
    assert message.usage.total_tokens == 14


def test_raw_assembler_preserves_provider_total_tokens_when_present() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(stream=stream, api="test", provider="test", model="test-model")

    assembler.feed({"type": "response_start", "response_id": "resp-1"})
    assembler.feed({"type": "usage_delta", "input": 10, "output": 4, "total_tokens": 42})
    assembler.feed({"type": "response_done"})

    message = asyncio.run(stream.result())

    assert message.usage.total_tokens == 42


def test_raw_assembler_never_reports_total_below_usage_components() -> None:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(stream=stream, api="test", provider="test", model="test-model")

    assembler.feed({"type": "response_start", "response_id": "resp-1"})
    assembler.feed({"type": "usage_delta", "input": 0, "output": 7, "cache_read": 36, "total_tokens": 7})
    assembler.feed({"type": "response_done"})

    message = asyncio.run(stream.result())

    assert message.usage.cache_read == 36
    assert message.usage.output == 7
    assert message.usage.total_tokens == 43
