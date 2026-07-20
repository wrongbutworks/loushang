"""Compatibility facade for the Work-owned Agent event projection."""

from loushang.work.agent_projection import (
    AgentWorkFactProjectionContext,
    project_agent_event_to_work_facts,
)

CodingWorkFactProjectionContext = AgentWorkFactProjectionContext

__all__ = [
    "CodingWorkFactProjectionContext",
    "project_agent_event_to_work_facts",
]
