"""Language-extensible semantic code intelligence for the Coding product."""

from loushang.coding.lsp.binding import CodingLspBinding
from loushang.coding.lsp.catalog import LspCatalog
from loushang.coding.lsp.client import LspClient
from loushang.coding.lsp.documents import DocumentSnapshot, LspDocumentManager
from loushang.coding.lsp.model import (
    CodeLocation,
    CodePosition,
    CodeQueryResult,
    CodeRange,
    LspError,
    LspInvalidInputError,
    LspProtocolError,
    LspServerDefinition,
    LspServerKey,
    LspServerSelection,
    LspUnavailableError,
)
from loushang.coding.lsp.ports import (
    AuthorizedProcessLauncher,
    ProcessExit,
    ProcessHandle,
    ProcessLaunchRequest,
    ProcessStderrTail,
)
from loushang.coding.lsp.selector import LspSelector
from loushang.coding.lsp.supervisor import LspRuntimeHandle, LspServerSupervisor
from loushang.coding.lsp.tools import (
    INSPECT_SYMBOL_TOOL_NAME,
    MAX_INSPECT_SYMBOL_RESULTS,
    CodingLspTools,
    create_inspect_symbol_tool_definition,
)

__all__ = [
    "AuthorizedProcessLauncher",
    "CodeLocation",
    "CodePosition",
    "CodeQueryResult",
    "CodeRange",
    "CodingLspBinding",
    "CodingLspTools",
    "DocumentSnapshot",
    "INSPECT_SYMBOL_TOOL_NAME",
    "LspCatalog",
    "LspClient",
    "LspDocumentManager",
    "LspError",
    "LspInvalidInputError",
    "LspProtocolError",
    "LspRuntimeHandle",
    "LspSelector",
    "LspServerDefinition",
    "LspServerKey",
    "LspServerSelection",
    "LspServerSupervisor",
    "LspUnavailableError",
    "MAX_INSPECT_SYMBOL_RESULTS",
    "ProcessExit",
    "ProcessHandle",
    "ProcessLaunchRequest",
    "ProcessStderrTail",
    "create_inspect_symbol_tool_definition",
]
