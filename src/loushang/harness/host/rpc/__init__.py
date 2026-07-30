"""Product-neutral JSONL RPC host."""

from .projections import (
    STANDARD_AGENT_RPC_EVENT_PROJECTION,
    STANDARD_RPC_DIAGNOSTICS_PROJECTION,
    RpcDiagnosticsProjection,
    RpcEventProjection,
)
from .remote_ui import RpcExtensionUIContext
from .runtime import (
    RpcHost,
    run_rpc_host,
)
from .types import RpcModel, RpcModelCost, RpcSessionState

__all__ = [
    "RpcDiagnosticsProjection",
    "RpcEventProjection",
    "RpcExtensionUIContext",
    "RpcHost",
    "RpcModel",
    "RpcModelCost",
    "RpcSessionState",
    "STANDARD_AGENT_RPC_EVENT_PROJECTION",
    "STANDARD_RPC_DIAGNOSTICS_PROJECTION",
    "run_rpc_host",
]
