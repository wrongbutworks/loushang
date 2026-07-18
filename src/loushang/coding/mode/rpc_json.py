"""Compatibility projection helpers for the legacy Coding RPC adapter."""

from loushang.channel.json_projection import (
    ChannelJsonProjectionError,
    project_channel_value,
)
from loushang.protocol import JSONValue

RpcJsonProjectionError = ChannelJsonProjectionError


def project_rpc_value(value: object, *, name: str = "rpc_output") -> JSONValue:
    return project_channel_value(value, name=name, surface="RPC")


__all__ = ["RpcJsonProjectionError", "project_rpc_value"]
