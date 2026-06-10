"""Channel boundary protocol primitives."""

from loushang.channel.json_codec import (
    channel_envelope_from_json,
    channel_envelope_to_json,
)
from loushang.channel.types import (
    ChannelEndpoint,
    ChannelEnvelope,
    ChannelEnvelopeKind,
    ChannelPayload,
)

__all__ = [
    "ChannelEndpoint",
    "ChannelEnvelope",
    "ChannelEnvelopeKind",
    "ChannelPayload",
    "channel_envelope_from_json",
    "channel_envelope_to_json",
]
