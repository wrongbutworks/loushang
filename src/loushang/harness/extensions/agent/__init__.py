"""Typed in-process Agent integration for Harness extension runtimes.

The profile is optional: neutral ``harness.extensions`` modules do not import
it.  It composes extension input, Agent hooks, and lifecycle callbacks through
public Agent/AI values and injected ports; it is neither an event bus nor a
session runtime.
"""

from loushang.harness.extensions.agent.hooks import (
    BeforeAgentStartState,
    ContextHookEvent,
    ExtensionAgentHookPort,
    ExtensionAgentHookRuntime,
    ExtensionPromptHookDispatcher,
    ExtensionSessionHookDispatcher,
    ExtensionToolHookDispatcher,
    compose_after_tool_call_hooks,
    compose_before_tool_call_hooks,
)
from loushang.harness.extensions.agent.input import (
    ApplicationInputDeliveryPort,
    ExtensionApplicationInput,
    ExtensionInputRuntime,
    ExtensionUserInput,
    PreparedUserInputQueuePort,
)
from loushang.harness.extensions.agent.input_adapter import ExtensionInputAdapter
from loushang.harness.extensions.agent.lifecycle import (
    ExtensionAgentEventRuntime,
    ExtensionEventPort,
)
from loushang.harness.extensions.agent.replacement import ExtensionReplacementRuntime

__all__ = [
    "ApplicationInputDeliveryPort",
    "BeforeAgentStartState",
    "ContextHookEvent",
    "ExtensionAgentEventRuntime",
    "ExtensionAgentHookPort",
    "ExtensionAgentHookRuntime",
    "ExtensionToolHookDispatcher",
    "ExtensionApplicationInput",
    "ExtensionEventPort",
    "ExtensionInputRuntime",
    "ExtensionInputAdapter",
    "ExtensionPromptHookDispatcher",
    "ExtensionSessionHookDispatcher",
    "ExtensionReplacementRuntime",
    "ExtensionUserInput",
    "PreparedUserInputQueuePort",
    "compose_after_tool_call_hooks",
    "compose_before_tool_call_hooks",
]
