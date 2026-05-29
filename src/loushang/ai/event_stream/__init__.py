from loushang.ai.event_stream.assembler import RawAssembler
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.event_stream.stream import AssistantMessageEventStream, EventStream

__all__ = [
    "AssistantMessageEventStream",
    "EventStream",
    "RawAssembler",
    "RawPart",
]


def create_assistant_message_event_stream() -> AssistantMessageEventStream:
    return AssistantMessageEventStream()
